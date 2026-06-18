"""
Incremental reindexing primitives — keeping a Vectara corpus consistent with its source.

The Vectara corpus itself is the manifest: at index time each document's metadata is
stamped with a content fingerprint, and on the next run a single `_list_docs()` pass
reconstructs what is already indexed and how it was fingerprinted. That manifest drives a
3-way sync: index new items, re-index changed ones, delete removed ones.

This module is deliberately crawler-agnostic. Crawlers supply a cheap "did it change"
signal (sitemap <lastmod>, RSS pub_date, S3 LastModified, file mtime) and a doc_id; the
indexer supplies the content hash. Nothing here fetches or parses content.

Design notes:
- The fingerprint covers content + metadata + ingest-config, not just content. A
  content-only hash would silently skip metadata-only changes (e.g. updated GDrive
  `acl_groups`, a security correctness bug) and ingest-config changes (e.g. a new
  `extract_metadata` question would otherwise leave docs processed under the old config).
- `compute_fingerprint` strips reserved/volatile keys so it is idempotent: re-running it on
  metadata that already carries our stamps yields the same value.
- All comparisons fail safe: on any ambiguity we re-index rather than risk staleness, and we
  refuse to delete rather than risk wiping live documents.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from core.indexer_utils import normalize_url_for_metadata

logger = logging.getLogger(__name__)

# Metadata keys this pipeline manages itself. They are excluded from the fingerprint so that
# stamping them back into a metadata dict does not change the next run's fingerprint, and so
# that pipeline-derived fields (which are deterministic functions of content + config and
# thus already captured by content_hash + config_sig) do not cause churn.
RESERVED_METADATA_KEYS = frozenset(
    {"fingerprint", "content_hash", "source", "parent_doc_id", "last_updated", "file_name"}
)

# Config keys that change how a document is processed. A change to any of these must
# invalidate the skip decision, otherwise documents stay processed under the old pipeline.
_CONFIG_SIG_DOC_PROCESSING_KEYS = (
    "doc_parser",
    "extract_metadata",
    "contextual_chunking",
    "summarize_images",
    "add_image_bytes",
    "remove_boilerplate",
    "remove_code",
    "parse_tables",
    "enable_gmft",
    "do_ocr",
    "use_core_indexing",
    "unstructured_config",
    "docling_config",
    "image_context",
)
_CONFIG_SIG_VECTARA_KEYS = ("chunking_strategy", "chunk_size")


@dataclass
class ManifestEntry:
    """One document as it currently exists in the corpus."""
    doc_id: str
    fingerprint: Optional[str] = None
    content_hash: Optional[str] = None
    last_updated: Optional[str] = None
    parent_doc_id: Optional[str] = None
    url: Optional[str] = None


def _canonical_json(obj: Any) -> str:
    """Stable JSON for hashing: sorted keys, no whitespace, default=str for odd types."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True)


