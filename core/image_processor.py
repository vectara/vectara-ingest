import logging
import os
import requests
from typing import List, Dict, Any, Tuple
from omegaconf import OmegaConf
from slugify import slugify
from core.summary import ImageSummarizer
from core.utils import get_headers

import base64
import mimetypes
import tempfile
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

class ImageProcessor:
    """Handles image processing and summarization"""
    
    def __init__(self, cfg: OmegaConf, model_config: Dict[str, Any], verbose: bool = False):
        self.cfg = cfg
        self.model_config = model_config
        self.verbose = verbose
        self.image_summarizer = None
        
    def _get_image_summarizer(self):
        """Lazy initialization of image summarizer"""
        if self.image_summarizer is None:
            if 'vision' not in self.model_config:
                logger.warning("Image summarization enabled but no vision model configured")
                return None
            
            self.image_summarizer = ImageSummarizer(
                cfg=self.cfg,
                image_model_config=self.model_config['vision']
            )
        return self.image_summarizer
    
    def process_web_images(self, images: List[Dict[str, str]], url: str, ex_metadata: Dict[str, Any]) -> Tuple[List[Tuple[str, str, Dict[str, Any]]], List[Tuple[str, bytes]]]:
        """
        Process images from web pages
        
        Args:
            images: List of image dictionaries with 'src' and 'alt' keys
            url: Source URL
            ex_metadata: Extra metadata to add to each image
            
        Returns:
            Tuple of (processed_images, image_bytes) where:
            - processed_images: List of (doc_id, image_summary, metadata) tuples
            - image_bytes: List of (image_id, binary_data) tuples
        """
        if not images:
            return [], []
        
        image_summarizer = self._get_image_summarizer()
        if not image_summarizer:
            return [], []
        
        if self.verbose:
            logger.info(f"Found {len(images)} images in {url}")
        
        processed_images = []
        image_bytes = []
        image_filename = 'image.png'
        
        for inx, image in enumerate(images):
            try:
                image_url = image['src']

                if image_url.startswith('data:image/'):
                    header, payload = image_url.split(',', 1)
                    # header will be like "data:image/svg+xml;base64"
                    mime = header.split(';')[0].split(':')[1]  # e.g. "image/svg+xml"
                    ext = mimetypes.guess_extension(mime) or '.bin'
                    # write to a temp file
                    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                        tmp.write(base64.b64decode(payload))
                        tmp_filename = tmp.name
                    local_path = tmp_filename

                elif image_url.startswith('http'):
                    # download as before
                    response = requests.get(image_url, headers=get_headers(self.cfg), stream=True)
                    if response.status_code != 200:
                        logger.info(f"Failed to retrieve image {image_url} from {url}, skipping")
                        continue
                    # write to a temp file with appropriate extension guessed from URL path or default to .png
                    url_path = urlparse(image_url).path
                    ext = os.path.splitext(url_path)[1] or '.png'
                    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
                        for chunk in response.iter_content(chunk_size=8192):
                            tmp.write(chunk)
                        local_path = tmp.name

                else:
                    logger.info(f"Image URL '{image_url}' is not valid, skipping")
                    continue

                # Store binary data
                with open(local_path, 'rb') as fp:
                    image_binary = fp.read()
                image_id = f"web_{slugify(url)}_image_{inx}"
                image_bytes.append((image_id, image_binary))
                
                # Generate summary from local_path
                image_summary = image_summarizer.summarize_image(local_path, image_url, None)
                if not image_summary:
                    logger.info(f"Failed to generate summary for image {image_url}")
                    continue
                
                # Prepare metadata
                metadata = {
                    'element_type': 'image',
                    'url': image_url,
                    'alt_text': image.get('alt', ''),
                    'image_id': image_id
                }
                if ex_metadata:
                    metadata.update(ex_metadata)
                
                if self.verbose:
                    logger.info(f"Image summary: {image_summary[:500]}...")
                
                # Generate document ID
                doc_id = slugify(url) + "_image_" + str(inx)
                
                processed_images.append((doc_id, image_summary, metadata))
                
            except Exception as e:
                logger.warning(f"Failed to process image {image.get('src', 'unknown')}: {e}")
                continue

            finally:
                # Clean up temporary file
                if 'local_path' in locals() and os.path.exists(local_path):
                    os.remove(local_path)

        return processed_images, image_bytes
    
    def process_document_images(self, images: List[tuple], uri: str, ex_metadata: Dict[str, Any]) -> List[Tuple[str, str, Dict[str, Any]]]:
        """
        Process images from document parser (images already have summaries and metadata)
        
        Args:
            images: List of (image_summary, image_metadata) tuples
            uri: Source URI
            ex_metadata: Extra metadata to add to each image
            
        Returns:
            List of (doc_id, image_summary, metadata) tuples
            
        Note: This method processes pre-summarized images from document parsers.
        Binary data is handled separately via ParsedDocument.image_bytes field.
        """
        if not images:
            return []
        
        if self.verbose:
            logger.info(f"Processing {len(images)} images from {uri}")
        
        processed_images = []
        
        for inx, (image_summary, image_metadata) in enumerate(images):
            try:
                # Prepare metadata
                metadata = image_metadata.copy()
                metadata['url'] = uri
                if ex_metadata:
                    metadata.update(ex_metadata)
                
                # Generate document ID
                doc_id = slugify(uri) + "_image_" + str(inx)
                
                processed_images.append((doc_id, image_summary, metadata))
                
            except Exception as e:
                logger.warning(f"Failed to process document image {inx}: {e}")
                continue
        
        return processed_images
    
    def log_processing_summary(self, filename: str, image_count: int, success_count: int):
        """Log image processing summary"""
        if image_count > 0:
            logger.info(f"Indexed {image_count} images from {filename} with {success_count} successes")