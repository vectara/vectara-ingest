"""Text that Docling nests inside a picture must be indexed.

Docling's layout model can classify a whole PDF page as one picture (CAD
drawings, schematics, full-page scans with a text layer). The page's text
cells are then children of that PictureItem. DoclingDocument.iterate_items()
and the chunkers skip picture children unless traverse_pictures=True, so the
text was dropped: only the vision summary of the page reached the index.
"""
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.modules['cairosvg'] = MagicMock()

from docling_core.types.doc import (  # noqa: E402
    BoundingBox, DocItemLabel, DoclingDocument, ImageRef, ProvenanceItem, Size,
)
from omegaconf import OmegaConf  # noqa: E402
from PIL import Image  # noqa: E402

from core.doc_parser import DoclingDocumentParser  # noqa: E402

PICTURE_TEXT = ["1.375", "(DIMENSION A)", "Insulator: Liq. Crystal Polymer"]


def _prov(page_no, text=""):
    return ProvenanceItem(page_no=page_no, bbox=BoundingBox(l=0, t=0, r=10, b=10),
                          charspan=(0, len(text)))


def make_doc():
    """Page 1: one picture holding the page's text. Page 2: plain text."""
    doc = DoclingDocument(name="drawing")
    for page_no in (1, 2):
        doc.add_page(page_no=page_no, size=Size(width=200, height=200))
    image = ImageRef.from_pil(Image.new("RGB", (200, 200), "white"), dpi=72)
    picture = doc.add_picture(image=image, prov=_prov(1))
    for text in PICTURE_TEXT:
        doc.add_text(label=DocItemLabel.TEXT, text=text, parent=picture, prov=_prov(1, text))
    doc.add_text(label=DocItemLabel.TEXT, text="SUGGESTED MATING CONNECTORS", prov=_prov(2))
    return doc


def make_parser(chunking_strategy, summarize_images=False):
    cfg = OmegaConf.create({"vectara": {"verbose": False}, "doc_processing": {}})
    return DoclingDocumentParser(
        cfg=cfg, verbose=False, model_config={}, parse_tables=False, enable_gmft=False,
        do_ocr=False, summarize_images=summarize_images, chunking_strategy=chunking_strategy,
        chunk_size=1024, image_scale=1.0,
        image_context={'num_previous_chunks': 1, 'num_next_chunks': 1},
    )


def parse(parser, doc):
    converter = MagicMock()
    converter.convert.return_value.document = doc
    with patch.object(parser, '_get_pdf_page_count', return_value=2), \
         patch('core.doc_parser.extract_document_title', return_value='drawing'):
        return parser._parse_with_converter('/tmp/drawing.pdf', 'file:///drawing.pdf', converter)


def page_text(parsed, page):
    return "\n".join(text for text, meta in parsed.get_texts() if meta.get('page') == page)


class TestPictureTextIsIndexed(unittest.TestCase):

    def test_each_chunking_strategy_keeps_picture_text_on_its_page(self):
        for strategy in ('none', 'hierarchical', 'hybrid'):
            with self.subTest(strategy=strategy):
                parsed = parse(make_parser(strategy), make_doc())
                for text in PICTURE_TEXT:
                    self.assertIn(text, page_text(parsed, 1))
                # The hybrid chunker merges small peers across pages, so page 2's
                # line may share page 1's chunk; it must still be indexed.
                all_text = "\n".join(text for text, _ in parsed.get_texts())
                self.assertIn("SUGGESTED MATING CONNECTORS", all_text)

    def test_picture_text_is_given_to_the_image_summarizer(self):
        parser = make_parser('hybrid', summarize_images=True)
        parser.image_summarizer = MagicMock()
        parser.image_summarizer.summarize_image.return_value = "A drawing sheet."
        parsed = parse(parser, make_doc())

        kwargs = parser.image_summarizer.summarize_image.call_args.kwargs
        self.assertEqual(kwargs['image_text'], "\n".join(PICTURE_TEXT))
        self.assertIn(("A drawing sheet.", 1),
                      [(text, meta['page']) for text, meta in parsed.get_images()])


class TestSummarizerPrompt(unittest.TestCase):

    def test_image_text_is_in_the_prompt(self):
        from core.summary import ImageSummarizer
        summarizer = ImageSummarizer.__new__(ImageSummarizer)
        summarizer.cfg, summarizer.image_model_config = MagicMock(), {}
        with patch('core.summary._get_image_shape', return_value=(200, 200)), \
             patch('core.summary.generate_image_summary', return_value="ok") as generate:
            summarizer.summarize_image('', 'url', image_bytes=b'png', image_text="1.375\n[34,93]")
        prompt = generate.call_args.args[1]
        self.assertIn("1.375\n[34,93]", prompt)


if __name__ == '__main__':
    unittest.main()
