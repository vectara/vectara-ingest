import pathlib
import boto3
import os
from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)

from core.crawler import Crawler
from core.indexer import Indexer
from core.utils import RateLimiter, setup_logging, release_memory, AUDIO_EXTENSIONS, VIDEO_EXTENSIONS
from core.incremental import build_manifest, plan_deletions, source_is_newer

from slugify import slugify
import pandas as pd
import ray
import psutil

def create_s3_client(cfg):
    """Create boto3 S3 client with optional custom endpoint"""
    endpoint_url = cfg.s3_crawler.get("endpoint_url", None)
    aws_access_key_id = cfg.s3_crawler.get("aws_access_key_id", None)
    aws_secret_access_key = cfg.s3_crawler.get("aws_secret_access_key", None)
    
    client_kwargs = {}
    if endpoint_url:
        client_kwargs['endpoint_url'] = endpoint_url
    
    if aws_access_key_id and aws_secret_access_key:
        client_kwargs['aws_access_key_id'] = aws_access_key_id
        client_kwargs['aws_secret_access_key'] = aws_secret_access_key
    elif aws_access_key_id or aws_secret_access_key:
        raise ValueError(
            "S3 crawler: aws_access_key_id and aws_secret_access_key must be set together. "
            "Provide both or omit both (to use the boto3 default credential chain)."
        )
    # else: both omitted — fall through and let boto3 resolve credentials from
    # the standard chain (env vars, shared config, IAM role, instance metadata).
    # boto3 will raise NoCredentialsError at the first call site if nothing resolves.
    
    # Handle SSL verification based on vectara config
    ssl_verify = cfg.vectara.get("ssl_verify", None)
    if ssl_verify is False or (isinstance(ssl_verify, str) and ssl_verify.lower() in ("false", "0")):
        logger.warning("Disabling SSL verification for S3 client.")
        client_kwargs['verify'] = False
    elif ssl_verify is True or (isinstance(ssl_verify, str) and ssl_verify.lower() in ("true", "1")):
        # Use default SSL verification - no need to set verify parameter
        logger.debug("Using default SSL verification for S3 client.")
    elif isinstance(ssl_verify, str):
        # If ssl_verify is a string and not true/false, treat it as a path to certificate file
        if os.path.exists(ssl_verify):
            logger.info(f"Using certificate path for S3 client: {ssl_verify}")
            client_kwargs['verify'] = ssl_verify
        else:
            # Try expanded path (handles ~ in paths)
            ca_path = os.path.expanduser(ssl_verify)
            if os.path.exists(ca_path):
                logger.info(f"Using expanded certificate path for S3 client: {ca_path}")
                client_kwargs['verify'] = ca_path
            else:
                logger.warning(f"Certificate path '{ssl_verify}' not found. Using default SSL verification for S3 client.")
    # If ssl_verify is None or any other value, use default SSL verification (don't set verify parameter)
    
    return boto3.client('s3', **client_kwargs)

class FileCrawlWorker(object):
    def __init__(self, indexer: Indexer, num_per_second: int, bucket: str, cfg):
        self.indexer = indexer
        self.rate_limiter = RateLimiter(num_per_second)
        self.bucket = bucket
        self.cfg = cfg

    def setup(self):
        self.indexer.setup()
        setup_logging()

    def cleanup(self):
        self.indexer.cleanup()
        release_memory()

    def process(self, s3_file: str, metadata: dict, source: str,
                prior_fingerprint: str = None, last_modified: str = None):
        s3 = create_s3_client(self.cfg)
        extension = pathlib.Path(s3_file).suffix
        local_fname = slugify(s3_file.replace(extension, ''), separator='_') + '.' + extension
        url = f's3://{self.bucket}/{s3_file}'
        logger.info(f"Crawling and indexing {s3_file}")
        try:
            with self.rate_limiter:
                s3.download_file(self.bucket, s3_file, local_fname)
                metadata = dict(metadata)  # don't mutate the shared/base metadata
                metadata.update({
                    'source': source,
                    'title': s3_file,
                    'url': url
                })
                # Store the object's LastModified as the cheap change signal for next run.
                if last_modified:
                    metadata['last_updated'] = str(last_modified)
                if extension.lower() in AUDIO_EXTENSIONS + VIDEO_EXTENSIONS:
                    # index_media_file stores under slugify(local_fname), not the url-derived
                    # doc_id the crawl tracks. Tag it as a sub-doc of the file's primary key so
                    # the deletion pass never removes a live media doc (no-op unless incremental).
                    self.indexer.stamp_subdoc_metadata(metadata, slugify(url))
                    succeeded = self.indexer.index_media_file(local_fname, metadata)
                else:
                    succeeded = self.indexer.index_file(filename=local_fname, uri=url, metadata=metadata,
                                                        prior_fingerprint=prior_fingerprint)
            if not succeeded:
                logger.info(f"Indexing failed for {url}")
            else:
                logger.info(f"Indexing {url} was successful")
        except Exception as e:
            import traceback
            logger.error(
                f"Error while indexing {url}: {e}, traceback={traceback.format_exc()}"
            )
            return -1
        finally:
            release_memory()
        if succeeded and self.indexer.was_skipped():
            return 2  # unchanged — skipped (distinct from indexed)
        return 0 if succeeded else 1


