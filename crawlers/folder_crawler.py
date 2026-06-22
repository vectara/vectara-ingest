import hashlib
import logging
import os
import pathlib
import time
import pandas as pd
import ray
import psutil
from slugify import slugify

from core.crawler import Crawler
from core.indexer import Indexer
from core.utils import setup_logging, get_docker_or_local_path, release_memory, AUDIO_EXTENSIONS, VIDEO_EXTENSIONS
from core.incremental import build_manifest, plan_deletions, source_is_newer
from core.summary import TableSummarizer
from omegaconf import DictConfig
from core.dataframe_parser import (
    supported_by_dataframe_parser,
    DataframeParser,
    determine_dataframe_type,
    get_separator_by_file_name,
    open_excel_with_fallback,
)

logger = logging.getLogger(__name__)


def _doc_id_for_file(file_name: str) -> str:
    # slugify is lossy ("a/b.txt" and "a-b.txt" both produce "a-b-txt"), so we
    # append a short hash of the original file_name to keep ids unique while
    # remaining human-readable in logs and the admin UI.
    path_hash = hashlib.sha256(file_name.encode("utf-8")).hexdigest()[:12]
    return f"{slugify(file_name)}-{path_hash}"

class FileCrawlWorker(object):
    def __init__(self, cfg: DictConfig, crawler_config: DictConfig, indexer: Indexer, num_per_second: int):
        self.indexer = indexer
        self.cfg = cfg
        self.crawler_config = crawler_config

    def setup(self):
        self.indexer.setup()
        setup_logging()
        # Initialize the parser once per worker
        table_summarizer = TableSummarizer(self.cfg, self.cfg.doc_processing.model_config.text)
        self.df_parser = DataframeParser(self.cfg, self.crawler_config, self.indexer, table_summarizer)

    def cleanup(self):
        self.indexer.cleanup()
        self.df_parser = None
        release_memory()

    def process(self, file_path: str, file_name: str, metadata: dict, prior_fingerprint: str = None):
        extension = pathlib.Path(file_path).suffix.lower()
        succeeded = False
        # Media and dataframe docs are stored under doc_ids unrelated to _doc_id_for_file
        # (slugify(path) for media, the dataframe doc_id for tables, plus one doc per xls
        # sheet). Tag them as sub-docs of the file's primary key so the deletion pass treats
        # them as present iff the file is present (no-op unless incremental). Without this they
        # would be flagged as orphans and deleted on every incremental run.
        parent_key = _doc_id_for_file(file_name)
        try:
            if extension in AUDIO_EXTENSIONS + VIDEO_EXTENSIONS:
                self.indexer.stamp_subdoc_metadata(metadata, parent_key)
                succeeded = self.indexer.index_media_file(file_path, metadata=metadata)

            elif supported_by_dataframe_parser(file_path):
                self.indexer.stamp_subdoc_metadata(metadata, parent_key)
                logger.info(f"Parsing dataframe {file_path}")
                file_type = determine_dataframe_type(file_path)
                doc_title = os.path.basename(file_path)

                if file_type == 'csv':
                    separator = get_separator_by_file_name(file_path)
                    df = pd.read_csv(file_path, sep=separator)
                    self.df_parser.process_dataframe(df, doc_id=file_path, doc_title=doc_title, metadata=metadata)

                elif file_type == 'xls':
                    xls = open_excel_with_fallback(file_path)
                    sheet_names = self.crawler_config.get("sheet_names", xls.sheet_names)
                    for sheet_name in sheet_names:
                        if sheet_name not in xls.sheet_names:
                            logger.warning(f"Sheet '{sheet_name}' not found in '{file_path}'. Skipping.")
                            continue

                        df = pd.read_excel(xls, sheet_name=sheet_name)
                        sheet_doc_id = f"{file_path}_{sheet_name}"
                        sheet_doc_title = f"{doc_title} - {sheet_name}"
                        self.df_parser.process_dataframe(df, doc_id=sheet_doc_id, doc_title=sheet_doc_title, metadata=metadata)

                succeeded = True  # process_dataframe has no return value; assume success if no exception

            else:
                uri_to_use = file_name if "url" not in metadata else metadata["url"]
                # Stable doc_id derived from the relative file_name so that re-indexing
                # after metadata changes (e.g. adding a "url" field) updates the
                # existing document instead of creating a new one with a URL-derived id.
                doc_id = _doc_id_for_file(file_name)
                succeeded = bool(self.indexer.index_file(filename=file_path, uri=uri_to_use, metadata=metadata,
                                                         id=doc_id, prior_fingerprint=prior_fingerprint))

            logger.info(f"Finished indexing {file_path} with metadata={metadata}")

        except Exception as e:
            import traceback
            logger.error(f"Error while indexing {file_path}: {e}, traceback={traceback.format_exc()}")
            return -1
        finally:
            release_memory()
        if succeeded and self.indexer.was_skipped():
            return 2  # unchanged — skipped
        return 0 if succeeded else 1


