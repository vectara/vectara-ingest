"""
Multi-page image detection and stitching for document processing.

This module provides functionality to detect images that span multiple pages
in PDF documents and stitch them together into a single coherent image.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any
from PIL import Image
import numpy as np

logger = logging.getLogger(__name__)

# Caption indicators for detecting figure captions
CAPTION_INDICATORS = frozenset(['figure', 'fig.', 'fig', 'table', 'diagram', 'drawing', 'image', 'photo'])


@dataclass
class ImageFragment:
    """
    Represents a single image fragment extracted from a document page.

    Attributes:
        image: PIL Image object
        page_num: Page number where image was found (1-indexed)
        bbox: Bounding box coordinates (left, top, right, bottom) in page coordinate system
        position: Position index in document element order
        width: Image width in points
        height: Image height in points
        page_height: Height of the page in points
        page_width: Width of the page in points
        is_last_on_page: Whether this is the last element on its page
        is_first_on_page: Whether this is the first element on its page
        next_text: Text of the next element on the same page (for caption detection)
    """
    image: Image.Image
    page_num: int
    bbox: Optional[Tuple[float, float, float, float]]
    position: int
    width: float
    height: float
    page_height: float
    page_width: float
    is_last_on_page: bool = False
    is_first_on_page: bool = False
    next_text: Optional[str] = None

    def horizontal_alignment(self) -> float:
        """Get horizontal (x) alignment of the image."""
        return self.bbox[0] if self.bbox else 0.0


@dataclass
class StitchConfig:
    """
    Configuration for multi-page image stitching.

    Attributes:
        enabled: Whether multi-page stitching is enabled
        width_tolerance_pct: Percentage tolerance for width matching (default 15%)
        alignment_tolerance_pts: Tolerance for horizontal alignment in points (default 50)
        min_overlap_pixels: Minimum overlap in pixels to detect (default 10)
        max_pages_to_stitch: Maximum number of pages to stitch together (default 2)
    """
    enabled: bool = True
    width_tolerance_pct: float = 15.0
    alignment_tolerance_pts: float = 50.0
    min_overlap_pixels: int = 10
    max_pages_to_stitch: int = 2


class MultiPageImageStitcher:
    """
    Detects and stitches images that span multiple pages in documents.
    """

    def __init__(self, config: Optional[StitchConfig] = None):
        """
        Initialize the stitcher with configuration.

        Args:
            config: Stitching configuration, uses defaults if None
        """
        self.config = config or StitchConfig()

    def detect_split_images(self, fragments: List[ImageFragment]) -> List[List[int]]:
        """
        Detect which image fragments should be stitched together.

        Args:
            fragments: List of ImageFragment objects in document order

        Returns:
            List of groups, where each group is a list of fragment indices that should be stitched
        """
        if not self.config.enabled or len(fragments) < 2:
            return []

        groups = []
        sorted_fragments = sorted(enumerate(fragments), key=lambda x: (x[1].page_num, x[1].position))

        i = 0
        while i < len(sorted_fragments) - 1:
            idx1, frag1 = sorted_fragments[i]
            idx2, frag2 = sorted_fragments[i + 1]

            # Check if on consecutive pages
            if frag2.page_num == frag1.page_num + 1 and self._should_stitch(frag1, frag2):
                group = [idx1, idx2]

                # Look ahead for more fragments in the sequence (up to max_pages_to_stitch)
                j = i + 2
                while j < len(sorted_fragments) and len(group) < self.config.max_pages_to_stitch:
                    idx_next, frag_next = sorted_fragments[j]
                    idx_prev, frag_prev = sorted_fragments[j - 1]

                    if frag_next.page_num == frag_prev.page_num + 1 and self._should_stitch(frag_prev, frag_next):
                        group.append(idx_next)
                        j += 1
                    else:
                        break

                groups.append(group)
                i = j  # Skip past all fragments in this group
                continue

            i += 1

        return groups

    def _should_stitch(self, frag1: ImageFragment, frag2: ImageFragment) -> bool:
        """
        Determine if two fragments should be stitched together using multi-signal approach.

        Args:
            frag1: First fragment (earlier page)
            frag2: Second fragment (later page)

        Returns:
            True if fragments should be stitched
        """
        # Calculate width difference
        width_diff = abs(frag1.width - frag2.width) / max(frag1.width, frag2.width)

        # Caption detection: Check if image is followed by caption text
        if frag1.next_text and len(frag1.next_text.strip()) < 200:
            caption_lower = frag1.next_text.lower()
            has_caption = any(indicator in caption_lower for indicator in CAPTION_INDICATORS)

            if has_caption and frag2.is_first_on_page and width_diff < 0.25:
                logger.info(f"Caption match: pages {frag1.page_num}->{frag2.page_num}")
                return True

        # Positional continuity check
        positional_match = frag1.is_last_on_page and frag2.is_first_on_page
        if not positional_match:
            return False

        # Visual similarity checks
        widths_similar = width_diff < (self.config.width_tolerance_pct / 100.0)

        # Strong match: positional + width + alignment
        if widths_similar:
            alignment_diff = abs(frag1.horizontal_alignment() - frag2.horizontal_alignment())
            if alignment_diff < self.config.alignment_tolerance_pts:
                logger.info(f"Strong match: pages {frag1.page_num}->{frag2.page_num}")
                return True

            # Medium match: positional + width only
            logger.info(f"Medium match: pages {frag1.page_num}->{frag2.page_num}")
            return True

        # Lenient match: Full-page diagrams (both first and last on their pages)
        only_content = frag1.is_first_on_page and frag1.is_last_on_page and \
                       frag2.is_first_on_page and frag2.is_last_on_page

        if only_content and width_diff < 0.25:
            logger.info(f"Lenient match: pages {frag1.page_num}->{frag2.page_num}")
            return True

        return False

    def stitch_vertical(
        self,
        fragments: List[ImageFragment],
        detect_overlap: bool = True
    ) -> Tuple[Image.Image, Dict[str, Any]]:
        """
        Stitch multiple image fragments vertically.

        Args:
            fragments: List of ImageFragment objects to stitch (in order)
            detect_overlap: Whether to attempt overlap detection

        Returns:
            Tuple of (stitched PIL Image, metadata dict)
        """
        if not fragments:
            raise ValueError("Cannot stitch empty fragment list")

        if len(fragments) == 1:
            return fragments[0].image, {'pages': [fragments[0].page_num], 'overlap_detected': False}

        # Sort by page number to ensure correct order
        fragments = sorted(fragments, key=lambda f: f.page_num)
        images = [f.image for f in fragments]
        pages = [f.page_num for f in fragments]

        # Detect overlap if requested
        overlap_pixels = self._detect_overlap(images[0], images[1]) if detect_overlap and len(images) >= 2 else 0

        # Calculate dimensions
        max_width = max(img.width for img in images)
        total_height = sum(img.height for img in images) - overlap_pixels * (len(images) - 1) if overlap_pixels > 0 else sum(img.height for img in images)

        # Create and populate stitched image
        stitched = Image.new('RGB', (max_width, total_height), color='white')
        y_offset = 0

        for i, img in enumerate(images):
            x_offset = (max_width - img.width) // 2  # Center horizontally
            if i > 0 and overlap_pixels > 0:
                y_offset -= overlap_pixels
            stitched.paste(img, (x_offset, y_offset))
            y_offset += img.height

        metadata = {
            'pages': pages,
            'overlap_detected': overlap_pixels > 0,
            'overlap_pixels': overlap_pixels,
            'original_heights': [img.height for img in images],
            'stitched_size': (max_width, total_height)
        }

        logger.info(f"Stitched {len(fragments)} pages {pages[0]}-{pages[-1]}: {max_width}x{total_height}px")
        return stitched, metadata

    def _detect_overlap(self, img1: Image.Image, img2: Image.Image) -> int:
        """
        Detect overlap between bottom of img1 and top of img2.

        Args:
            img1: First image
            img2: Second image

        Returns:
            Number of overlapping pixels, or 0 if no overlap detected
        """
        try:
            arr1 = np.array(img1)
            arr2 = np.array(img2)

            # Only check if images have similar widths (within 10%)
            min_width = min(arr1.shape[1], arr2.shape[1])
            if abs(arr1.shape[1] - arr2.shape[1]) > min_width * 0.1:
                return 0

            # Search bottom of img1 against top of img2 (up to 200 pixels)
            max_search = min(arr1.shape[0], arr2.shape[0], 200)
            best_overlap = 0
            best_score = float('inf')

            for overlap in range(self.config.min_overlap_pixels, max_search):
                bottom_slice = arr1[-overlap:, :min_width]
                top_slice = arr2[:overlap, :min_width]
                diff = np.mean(np.abs(bottom_slice.astype(float) - top_slice.astype(float)))

                if diff < best_score:
                    best_score = diff
                    best_overlap = overlap

                # Early exit if difference is very small
                if diff < 10.0:
                    return overlap

            # Return best overlap if score is reasonable
            if best_score < 50.0 and best_overlap > self.config.min_overlap_pixels:
                return best_overlap

        except Exception as e:
            logger.warning(f"Overlap detection failed: {e}")

        return 0

    def process_fragments(
        self,
        fragments: List[ImageFragment]
    ) -> Tuple[List[ImageFragment], List[Tuple[Image.Image, Dict[str, Any], List[int]]]]:
        """
        Process fragments, detecting and stitching multi-page images.

        Args:
            fragments: List of all image fragments

        Returns:
            Tuple of:
            - List of remaining single-page fragments (not stitched)
            - List of (stitched_image, metadata, fragment_indices) for stitched images
        """
        if not self.config.enabled:
            return fragments, []

        stitch_groups = self.detect_split_images(fragments)

        if not stitch_groups:
            return fragments, []

        logger.info(f"Detected {len(stitch_groups)} multi-page image group(s)")

        # Track which fragments are used in stitching
        stitched_indices = set()
        for group in stitch_groups:
            stitched_indices.update(group)

        # Separate stitched and single fragments
        single_fragments = [f for i, f in enumerate(fragments) if i not in stitched_indices]

        # Stitch the groups
        stitched_results = [
            (*self.stitch_vertical([fragments[i] for i in group]), group)
            for group in stitch_groups
        ]

        return single_fragments, stitched_results