def _meaningful_metadata(metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Metadata that should participate in the fingerprint (reserved keys removed)."""
    if not metadata:
        return {}
    return {k: v for k, v in metadata.items() if k not in RESERVED_METADATA_KEYS}


def compute_fingerprint(content_hash: Optional[str],
                        metadata: Optional[Dict[str, Any]],
                        config_sig: str) -> str:
    """
    Composite content+metadata+config fingerprint used as the skip decision.

    Callers must pass the *source* metadata (what the crawler provides), not pipeline-derived
    fields, so the value is stable across runs. Reserved keys are stripped here defensively.
    """
    payload = "|".join([
        content_hash or "",
        _canonical_json(_meaningful_metadata(metadata)),
        config_sig or "",
    ])
    return hashlib.md5(payload.encode("utf-8")).hexdigest()


def config_signature(cfg: Any) -> str:
    """md5 of the processing-relevant config subset; compute once per run."""
    doc_processing = {}
    if "doc_processing" in cfg:
        for k in _CONFIG_SIG_DOC_PROCESSING_KEYS:
            if k in cfg.doc_processing:
                doc_processing[k] = cfg.doc_processing.get(k)
    vectara = {}
    if "vectara" in cfg:
        for k in _CONFIG_SIG_VECTARA_KEYS:
            if k in cfg.vectara:
                vectara[k] = cfg.vectara.get(k)
    # OmegaConf containers must be resolved to plain Python before JSON serialization.
    try:
        from omegaconf import OmegaConf
        doc_processing = OmegaConf.to_container(OmegaConf.create(doc_processing), resolve=True)
        vectara = OmegaConf.to_container(OmegaConf.create(vectara), resolve=True)
    except Exception:
        pass
    return hashlib.md5(
        _canonical_json({"doc_processing": doc_processing, "vectara": vectara}).encode("utf-8")
    ).hexdigest()


def build_manifest(indexer: Any, key: str = "url", source: Optional[str] = None) -> Dict[str, ManifestEntry]:
    """
    One corpus scan -> {key: ManifestEntry}. `key` is "url" (normalized doc URL) for
    URL-based crawlers or "id" (doc_id) for file-based crawlers. `source` scopes the listing
    to this crawler's own documents so a shared corpus is not cross-deleted.
    """
    manifest: Dict[str, ManifestEntry] = {}
    for d in indexer._list_docs(source=source):
        entry = ManifestEntry(
            doc_id=d.get("id"),
            fingerprint=d.get("fingerprint"),
            content_hash=d.get("content_hash"),
            last_updated=d.get("last_updated"),
            parent_doc_id=d.get("parent_doc_id"),
            url=d.get("url"),
        )
        if key == "url":
            if not entry.url:
                continue
            manifest[normalize_url_for_metadata(entry.url)] = entry
        else:
            if not entry.doc_id:
                continue
            manifest[entry.doc_id] = entry
    return manifest


def _parse_dt(sig: Any) -> Optional[datetime]:
    """Parse a date/time signal (RFC822 / ISO8601 / YYYY-MM-DD / epoch) into aware UTC."""
    if sig is None:
        return None
    if isinstance(sig, datetime):
        dt = sig
    elif isinstance(sig, (int, float)):
        try:
            dt = datetime.fromtimestamp(float(sig), tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None
    else:
        s = str(sig).strip()
        if not s:
            return None
        dt = None
        # epoch-as-string
        try:
            dt = datetime.fromtimestamp(float(s), tz=timezone.utc)
        except (ValueError, OverflowError, OSError):
            dt = None
        if dt is None:
            for parser in (datetime.fromisoformat, parsedate_to_datetime):
                try:
                    dt = parser(s.replace("Z", "+00:00") if parser is datetime.fromisoformat else s)
                    break
                except (ValueError, TypeError):
                    continue
        if dt is None:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def source_is_newer(current_sig: Any, stored_sig: Any) -> bool:
    """
    True if the source signal is strictly newer than what we last indexed — i.e. "fetch it".

    Fail-safe: returns True (fetch) whenever either side is missing or unparseable, so we
    never skip a document on uncertainty.
    """
    cur = _parse_dt(current_sig)
    stored = _parse_dt(stored_sig)
    if cur is None or stored is None:
        return True
    return cur > stored


def plan_deletions(manifest: Dict[str, ManifestEntry],
                   present_keys: Set[str],
                   listing_complete: bool,
                   min_ratio: float = 0.5) -> Tuple[List[str], bool]:
    """
    Decide which corpus docs to delete (present in the manifest but not at the source).

    `present_keys` MUST include items skipped as unchanged (still live) so they are not
    deleted. Sub-documents (those with a parent_doc_id) are treated as present iff their
    parent is present, so re-indexing a parent never orphans its image/part sub-docs.

    Safety guard (mirrors box_crawler): refuse the whole deletion if the crawl was
    incomplete, or if the source produced fewer than `min_ratio` of the corpus — protecting
    against an interrupted/partial crawl mass-deleting live documents. Returns
    (doc_ids_to_delete, refused).
    """
    if not manifest:
        return [], False

    # doc_ids of primary (non-sub) docs that are still present at the source. A primary doc's
    # manifest key is in present_keys; this set lets sub-docs (keyed differently — by their own
    # url or id) resolve their parent regardless of the manifest's keying scheme.
    present_doc_ids = {
        e.doc_id for k, e in manifest.items()
        if not e.parent_doc_id and k in present_keys
    }
    all_doc_ids = {e.doc_id for e in manifest.values()}

    def _is_present(k: str, e: ManifestEntry) -> bool:
        if e.parent_doc_id:
            # A sub-doc survives iff its parent survives. If the parent is unknown to this
            # manifest (e.g. different keying / not listed), stay conservative and keep it.
            return (e.parent_doc_id in present_doc_ids) or (e.parent_doc_id not in all_doc_ids)
        return k in present_keys

    to_delete = [e.doc_id for k, e in manifest.items() if not _is_present(k, e)]

    if not listing_complete:
        logger.warning(
            "Skipping deletion of %d doc(s): source listing was incomplete/interrupted — "
            "refusing to mass-delete live documents.", len(to_delete))
        return [], True

    if min_ratio > 0 and len(present_keys) < len(manifest) * min_ratio:
        logger.warning(
            "Skipping deletion of %d doc(s): source produced %d items vs %d in corpus "
            "(below deletion_safety_ratio=%.2f) — refusing to mass-delete. Set "
            "deletion_safety_ratio: 0 to override.",
            len(to_delete), len(present_keys), len(manifest), min_ratio)
        return [], True

    return to_delete, False
