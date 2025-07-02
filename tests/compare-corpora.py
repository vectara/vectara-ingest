import requests
import json
import difflib
import logging
import typer
import os
import urllib.parse
from typing import Dict, Any, List

# --- Setup ---
# Use Typer for a clean command-line interface
app = typer.Typer(
    help="A tool to compare two Vectara corpora and report any differences in documents."
)

# Configure logging for clear output
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# --- Helper Functions ---

def get_headers(api_key: str) -> Dict[str, str]:
    """Constructs the necessary headers for a Vectara API request."""
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "x-api-key": api_key,
    }


def get_all_document_ids(
        corpus_key: str, api_key: str, endpoint: str
) -> Dict[str, Dict[str, Any]]:
    """
    Retrieves all document IDs from a specified Vectara corpus, handling pagination using v2 API.

    Args:
        corpus_key: The key of the corpus (a string).
        api_key: The API key for authentication.
        endpoint: The Vectara API endpoint.

    Returns:
        A dictionary mapping document IDs to a basic document object (containing at least documentId).
    """
    documents: Dict[str, Dict[str, Any]] = {}
    page_key = None
    url = f"{endpoint}/v2/corpora/{corpus_key}/documents"
    headers = get_headers(api_key)

    logger.info(f"Fetching all document IDs from corpus '{corpus_key}' using v2 API...")

    while True:
        params = {"limit": 100}  # Max allowed is 100 for v2 list-documents
        if page_key:
            params["page_key"] = page_key

        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            logger.error(
                f"Failed to fetch document IDs from corpus '{corpus_key}': {e}")
            if 'response' in locals() and response:
                logger.error(f"Response body: {response.text}")
            raise

        for doc in data.get("documents", []):  # v2 uses "documents" key
            doc_id = doc.get("id")
            if not doc_id:
                logger.warning(
                    f"Skipping an entry in list from corpus '{corpus_key}' because it's missing a 'documentId'. Entry: {doc}")
                continue
            documents[doc_id] = doc  # Store the basic doc object

        page_key = data.get("next_page_key")  # v2 uses "next_page_key"
        if not page_key:
            break
        else:
            logger.info(f"Fetching next page of document IDs for corpus '{corpus_key}'...")

    logger.info(f"Found {len(documents)} document IDs in corpus '{corpus_key}'.")
    return documents


def get_document_details(
        corpus_key: str, document_id: str, api_key: str, endpoint: str
) -> Dict[str, Any]:
    """
    Retrieves full details for a specific document from a Vectara corpus using v2 API.

    Args:
        corpus_key: The key of the corpus (a string).
        document_id: The ID of the document.
        api_key: The API key for authentication.
        endpoint: The Vectara API endpoint.

    Returns:
        A dictionary containing the full document details.

    Raises:
        requests.exceptions.RequestException: If the API call fails.
        ValueError: If the API response is missing the 'document' object.
    """
    encoded_doc_id = urllib.parse.quote(document_id, safe='')
    url = f"{endpoint}/v2/corpora/{corpus_key}/documents/{encoded_doc_id}"
    headers = get_headers(api_key)
    params = {"include_parts": "true", "include_metadata": "true"}  # Request full content

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to fetch details for document {document_id} from corpus '{corpus_key}': {e}")
        if 'response' in locals() and response:
            logger.error(f"Response body: {response.text}")
        raise


def format_document_for_diff(doc: Dict[str, Any]) -> List[str]:
    """
    Formats a document's data into a sorted, pretty-printed string list for diffing.
    This creates a canonical representation to ensure that key order doesn't cause
    false positives in the diff.
    """
    # # Normalize metadata to a simple dict for consistent ordering
    # # v2 get-document still returns metadata as list of {"name": "...", "value": "..."}
    # metadata = {meta["name"]: meta["value"] for meta in doc.get("metadata", [])}
    #
    # # Combine text from all parts
    # # v2 get-document still returns parts as list of {"text": "..."}
    # text_parts = [part.get("text", "") for part in doc.get("parts", [])]
    #
    # # Create a canonical representation of the document
    # canonical_doc = {
    #     "documentId": doc.get("documentId"),
    #     "title": doc.get("title"),  # Include title from v2 response
    #     "metadata": metadata,
    #     "parts_text": text_parts,
    # }

    # Pretty-print to a list of strings (which is what difflib expects)
    return json.dumps(doc, sort_keys=True, indent=2).splitlines()


