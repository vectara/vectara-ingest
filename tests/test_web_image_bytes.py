"""Regression: web image binary must be stored as a renderable raster.

SVG web images were stored as raw SVG bytes but labeled image/png (the MIME
sniffer's default fallback), so the corpus UI could not render them. The binary
for an SVG must be routed through cairosvg to a rasterized PNG; raster images
pass through unchanged.

cairosvg needs the native libcairo (present in the Docker image, absent in most
local envs), so it is stubbed here — the real rasterization is covered by the
end-to-end Docker run. These tests assert the branching logic: SVG goes through
svg2png, raster is read as-is.
"""
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

PNG_MAGIC = b'\x89PNG\r\n\x1a\n'
# A minimal valid 1x1 PNG, used as the stubbed svg2png output and the raster input.
_TINY_PNG = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc````'
    b'\x00\x00\x00\x05\x00\x01\xa5\xf6E@\x00\x00\x00\x00IEND\xaeB`\x82'
)

# Stub cairosvg (no libcairo locally); svg2png returns known PNG bytes.
_cairosvg_stub = MagicMock()
_cairosvg_stub.svg2png.return_value = _TINY_PNG
sys.modules['cairosvg'] = _cairosvg_stub

from core.image_processor import ImageProcessor
from core.indexer import Indexer


class TestReadRenderableImageBytes(unittest.TestCase):
    def test_svg_is_routed_through_rasterizer(self):
        with tempfile.NamedTemporaryFile(suffix='.svg', delete=False, mode='w') as f:
            f.write('<svg xmlns="http://www.w3.org/2000/svg"/>')
            svg_path = f.name
        data = ImageProcessor._read_renderable_image_bytes(svg_path, is_svg=True)
        _cairosvg_stub.svg2png.assert_called_once_with(url=svg_path)
        self.assertTrue(data.startswith(PNG_MAGIC),
                        "SVG must be stored as rasterized PNG bytes")
        # The MIME sniffer now agrees it is a PNG (previously defaulted to png over SVG bytes).
        self.assertEqual(
            Indexer._detect_image_mime_type(Indexer.__new__(Indexer), "web_x_image_0", data),
            "image/png")

    def test_raster_passes_through_unchanged(self):
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            f.write(_TINY_PNG)
            png_path = f.name
        data = ImageProcessor._read_renderable_image_bytes(png_path, is_svg=False)
        self.assertEqual(data, _TINY_PNG)


if __name__ == "__main__":
    unittest.main()
