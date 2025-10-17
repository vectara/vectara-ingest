import pathlib
import boto3
import os
from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)

from core.crawler import Crawler
from core.indexer import Indexer
from core.utils import RateLimiter, setup_logging, AUDIO_EXTENSIONS, VIDEO_EXTENSIONS

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
    
    else:
        raise ValueError("No AWS credentials found!")
    
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
    def __init__(self, indexer: Indexer, crawler: Crawler, num_per_second: int, bucket: str, cfg):
        self.crawler = crawler
        self.indexer = indexer
        self.rate_limiter = RateLimiter(num_per_second)
        self.bucket = bucket
        self.cfg = cfg

    def setup(self):
        self.indexer.setup()
        setup_logging()

    def process(self, s3_file: str, metadata: dict, source: str):
        s3 = create_s3_client(self.cfg)
        extension = pathlib.Path(s3_file).suffix
        local_fname = slugify(s3_file.replace(extension, ''), separator='_') + '.' + extension
        logger.info(f"Crawling and indexing {s3_file}")
        try:
            with self.rate_limiter:
                s3.download_file(self.bucket, s3_file, local_fname)
                url = f's3://{self.bucket}/{s3_file}'
                metadata.update({
                    'source': source,
                    'title': s3_file,
                    'url': url
                })
                if extension in AUDIO_EXTENSIONS + VIDEO_EXTENSIONS:
                    succeeded = self.indexer.index_media_file(local_fname, metadata)
                else:
                    succeeded = self.indexer.index_file(filename=local_fname, uri=url, metadata=metadata)
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
        return 0


def list_files_in_s3_bucket(bucket_name: str, prefix: str, cfg) -> List[str]:
    """
    List all files in an S3 bucket.

    args:
        bucket_name: name of the S3 bucket
        prefix: the "folder" on S3 to list files from
        cfg: configuration object for S3 client creation
    """
    s3 = create_s3_client(cfg)
    result = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
    files = []

    for content in result.get('Contents', []):
        files.append(content['Key'])

    while result.get('IsTruncated', False):
        continuation_key = result.get('NextContinuationToken')
        result = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix, ContinuationToken=continuation_key)

        for content in result.get('Contents', []):
            files.append(content['Key'])

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
        extensions = self.cfg.s3_crawler.extensions
        metadata_file = self.cfg.s3_crawler.get("metadata_file", None)
        ray_workers = self.cfg.s3_crawler.get("ray_workers", 0)            # -1: use ray with ALL cores, 0: dont use ray
        num_per_second = max(self.cfg.s3_crawler.get("num_per_second", 10), 1)
        source = self.cfg.s3_crawler.get("source", "S3")

        s3 = create_s3_client(self.cfg)
        bucket, key = split_s3_uri(folder)

        if metadata_file:
            local_metadata_fname = slugify(metadata_file)
            s3.download_file(bucket, metadata_file, local_metadata_fname)
            df = pd.read_csv(local_metadata_fname)
            metadata = {row['filename'].strip(): row.drop('filename').to_dict() for _, row in df.iterrows()}
        else:
            metadata = {}
        self.model = None

        # process all files
        s3_files = list_files_in_s3_bucket(bucket, key, self.cfg)
        files_to_process = []
        for s3_file in s3_files:
            if metadata_file and s3_file.endswith(metadata_file):
                continue
            file_extension = pathlib.Path(s3_file).suffix
            if file_extension in extensions or "*" in extensions:
                files_to_process.append(s3_file)

        # Now process all files
        if ray_workers == -1:
            ray_workers = psutil.cpu_count(logical=True)

        if ray_workers > 0:
            logger.info(f"Using {ray_workers} ray workers")
            self.indexer.p = self.indexer.browser = None
            ray.init(num_cpus=ray_workers, log_to_driver=True, include_dashboard=False)
            actors = [ray.remote(FileCrawlWorker).remote(self.indexer, self, num_per_second, bucket, self.cfg) for _ in range(ray_workers)]
            for a in actors:
                a.setup.remote()
            pool = ray.util.ActorPool(actors)
            _ = list(pool.map(lambda a, u: a.process.remote(u, metadata=metadata, source=source), files_to_process))
            ray.shutdown()
        else:
            crawl_worker = FileCrawlWorker(self.indexer, self, num_per_second, bucket, self.cfg)
            for inx, url in enumerate(files_to_process):
                if inx % 100 == 0:
                    logger.info(f"Crawling URL number {inx+1} out of {len(files_to_process)}")
                crawl_worker.process(url, metadata=metadata, source=source)
