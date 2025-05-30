from easyocr import config
from easyocr.utils import download_and_unzip
import os.path
import sys

# Redirect print output to stderr
sys.stdout = sys.stderr

model_storage_directory=os.path.expanduser("~/.EasyOCR/")
os.makedirs(model_storage_directory, exist_ok=True)
verbose=False

def download_models(models: dict):
    print(f"Download {len(models)} EasyOCR model(s)")
    for model_name, model in models.items():
        print(f"  Downloading {model['url']}")
        download_and_unzip(model['url'], model['filename'], model_storage_directory, verbose)

download_models(config.detection_models)
generations = ['gen1', 'gen2']
for generation in generations:
    models = config.recognition_models.get(generation, {})
    download_models(models)