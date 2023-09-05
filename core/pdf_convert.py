import logging
import subprocess
import pdfkit

class PDFConverter:
    """
    Helper class for converting web pages to PDF.
    """
    def __init__(self, use_pdfkit: bool = False):
        self.use_pdfkit = use_pdfkit

    def from_url(self, url: str, filename: str, title: str = "No Title") -> bool:
        """
        Convert a webpage to PDF and save it to a file.

        Args:
            url (str): The URL of the webpage to convert.
            filename (str): The name of the file to save the PDF to.

        Returns:
            name of file
        """
        try:
            if self.use_pdfkit:
                pdfkit.from_url(
                    url=url,
                    output_path=filename,
                    verbose=False,
                    options={'load-error-handling': 'ignore'}
                )
            else:
                cmd = ["wkhtmltopdf", "--quiet", "--load-error-handling", "ignore", '--title', title, url, filename]
                try:
                    subprocess.call(cmd, timeout=120)
                except subprocess.TimeoutExpired:
                    logging.warning(f"Timeout converting {url} to PDF")
                    return False

            return True

        except Exception as e:
            logging.error(f"Error {e} converting {url} to PDF")
            return False
        