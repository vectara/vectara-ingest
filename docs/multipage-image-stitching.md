# Multi-Page Image Stitching

## Overview

The multi-page image stitching feature automatically detects and combines images or diagrams that span multiple pages in PDF documents. This is common in technical documentation where large diagrams, flow charts, or dimensional drawings are split across consecutive pages.

## How It Works

The system uses a multi-signal approach to detect when images should be stitched together:

### Detection Signals

1. **Caption Detection**
   - Detects figure captions after images (e.g., "Figure 3-1", "Table 2-1")
   - Checks if the next page starts with an image and has similar width
   - Handles continued figures like "Figure 3-1 (cont)" across pages

2. **Positional Continuity**
   - Checks if image is the last element on one page
   - Checks if next image is the first element on the following page
   - Excludes headers and footers from consideration

3. **Visual Similarity**
   - **Strong match**: Similar width (±15%) + horizontal alignment (±50 points)
   - **Medium match**: Similar width (±15%) only
   - **Lenient match**: Full-page diagrams (both first and last on page) with ±25% width tolerance

### Filters

- **Page limit**: Maximum 2 consecutive pages stitched together (configurable)

### Overlap Detection

When stitching images, the system:
1. Searches for overlapping pixels between the bottom of the first image and top of the second
2. Removes duplicate overlapping regions when found
3. Seamlessly combines images vertically

## Configuration

### Parser Support

**Currently supported**: Docling parser only
**Not supported**: Unstructured parser (implementation reverted)

To use this feature, you must set:
```yaml
doc_processing:
  doc_parser: docling
  summarize_images: true
```

### Stitching Configuration

```yaml
doc_processing:
  multipage_image_stitching:
    enabled: true                # Enable/disable the feature
    max_pages_to_stitch: 2       # Maximum consecutive pages to stitch
    width_tolerance_pct: 15.0    # Width matching tolerance (default: 15%)
    alignment_tolerance_pts: 50.0 # Horizontal alignment tolerance in points
    min_overlap_pixels: 10       # Minimum overlap to detect (default: 10)
```

## Examples

### Use Case 1: Figure with Caption
```
Page 1: [Large diagram]
        "Figure 3-1. System Architecture"
Page 2: [Continuation of diagram]
```
**Result**: Stitched together as single image

### Use Case 2: Positional Continuity
```
Page 1: Text content
        [Bottom: Large flow diagram (part 1)]
Page 2: [Top: Large flow diagram (part 2)]
        Text content
```
**Result**: Stitched together based on positional continuity

### Use Case 3: Different Figures (NOT stitched)
```
Page 1: [Diagram]
        "Figure 1-1. Component A"
Page 2: [Diagram]
        "Figure 1-2. Component B"
```
**Result**: Kept as separate images (different figure numbers)

## Configuration Examples

See the example configuration file:
- `config/folder-ingest-image-stitch.yaml`

## Technical Details

### Image Metadata

Stitched images include metadata:
- `is_multipage: true`
- `pages: [44, 45]` - List of source page numbers
- `overlap_detected: true/false`
- `overlap_pixels: N` - Number of overlapping pixels removed

### Performance Considerations

- Stitching happens before image summarization
- Context is extracted from the first fragment's position
- Image IDs use format: `docling_stitched_pages_44_45`

## Troubleshooting

### Images not being stitched

1. **Check page limit**: Only 2 consecutive pages by default
2. **Check width difference**: Must be within 15-25% depending on match type
3. **Enable logging**: Set verbose mode to see detection details

### Too many images being stitched

1. **Reduce width tolerance**: Lower `width_tolerance_pct` (e.g., to 10%)
2. **Reduce page limit**: Set `max_pages_to_stitch` to 2 (if higher)
3. **Disable lenient matching**: This would require code modification

### Stitching quality issues

1. **Check overlap detection**: Look for `overlap_detected` in metadata
2. **Verify alignment**: Images should have similar horizontal alignment
3. **Review source images**: Some multi-page images may have intentional gaps

## Logging

When verbose mode is enabled, you'll see:
- `Caption match: pages X->Y`
- `Strong match: pages X->Y`
- `Medium match: pages X->Y`
- `Lenient match: pages X->Y`
- `Detected N multi-page image group(s)`
- `Stitched N pages X-Y: WxH pixels`

## Implementation Files

- `core/image_stitcher.py` - Core stitching logic
- `core/doc_parser.py` - Integration with Docling parser
- `core/file_processor.py` - Configuration loading
