import unittest
import tempfile

from core.utils import get_file_size_in_MB
class TestUtils(unittest.TestCase):
    def test_get_file_size_in_MB(self):
        file_size=2 * 1024 * 1024
        with tempfile.TemporaryFile() as fp:
            buffer = bytearray(file_size)
            fp.write(buffer)
            fp.flush()
            actual = get_file_size_in_MB(fp.name)
            self.assertEqual(2.0, actual)

    def test_get_file_size_in_MB_zero_byte_file(self):
        with tempfile.TemporaryFile() as fp:
            fp.flush()
            actual = get_file_size_in_MB(fp.name)
            self.assertEqual(0, actual)