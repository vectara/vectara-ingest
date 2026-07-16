import sys
from pathlib import Path

# Redirect print output to stderr
sys.stdout = sys.stderr

from docling.datamodel.layout_model_specs import DOCLING_LAYOUT_HERON_101, DOCLING_LAYOUT_V2
from docling.models.stages.layout.layout_model import LayoutModel
from docling.utils.model_downloader import download_models
from easyocr import config as easyocr_config
from easyocr.utils import download_and_unzip

# Must match DOCLING_ARTIFACTS_PATH in core/doc_parser.py. Deliberately NOT read
# from a DOCLING_ARTIFACTS_PATH env var: docling's own pydantic-settings config
# (docling.datamodel.settings.AppSettings, env_prefix="DOCLING_") already binds
# that exact env var name as a global artifacts_path fallback used by every
# pipeline. Setting it would make docling require this folder to exist even on
# images that never ran this script, breaking default (non-baked) image builds.
output_dir = Path("/opt/docling-models")

# Bakes the default layout model (heron), TableFormer, and CodeFormula — the models
# core/doc_parser.py's default pipeline always reaches (table structure extraction is
# unconditional) or can reach via docling_config.do_formula_enrichment.
# Excludes picture_classifier/rapidocr/VLM/ASR: no code path in this repo uses them.
# EasyOCR is baked separately below, via EasyOCR's own downloader.
download_models(
    output_dir=output_dir,
    with_layout=True,
    with_tableformer=True,
    with_code_formula=True,
    with_easyocr=False,
    with_picture_classifier=False,
    with_rapidocr=False,
)

# EasyOCR models for OCR (do_ocr / fallback_ocr). Fetched with EasyOCR's own downloader
# (not docling's) so this doesn't depend on docling's internal module layout, which moves
# between versions. They must land in {output_dir}/EasyOcr/ specifically: once doc_parser.py
# sets pdf_opts.artifacts_path (which it does whenever these models are baked), docling forces
# EasyOCR to load from {artifacts_path}/EasyOcr/ with downloads disabled — the exact folder and
# the FileNotFoundError this fixes. Recognition models are per-script, not per-language; the
# runtime script is chosen by easy_ocr_config.lang. We bake the scripts covering the world's
# most-used languages, and selecting an unbaked script fails offline.
easyocr_dir = output_dir / "EasyOcr"
easyocr_dir.mkdir(parents=True, exist_ok=True)

# craft detector (shared) + gen2 recognizers (~15-20MB each) covering, by script family:
# Latin (en/fr/de/es/it/pt/nl/... ), Simplified Chinese, Japanese, Korean, Cyrillic (ru/uk/bg).
# Plus gen1-only scripts (~190MB each, heavier architecture): Devanagari (Hindi), Arabic
# (Arabic/Urdu), Bengali. Each unzips to the exact .pth name (craft_mlt_25k.pth, latin_g2.pth,
# arabic.pth, ...) the runtime requests for that script.
easyocr_models = [easyocr_config.detection_models["craft"]]
easyocr_models += [easyocr_config.recognition_models["gen2"][k] for k in
                   ("english_g2", "latin_g2", "zh_sim_g2", "japanese_g2", "korean_g2", "cyrillic_g2")]
easyocr_models += [easyocr_config.recognition_models["gen1"][k] for k in
                   ("devanagari_g1", "arabic_g1", "bengali_g1")]
for model in easyocr_models:
    print(f"Downloading EasyOCR model {model['filename']}...")
    download_and_unzip(model["url"], model["filename"], str(easyocr_dir), verbose=False)

# core/doc_parser.py's docling_config.layout_model also allows selecting these
# alternate layout variants at runtime. Bake them too so switching configs never
# needs a rebuild or hits docling's hard-fail-on-missing-artifacts behavior.
for layout_config in (DOCLING_LAYOUT_HERON_101, DOCLING_LAYOUT_V2):
    print(f"Downloading layout model {layout_config.repo_id}...")
    LayoutModel.download_models(
        local_dir=output_dir / layout_config.model_repo_folder,
        layout_model_config=layout_config,
    )

print(f"Docling models downloaded to {output_dir}")