def compare_corpora(source_corpus_key: str, target_corpus_key: str, source_docs_full: Dict[str, Dict],
                    target_docs_full: Dict[str, Dict]):
    """
    Compares two sets of documents and logs the differences.
    """
    source_ids = set(source_docs_full.keys())
    target_ids = set(target_docs_full.keys())

    only_in_source = sorted(list(source_ids - target_ids))
    only_in_target = sorted(list(target_ids - source_ids))
    common_ids = sorted(list(source_ids.intersection(target_ids)))

    has_differences = False

    if only_in_source:
        has_differences = True
        logger.warning(
            f"Found {len(only_in_source)} documents in SOURCE corpus but not in target:"
        )
        for doc_id in only_in_source:
            logger.warning(f"  - Document ID: {doc_id}")

    if only_in_target:
        has_differences = True
        logger.warning(
            f"Found {len(only_in_target)} documents in TARGET corpus but not in source:"
        )
        for doc_id in only_in_target:
            logger.warning(f"  - Document ID: {doc_id}")

    logger.info(f"Comparing {len(common_ids)} common documents...")
    differences_found_in_common = 0
    for doc_id in common_ids:
        source_doc_formatted = format_document_for_diff(source_docs_full[doc_id])
        target_doc_formatted = format_document_for_diff(target_docs_full[doc_id])

        if source_doc_formatted != target_doc_formatted:
            differences_found_in_common += 1
            has_differences = True
            logger.info(f"\nDifference found for document ID: {doc_id}")

            diff = difflib.unified_diff(
                source_doc_formatted,
                target_doc_formatted,
                fromfile=f"source (corpus '{source_corpus_key}')",
                tofile=f"target (corpus '{target_corpus_key}')",
                lineterm="",
            )

            # Print the diff to the log with color for readability
            for line in diff:
                if line.startswith("+"):
                    logger.info(f"\033[92m{line}\033[0m")  # Green
                elif line.startswith("-"):
                    logger.info(f"\033[91m{line}\033[0m")  # Red
                elif line.startswith("@@"):
                    logger.info(f"\033[96m{line}\033[0m")  # Cyan
                else:
                    logger.info(line)

    if not has_differences:
        logger.info("\n✅ Success! Both corpora are identical.")
    else:
        logger.info(
            f"\nComparison finished. Found differences in {differences_found_in_common} common documents."
        )


# --- Main Command ---

@app.command()
def main(
        source_corpus: str = typer.Option(
            ..., "--source", help="The key of the source corpus (a string)."
        ),
        target_corpus: str = typer.Option(
            ..., "--target", help="The key of the target corpus (a string)."
        ),
        endpoint: str = typer.Option(
            "https://api.vectara.io", help="Vectara API endpoint."
        ),
):
    """
    Compares two Vectara corpora by fetching all documents and diffing their content and metadata.
    """
    # --- Load Credentials from Environment Variables ---
    logger.info("Loading API keys from environment variables...")
    source_api_key = os.environ.get("VECTARA_SOURCE_API_KEY")
    target_api_key = os.environ.get("VECTARA_TARGET_API_KEY")

    # --- Validate Credentials ---
    missing_vars = []
    if not source_api_key:
        missing_vars.append("VECTARA_SOURCE_API_KEY")
    if not target_api_key:
        missing_vars.append("VECTARA_TARGET_API_KEY")

    if missing_vars:
        logger.error("The following required environment variables are not set:")
        for var in missing_vars:
            logger.error(f"  - {var}")
        raise typer.Exit(code=1)

    logger.info("API keys loaded successfully.")

    try:
        # Fetch all document IDs from both corpora using their string keys
        source_doc_ids_map = get_all_document_ids(source_corpus, source_api_key, endpoint)
        target_doc_ids_map = get_all_document_ids(target_corpus, target_api_key, endpoint)

        # Now, fetch full document details for comparison
        source_documents_full: Dict[str, Dict[str, Any]] = {}
        target_documents_full: Dict[str, Dict[str, Any]] = {}

        logger.info("Fetching full document details for source corpus...")
        for doc_id in source_doc_ids_map.keys():
            doc_details = get_document_details(source_corpus, doc_id, source_api_key, endpoint)
            source_documents_full[doc_id] = doc_details

        logger.info("Fetching full document details for target corpus...")
        for doc_id in target_doc_ids_map.keys():
            doc_details = get_document_details(target_corpus, doc_id, target_api_key, endpoint)
            target_documents_full[doc_id] = doc_details

        # Compare the retrieved documents
        compare_corpora(source_corpus, target_corpus, source_documents_full, target_documents_full)

    except Exception as e:
        logger.critical(f"An unrecoverable error occurred during the comparison process: {e}")
        logger.error("Traceback:", exc_info=True)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
