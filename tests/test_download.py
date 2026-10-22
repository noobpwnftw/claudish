import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "download_model", Path(__file__).resolve().parents[1] / "scripts" / "download_model.py")
download_model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(download_model)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.data = b"GGUF" + bytes(range(256)) * 9000
        self.source = self.root / "source.gguf"
        self.source.write_bytes(self.data)
        self.url = self.source.as_uri()
        self.digest = hashlib.sha256(self.data).hexdigest()
        self.target = self.root / "models" / "model.gguf"

    def tearDown(self):
        self.directory.cleanup()

    def test_verified_download_then_skip(self):
        self.assertTrue(download_model.download(self.url, self.target, len(self.data), self.digest))
        self.assertEqual(self.target.read_bytes(), self.data)
        self.source.unlink()  # A verified model must not be fetched again.
        self.assertFalse(download_model.download(self.url, self.target, len(self.data), self.digest))

    def test_corrupt_or_truncated_download_leaves_nothing_behind(self):
        for size, digest in [(len(self.data), "0" * 64), (len(self.data) + 1, self.digest)]:
            with self.assertRaisesRegex(ValueError, "verification"):
                download_model.download(self.url, self.target, size, digest)
            self.assertEqual(list(self.target.parent.iterdir()), [])

    def test_mismatched_existing_file_is_not_overwritten(self):
        self.target.parent.mkdir()
        self.target.write_bytes(b"someone else's model")
        with self.assertRaisesRegex(ValueError, "move it aside"):
            download_model.download(self.url, self.target, len(self.data), self.digest)
        self.assertEqual(self.target.read_bytes(), b"someone else's model")

    def test_presets_are_pinned(self):
        for repo, revision, filename, size, digest in download_model.PRESETS.values():
            self.assertRegex(revision, "^[0-9a-f]{40}$")
            self.assertRegex(digest, "^[0-9a-f]{64}$")
            self.assertTrue(filename.endswith(".gguf") and size > 0)


if __name__ == "__main__":
    unittest.main()
