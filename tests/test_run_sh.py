"""run.sh behaviour that no Python test covers.

Runs the real run.sh with a stubbed `docker` on PATH, so these need no Docker
daemon and never build an image or start a container. What they pin:

- Feature flags written as YAML booleans must select the right image. `.lower()`
  on a parsed bool raises AttributeError, and read_yaml_nested swallows it
  (`2>/dev/null || echo ""`), so `mask_pii: true` used to build the BASE image
  with no presidio — masking then no-opped after one log warning and the PII got
  indexed. Only a quoted "true" worked.
- A missing or misnamed `crawler_file` must stop the run. `exit` inside
  `$(get_custom_crawler_path)` only ends the subshell, so run.sh used to print
  the error and launch the container anyway with the BUILT-IN crawler.
- `summarize_tables` is not a switch: no Python reads it (`parse_tables` is the
  real one), so it must not drive the image choice either.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Prints its argv and succeeds, so run.sh's buildx probe, build, and run all
# "work" instantly and the tag it chose shows up on stdout.
DOCKER_STUB = '#!/bin/sh\necho "docker $@"\nexit 0\n'


class RunShTestCase(unittest.TestCase):

    def run_script(self, config_text, env=None, data_dir_key=None):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            bindir = tmp / "bin"
            bindir.mkdir()
            stub = bindir / "docker"
            stub.write_text(DOCKER_STUB)
            stub.chmod(0o755)

            config = tmp / "config.yaml"
            config.write_text(config_text.replace("__TMP__", str(tmp)))
            secrets = tmp / "secrets.toml"
            secrets.write_text('[default]\napi_key = "abc"\n')

            environ = {**os.environ,
                       "PATH": f"{bindir}{os.pathsep}{os.environ['PATH']}",
                       "SECRETS_FILE": str(secrets)}
            environ.update(env or {})
            return subprocess.run(["bash", "run.sh", str(config), "default"],
                                  cwd=str(REPO), capture_output=True, text=True,
                                  timeout=180, env=environ)

    @staticmethod
    def folder_config(extra_vectara="", extra_processing=""):
        return (f"vectara:\n"
                f"  corpus_key: test-corpus\n{extra_vectara}"
                f"crawling:\n"
                f"  crawler_type: folder\n"
                f"doc_processing:\n"
                f"  parse_tables: true\n{extra_processing}"
                f"folder_crawler:\n"
                f"  path: __TMP__\n"
                f"  extensions: ['.pdf']\n")

    def test_base_image_when_no_extra_features(self):
        res = self.run_script(self.folder_config())
        self.assertIn('INSTALL_EXTRA="false"', res.stdout)
        self.assertIn("vectara-ingest:latest", res.stdout)

    def test_mask_pii_yaml_boolean_selects_full_image(self):
        # `mask_pii: true`, unquoted — the form every example config uses.
        res = self.run_script(self.folder_config(extra_vectara="  mask_pii: true\n"))
        self.assertIn('INSTALL_EXTRA="true"', res.stdout)
        self.assertIn("vectara-ingest-full:latest", res.stdout)

    def test_summarize_images_yaml_boolean_selects_full_image(self):
        res = self.run_script(
            self.folder_config(extra_processing="  summarize_images: true\n"))
        self.assertIn('INSTALL_EXTRA="true"', res.stdout)
        self.assertIn("vectara-ingest-full:latest", res.stdout)

    def test_quoted_true_still_works(self):
        res = self.run_script(self.folder_config(extra_vectara='  mask_pii: "true"\n'))
        self.assertIn('INSTALL_EXTRA="true"', res.stdout)

    def test_summarize_tables_does_not_select_full_image(self):
        # Not a real switch — no Python reads it; parse_tables is the one that
        # drives table extraction and summarization.
        res = self.run_script(
            self.folder_config(extra_processing="  summarize_tables: true\n"))
        self.assertIn('INSTALL_EXTRA="false"', res.stdout)

    def test_download_docling_models_uses_onprem_tag(self):
        res = self.run_script(self.folder_config(),
                              env={"DOWNLOAD_DOCLING_MODELS": "true"})
        self.assertIn("latest.onprem", res.stdout)
        self.assertIn("--build-arg DOWNLOAD_DOCLING_MODELS=true", res.stdout)

    def test_missing_custom_crawler_aborts(self):
        res = self.run_script(
            self.folder_config(extra_vectara="  crawler_file: /nonexistent/folder_crawler.py\n"))
        self.assertEqual(res.returncode, 9, res.stdout + res.stderr)
        # The real damage was continuing past the error with the built-in crawler.
        self.assertNotIn("Running docker:", res.stdout)

    def test_misnamed_custom_crawler_aborts(self):
        with tempfile.TemporaryDirectory() as crawler_dir:
            wrong = Path(crawler_dir) / "wrong_crawler.py"
            wrong.write_text("class WrongCrawler(Crawler):\n    pass\n")
            res = self.run_script(
                self.folder_config(extra_vectara=f"  crawler_file: {wrong}\n"))
        self.assertEqual(res.returncode, 10, res.stdout + res.stderr)
        self.assertNotIn("Running docker:", res.stdout)


if __name__ == "__main__":
    unittest.main()
