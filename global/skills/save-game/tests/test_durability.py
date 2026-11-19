import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from engine import durability  # noqa: E402


class TestEnsurePrivateDir(unittest.TestCase):
    def test_creates_missing_components_with_private_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "a" / "b" / "c"
            durability.ensure_private_dir(target)
            self.assertTrue(target.is_dir())
            for p in (target, target.parent, target.parent.parent):
                self.assertEqual(stat.S_IMODE(p.stat().st_mode), durability.DIR_MODE)

    def test_repairs_broader_existing_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "broad"
            target.mkdir(mode=0o755)
            os.chmod(target, 0o755)  # mkdir mode is umask-affected; force it
            durability.ensure_private_dir(target)
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), durability.DIR_MODE)

    def test_refuses_symlink_component(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real"
            real.mkdir()
            link = Path(tmp) / "link"
            link.symlink_to(real)
            target = link / "child"
            with self.assertRaises(durability.UnsafePathError):
                durability.ensure_private_dir(target)

    def test_refuses_non_directory_component(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "afile"
            f.write_text("x")
            with self.assertRaises(durability.UnsafePathError):
                durability.ensure_private_dir(f / "child")


class TestAtomicReplaceDurable(unittest.TestCase):
    def test_writes_full_content_and_is_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "sub" / "file.json"
            durability.atomic_replace_durable(target, b'{"a": 1}')
            self.assertEqual(target.read_bytes(), b'{"a": 1}')
            self.assertEqual(stat.S_IMODE(target.stat().st_mode), durability.FILE_MODE)

    def test_replace_overwrites_previous_content_atomically(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "file.json"
            durability.atomic_replace_durable(target, b"first")
            durability.atomic_replace_durable(target, b"second")
            self.assertEqual(target.read_bytes(), b"second")
            # no leftover temp files
            leftovers = [p for p in Path(tmp).iterdir() if p.name != "file.json"]
            self.assertEqual(leftovers, [])

    def test_no_temp_file_leaked_on_write_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "file.json"
            with mock.patch.object(durability, "_sync_fd", side_effect=durability.DurabilityError("boom")):
                with self.assertRaises(durability.DurabilityError):
                    durability.atomic_replace_durable(target, b"data")
            self.assertFalse(target.exists())
            leftovers = list(Path(tmp).iterdir())
            self.assertEqual(leftovers, [])


class TestCreateExclusiveDurable(unittest.TestCase):
    def test_second_create_raises_file_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "once.json"
            durability.create_exclusive_durable(target, b"data")
            with self.assertRaises(FileExistsError):
                durability.create_exclusive_durable(target, b"data")
            self.assertEqual(target.read_bytes(), b"data")


class TestReadFileBytesNoFollow(unittest.TestCase):
    def test_reads_regular_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "f.json"
            target.write_bytes(b"payload")
            self.assertEqual(durability.read_file_bytes(target), b"payload")

    def test_refuses_symlink(self):
        with tempfile.TemporaryDirectory() as tmp:
            real = Path(tmp) / "real.json"
            real.write_bytes(b"payload")
            link = Path(tmp) / "link.json"
            link.symlink_to(real)
            with self.assertRaises(durability.UnsafePathError):
                durability.read_file_bytes(link)

    def test_missing_file_raises_file_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                durability.read_file_bytes(Path(tmp) / "missing.json")


class TestIsLocalDisk(unittest.TestCase):
    def test_local_mount_point_is_local(self):
        fake_mount_output = "/dev/disk3s1 on /System/Volumes/Data (apfs, local, journaled)\n"
        with mock.patch(
            "subprocess.run",
            return_value=mock.Mock(stdout=fake_mount_output),
        ):
            self.assertTrue(durability.is_local_disk(Path("/System/Volumes/Data/foo")))

    def test_network_mount_point_is_not_local(self):
        fake_mount_output = (
            "/dev/disk3s1 on / (apfs, local, journaled)\n"
            "//server/share on /Volumes/share (smbfs, nodev, nosuid)\n"
        )
        with mock.patch(
            "subprocess.run",
            return_value=mock.Mock(stdout=fake_mount_output),
        ):
            self.assertFalse(durability.is_local_disk(Path("/Volumes/share/state")))

    def test_unavailable_mount_command_fails_open(self):
        with mock.patch("subprocess.run", side_effect=FileNotFoundError()):
            self.assertTrue(durability.is_local_disk(Path("/tmp")))


class TestAssertEnvironmentSafe(unittest.TestCase):
    def test_creates_root_when_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "state" / "save-game" / "v1"
            durability.assert_environment_safe(root)
            self.assertTrue(root.is_dir())

    def test_raises_unsupported_environment_when_not_local(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "state"
            with mock.patch.object(durability, "is_local_disk", return_value=False):
                with self.assertRaises(durability.UnsupportedEnvironmentError):
                    durability.assert_environment_safe(root)


if __name__ == "__main__":
    unittest.main()
