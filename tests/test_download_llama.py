import hashlib
import io
import shutil
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import download_llama  # noqa: E402


def tar_with(path, members):
    """members: [(name, bytes | ("symlink", target))]"""
    with tarfile.open(path, "w:gz") as bundle:
        for name, content in members:
            info = tarfile.TarInfo(name)
            if isinstance(content, tuple):
                info.type, info.linkname = tarfile.SYMTYPE, content[1]
                bundle.addfile(info)
            else:
                info.size, info.mode = len(content), 0o644
                bundle.addfile(info, io.BytesIO(content))


class UnpackTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def test_refuses_paths_and_links_outside_the_target(self):
        for members in ([("../evil", b"x")], [("/etc/evil", b"x")],
                        [("llama/lib.so", ("symlink", "../../outside"))]):
            archive = self.root / "bad.tar.gz"
            tar_with(archive, members)
            with self.assertRaises(ValueError, msg=members):
                download_llama.unpack(archive, self.root / "out")
        archive = self.root / "bad.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("../evil", "x")
        with self.assertRaises(ValueError):
            download_llama.unpack(archive, self.root / "out")
        self.assertFalse((self.root / "evil").exists())

    def test_keeps_library_links_beside_the_server(self):
        archive = self.root / "good.tar.gz"
        tar_with(archive, [("llama-b1/llama-server", b"#!"), ("llama-b1/libggml.so.0.1", b"lib"),
                           ("llama-b1/libggml.so.0", ("symlink", "libggml.so.0.1"))])
        download_llama.unpack(archive, self.root / "out")
        self.assertEqual((self.root / "out/llama-b1/libggml.so.0").read_bytes(), b"lib")


class InstallTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.tools = Path(directory.name) / ".tools"
        self.archive = Path(directory.name) / "release.tar.gz"
        tar_with(self.archive, [("llama-b11822/llama-server", b"#!server"), ("llama-b11822/libllama.so", b"lib")])
        data = self.archive.read_bytes()
        self.asset = ("llama-test.tar.gz", len(data), hashlib.sha256(data).hexdigest())
        for p in (patch.object(download_llama, "TOOLS", self.tools),
                  patch.object(download_llama, "host", return_value=("Linux", "arm64")),
                  patch.dict(download_llama.ASSETS, {("Linux", "arm64", "cpu"): self.asset})):
            p.start()
            self.addCleanup(p.stop)

    def fake_download(self, url, target, size, digest, progress=None):
        self.assertTrue(url.endswith("/b11822/llama-test.tar.gz"))
        self.assertEqual((size, digest), self.asset[1:])
        shutil.copy(self.archive, target)
        return True

    def test_installs_once_with_its_libraries_and_is_found_by_run_model(self):
        with patch.object(download_llama, "download", side_effect=self.fake_download) as download:
            server, fetched = download_llama.install()
            self.assertTrue(fetched)
            self.assertEqual(server, self.tools / "llama-b11822-cpu" / "llama-server")
            self.assertTrue((server.parent / "libllama.so").is_file())
            self.assertTrue(server.stat().st_mode & 0o100)
            self.assertEqual(download_llama.install(), (server, False))
            self.assertEqual(download.call_count, 1)
            self.assertEqual(download_llama.installed(), server)
        self.assertEqual([p.name for p in self.tools.iterdir()], ["llama-b11822-cpu"])  # no scratch left

    def test_unsupported_platform_says_where_to_get_a_build(self):
        with patch.object(download_llama, "host", return_value=("FreeBSD", "riscv64")):
            with self.assertRaisesRegex(ValueError, "--server"):
                download_llama.install()


if __name__ == "__main__":
    unittest.main()