class FolderCrawler(Crawler):

    def crawl(self) -> None:
        folder_config = self.cfg.folder_crawler
        docker_path = "/home/vectara/data"
        config_path = folder_config.path

        folder = get_docker_or_local_path(docker_path=docker_path, config_path=config_path)

        extensions = [e.lower() if isinstance(e, str) else e for e in folder_config.get("extensions", ["*"])]
        metadata_file = folder_config.get("metadata_file", None)
        ray_workers = folder_config.get("ray_workers", 0)
        num_per_second = max(folder_config.get("num_per_second", 10), 1)
        source = folder_config.get("source", "folder")
        incremental = folder_config.get("incremental", False)
        remove_old_content = folder_config.get("remove_old_content", False)

        if metadata_file:
            df = pd.read_csv(f"{folder}/{metadata_file}")
            metadata = {row["filename"].strip(): row.drop("filename").to_dict() for _, row in df.iterrows()}
        else:
            metadata = {}

        logger.info(f"Indexing files in {folder_config.path} with extensions {extensions}")
        
        files_to_process = []
        for root, _, files in os.walk(folder):
            for file in files:
                if metadata_file and file.endswith(metadata_file):
                    continue

                file_extension = pathlib.Path(file).suffix.lower()
                if "*" in extensions or file_extension in extensions:
                    file_path = os.path.join(root, file)
                    file_name = os.path.relpath(file_path, folder)
                    
                    rel_under_container = os.path.relpath(root, folder)
                    full_folder_path = os.path.normpath(os.path.join(folder_config.path, rel_under_container))
                    parent = os.path.basename(full_folder_path)

                    file_metadata = {
                        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(os.path.getctime(file_path))),
                        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(os.path.getmtime(file_path))),
                        "file_size": os.path.getsize(file_path),
                        "source": source,
                        "title": file_name,
                        "parent_folder": parent,
                        "folder_path": full_folder_path,
                    }
                    if file_name in metadata:
                        file_metadata.update(metadata.get(file_name, {}))
                    
                    files_to_process.append((file_path, file_name, file_metadata))

        # Compute each file's Vectara doc_id once (sha256+slugify) and reuse it for present_keys,
        # the mtime prefilter, and the per-file prior_fingerprint lookup.
        doc_id_by_name = {fn: _doc_id_for_file(fn) for _fp, fn, _fm in files_to_process}
        # Full discovered set (everything that still exists at the source) keyed by Vectara
        # doc_id — used for safe deletion of removed files. Captured before any skipping.
        present_keys = set(doc_id_by_name.values())
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
            # Layer 1: skip files whose mtime (file_metadata['last_updated']) is not newer
            # than what we indexed — without reading/parsing them.
            kept, skipped = [], 0
            for fp, fn, fm in files_to_process:
                entry = manifest.get(doc_id_by_name[fn])
                if entry and entry.last_updated and not source_is_newer(fm.get("last_updated"), entry.last_updated):
                    skipped += 1
                    if self.tracker:
                        self.tracker.track_skipped(fp, title=fn)
                else:
                    kept.append((fp, fn, fm))
            if skipped:
                logger.info(f"Incremental: skipped {skipped} unchanged files via mtime "
                            f"({len(kept)} remaining)")
            files_to_process = kept
        elif self.tracker and not self.cfg.vectara.get("reindex", False):
            # Legacy blind crash-recovery pre-filter — suppressed under incremental.
            indexed = self.tracker.get_indexed_ids()
            before = len(files_to_process)
            files_to_process = [(fp, fn, fm) for fp, fn, fm in files_to_process if fp not in indexed]
            logger.info(f"Skipping {before - len(files_to_process)} already-indexed files ({len(files_to_process)} remaining)")

        def _track(file_path, file_name, result):
            if not self.tracker:
                return
            if result == 0:
                self.tracker.track_indexed(file_path, title=file_name)
            elif result == 2:
                self.tracker.track_skipped(file_path, title=file_name)
            else:
                self.tracker.track_failed(file_path, title=file_name)

        if ray_workers == -1:
            ray_workers = psutil.cpu_count(logical=True)

        # Decide which config to use for the dataframe parser
        df_parser_config = self.cfg.get('dataframe_processing', self.cfg.get('folder_crawler'))

        try:
            if ray_workers > 0:
                logger.info(f"Using {ray_workers} ray workers to process {len(files_to_process)} files")
                self.indexer.p = self.indexer.browser = None
                ray.init(num_cpus=ray_workers, log_to_driver=True, include_dashboard=False)
                actors = [
                    ray.remote(FileCrawlWorker).remote(self.cfg, df_parser_config, self.indexer, num_per_second)
                    for _ in range(ray_workers)
                ]
                ray.get([a.setup.remote() for a in actors])
                pool = ray.util.ActorPool(actors)
                batch_size = ray_workers * 4
                for batch_start in range(0, len(files_to_process), batch_size):
                    self.check_shutdown()
                    batch = files_to_process[batch_start:batch_start + batch_size]
                    results = list(pool.map(
                        lambda a, u: a.process.remote(
                            u[0], u[1], u[2],
                            prior_fingerprint=prior_fingerprints.get(doc_id_by_name[u[1]])),
                        batch))
                    for (file_path, file_name, _fm), result in zip(batch, results):
                        _track(file_path, file_name, result)
                    logger.info(f"Processed {min(batch_start + batch_size, len(files_to_process))}/{len(files_to_process)} files")
                ray.get([a.cleanup.remote() for a in actors])
            else:
                crawl_worker = FileCrawlWorker(self.cfg, df_parser_config, self.indexer, num_per_second)
                crawl_worker.setup()
                for inx, (file_path, file_name, file_metadata) in enumerate(files_to_process):
                    self.check_shutdown()
                    if (inx + 1) % 100 == 0:
                        logger.info(f"Crawling file number {inx+1} out of {len(files_to_process)}")
                    result = crawl_worker.process(
                        file_path, file_name, file_metadata,
                        prior_fingerprint=prior_fingerprints.get(doc_id_by_name[file_name]))
                    _track(file_path, file_name, result)
                crawl_worker.cleanup()
        except Exception:
            crawl_complete = False
            raise
        finally:
            # Always release Ray, even if a batch raised mid-crawl — otherwise the cluster
            # and its worker processes leak into subsequent runs in the same environment.
            if ray_workers > 0:
                ray.shutdown()

        # Delete files removed from the source folder (guarded against a partial crawl).
        # Requires incremental: only then do media/dataframe/split-PDF docs carry the
        # parent_doc_id tag that keeps the deletion pass from wrongly removing them.
        if remove_old_content and not incremental:
            logger.warning("folder_crawler.remove_old_content requires incremental: true to "
                           "safely handle media/dataframe/split-PDF documents; skipping deletion.")
        elif remove_old_content and incremental and manifest:
            ratio = folder_config.get("deletion_safety_ratio", 0.5)
            to_delete, refused = plan_deletions(manifest, present_keys, crawl_complete, ratio)
            if not refused:
                for doc_id in to_delete:
                    self.indexer.delete_doc(doc_id)
                logger.info(f"Removed {len(to_delete)} docs not present in the source folder.")
