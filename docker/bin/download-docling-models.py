import sys
from pathlib import Path

# Redirect print output to stderr
sys.stdout = sys.stderr

from docling.datamodel.layout_model_specs import DOCLING_LAYOUT_HERON_101, DOCLING_LAYOUT_V2
from docling.models.stages.layout.layout_model import LayoutModel
from docling.utils.model_downloader import download_models

# Must match DOCLING_ARTIFACTS_PATH in core/doc_parser.py. Deliberately NOT read
# from a DOCLING_ARTIFACTS_PATH env var: docling's own pydantic-settings config
# (docling.datamodel.settings.AppSettings, env_prefix="DOCLING_") already binds
# that exact env var name as a global artifacts_path fallback used by every
# pipeline. Setting it would make docling require this folder to exist even on
# images that never ran this script, breaking default (non-baked) image builds.
output_dir = Path("/opt/docling-models")

# Bakes the default layout model (heron), TableFormer, and CodeFormula — the
# models core/doc_parser.py's default pipeline always reaches (table structure
# extraction is unconditional) or can reach via docling_config.do_formula_enrichment.
# Explicitly excludes picture_classifier/rapidocr/easyocr/VLM/ASR models: no code
# path in this repo invokes them, and RapidOCR/EasyOCR aren't HF-hosted anyway
# (see docker/bin/download-easyocr-models.py for the EasyOCR equivalent).
download_models(
    output_dir=output_dir,
    with_layout=True,
    with_tableformer=True,
    with_code_formula=True,
    with_picture_classifier=False,
    with_rapidocr=False,
    with_easyocr=False,
)

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