def list_files_in_s3_bucket(bucket_name: str, prefix: str, cfg) -> List[Tuple[str, str]]:
    """
    List all files in an S3 bucket.

    args:
        bucket_name: name of the S3 bucket
        prefix: the "folder" on S3 to list files from
        cfg: configuration object for S3 client creation

    Returns a list of (key, last_modified) tuples. `last_modified` is the object's
    LastModified (ISO string), used as the cheap change signal for incremental crawls.
    """
    s3 = create_s3_client(cfg)
    result = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
    files = []

    def _collect(res):
        for content in res.get('Contents', []):
            lm = content.get('LastModified')
            files.append((content['Key'], lm.isoformat() if lm is not None else None))

    _collect(result)
    while result.get('IsTruncated', False):
        continuation_key = result.get('NextContinuationToken')
        result = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix, ContinuationToken=continuation_key)
        _collect(result)

    return files

def split_s3_uri(s3_uri: str) -> Tuple[str, str]:
    """
    Split an S3 URI into bucket and object key.
    """
    bucket_and_object = s3_uri[len("s3://"):].split("/", 1)
    bucket = bucket_and_object[0]
    object_key = bucket_and_object[1] if len(bucket_and_object) > 1 else ""
    return bucket, object_key

class S3Crawler(Crawler):
    """
    Crawler for S3 files.
    """
    def crawl(self) -> None:
        folder = self.cfg.s3_crawler.s3_path
        extensions = [e.lower() if isinstance(e, str) else e for e in self.cfg.s3_crawler.extensions]
        metadata_file = self.cfg.s3_crawler.get("metadata_file", None)
        ray_workers = self.cfg.s3_crawler.get("ray_workers", 0)            # -1: use ray with ALL cores, 0: dont use ray
        num_per_second = max(self.cfg.s3_crawler.get("num_per_second", 10), 1)
        source = self.cfg.s3_crawler.get("source", "S3")
        incremental = self.cfg.s3_crawler.get("incremental", False)
        remove_old_content = self.cfg.s3_crawler.get("remove_old_content", False)

        s3 = create_s3_client(self.cfg)
        bucket, key = split_s3_uri(folder)

        def _doc_id_for(s3_file: str) -> str:
            return slugify(f's3://{bucket}/{s3_file}')

        if metadata_file:
            local_metadata_fname = slugify(metadata_file)
            s3.download_file(bucket, metadata_file, local_metadata_fname)
            df = pd.read_csv(local_metadata_fname)
            metadata = {row['filename'].strip(): row.drop('filename').to_dict() for _, row in df.iterrows()}
        else:
            metadata = {}

        # process all files
        s3_files = list_files_in_s3_bucket(bucket, key, self.cfg)
        files_to_process = []          # list of file keys
        lastmod_by_file = {}           # key -> LastModified (cheap change signal)
        for s3_file, lastmod in s3_files:
            if metadata_file and s3_file.endswith(metadata_file):
                continue
            file_extension = pathlib.Path(s3_file).suffix.lower()
            if file_extension in extensions or "*" in extensions:
                files_to_process.append(s3_file)
                lastmod_by_file[s3_file] = lastmod

        # Compute each object's Vectara doc_id once (slugify of the s3 uri) and reuse it for
        # present_keys, the LastModified prefilter, and the per-object prior_fingerprint lookup.
        doc_id_by_file = {f: _doc_id_for(f) for f in files_to_process}
        # Full discovered set (everything that still exists at the source) keyed by Vectara
        # doc_id — used for safe deletion of removed objects. Captured before any skipping.
        present_keys = set(doc_id_by_file.values())
        crawl_complete = True

        # Build the corpus manifest once when needed for incremental skipping and/or deletion.
        manifest = {}
        if incremental or remove_old_content:
            manifest = build_manifest(self.indexer, key="id",
                                      source=(self.indexer.source_tag if incremental else None))
            logger.info(f"Loaded corpus manifest: {len(manifest)} existing documents")

        prior_fingerprints = {}
        if incremental and manifest:
            prior_fingerprints = {k: e.fingerprint for k, e in manifest.items() if e.fingerprint}
            # Layer 1: skip objects whose LastModified is not newer than what we indexed.
            kept, skipped = [], 0
            for f in files_to_process:
                entry = manifest.get(doc_id_by_file[f])
                if entry and entry.last_updated and not source_is_newer(lastmod_by_file.get(f), entry.last_updated):
                    skipped += 1
                    if self.tracker:
                        self.tracker.track_skipped(f, url=f's3://{bucket}/{f}', title=f)
                else:
                    kept.append(f)
            if skipped:
                logger.info(f"Incremental: skipped {skipped} unchanged S3 files via LastModified "
                            f"({len(kept)} remaining)")
            files_to_process = kept
        elif self.tracker and not self.cfg.vectara.get("reindex", False):
            # Legacy blind crash-recovery pre-filter — suppressed under incremental.
            indexed = self.tracker.get_indexed_ids()
            before = len(files_to_process)
            files_to_process = [f for f in files_to_process if f not in indexed]
            logger.info(f"Skipping {before - len(files_to_process)} already-indexed S3 files ({len(files_to_process)} remaining)")

        def _track(s3_file, result):
            if not self.tracker:
                return
            s3_url = f's3://{bucket}/{s3_file}'
            if result == 0:
                self.tracker.track_indexed(s3_file, url=s3_url, title=s3_file)
            elif result == 2:
                self.tracker.track_skipped(s3_file, url=s3_url, title=s3_file)
            else:
                self.tracker.track_failed(s3_file, url=s3_url, title=s3_file)

        # Now process all files
        if ray_workers == -1:
            ray_workers = psutil.cpu_count(logical=True)

        try:
            if ray_workers > 0:
                logger.info(f"Using {ray_workers} ray workers")
                self.indexer.p = self.indexer.browser = None
                ray.init(num_cpus=ray_workers, log_to_driver=True, include_dashboard=False)
                actors = [ray.remote(FileCrawlWorker).remote(self.indexer, num_per_second, bucket, self.cfg) for _ in range(ray_workers)]
                ray.get([a.setup.remote() for a in actors])
                pool = ray.util.ActorPool(actors)
                batch_size = max(ray_workers * 4, 20)
                for batch_start in range(0, len(files_to_process), batch_size):
                    self.check_shutdown()
                    batch = files_to_process[batch_start:batch_start + batch_size]
                    results = list(pool.map(
                        lambda a, u: a.process.remote(
                            u, metadata=metadata, source=source,
                            prior_fingerprint=prior_fingerprints.get(doc_id_by_file[u]),
                            last_modified=lastmod_by_file.get(u)),
                        batch))
                    for s3_file, result in zip(batch, results):
                        _track(s3_file, result)
                    logger.info(f"Processed {min(batch_start + batch_size, len(files_to_process))}/{len(files_to_process)} S3 files")
                ray.get([a.cleanup.remote() for a in actors])
                ray.shutdown()
            else:
                crawl_worker = FileCrawlWorker(self.indexer, num_per_second, bucket, self.cfg)
                crawl_worker.setup()
                for inx, url in enumerate(files_to_process):
                    self.check_shutdown()
                    if inx % 100 == 0:
                        logger.info(f"Crawling URL number {inx+1} out of {len(files_to_process)}")
                    result = crawl_worker.process(
                        url, metadata=metadata, source=source,
                        prior_fingerprint=prior_fingerprints.get(doc_id_by_file[url]),
                        last_modified=lastmod_by_file.get(url))
                    _track(url, result)
        except Exception:
            crawl_complete = False
            raise

        # Delete objects removed from S3 (guarded against a partial crawl). Requires
        # incremental: only then do media docs carry the parent_doc_id tag that keeps the
        # deletion pass from wrongly removing them.
        if remove_old_content and not incremental:
            logger.warning("s3_crawler.remove_old_content requires incremental: true to safely "
                           "handle media documents; skipping deletion.")
        elif remove_old_content and incremental and manifest:
            ratio = self.cfg.s3_crawler.get("deletion_safety_ratio", 0.5)
            to_delete, refused = plan_deletions(manifest, present_keys, crawl_complete, ratio)
            if not refused:
                for doc_id in to_delete:
                    self.indexer.delete_doc(doc_id)
                logger.info(f"Removed {len(to_delete)} S3 docs not present in the source bucket.")
