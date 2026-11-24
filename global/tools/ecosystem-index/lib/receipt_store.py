"""Durable paired receipts for an owner-selected admitted snapshot location."""

import fcntl
import os
import secrets
import stat

from .contracts import (SNAPSHOT_MAX, Refusal, digest, encode, fail, json_load,
                        result as validate_result, snapshot)
from .io_safe import FLAGS, Publisher, read_at, read_file
from .checkout_admission import validate_input_diagnostics


LOCK_MARKER = b"skills-admitted-snapshot-lock/v1\n"


def receipt_name(snapshot_name, admission, snapshot_digest):
    key = encode([admission.inventory_version, admission.config_digest, admission.projection_digest,
                  admission.physical_binding_digest,
                  admission.skills_revision, snapshot_digest])
    return snapshot_name + ".receipt-" + digest(key) + ".json"


def install_record(fd, name, data):
    """Publish exact private bytes at a closed owned name without overwriting."""
    staged = ".skills-record-" + secrets.token_hex(16)
    open_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
    with os.fdopen(os.open(staged, open_flags, 0o600, dir_fd=fd), "wb") as stream:
        try:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
            os.link(staged, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False)
            os.fsync(fd)
        finally:
            os.unlink(staged, dir_fd=fd)


def checksum_name(receipt):
    return receipt.removesuffix(".json") + ".sha"


def install_matching_record(fd, name, data, limit):
    try:
        install_record(fd, name, data)
    except FileExistsError:
        if read_at(fd, name, limit, True) != data:
            fail("unavailable", 3)
        # A concurrent creator or interrupted retry may not have synced yet.
        os.fsync(fd)


class AdmittedPublisher(Publisher):
    """Retain an owner marker and use a kernel lock released on process exit."""

    lock_fd = None

    def acquire(self):
        self.lock = self.name + ".lock"
        try:
            os.stat(self.lock, dir_fd=self.fd, follow_symlinks=False)
        except FileNotFoundError:
            try:
                install_record(self.fd, self.lock, LOCK_MARKER)
            except FileExistsError:
                pass
        try:
            self.lock_fd = os.open(self.lock, FLAGS | os.O_NONBLOCK, dir_fd=self.fd)
            info = os.fstat(self.lock_fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600):
                fail("unsafe_path", 3)
            if os.read(self.lock_fd, len(LOCK_MARKER) + 1) != LOCK_MARKER:
                fail("busy", 3)
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            current = os.stat(self.lock, dir_fd=self.fd, follow_symlinks=False)
            if not os.path.samestat(info, current):
                fail("busy", 3)
        except BlockingIOError:
            fail("busy", 3)
        except OSError:
            fail("unsafe_path", 3)

    def __exit__(self, *exc):
        try:
            super().__exit__(*exc)
        finally:
            if self.lock_fd is not None:
                os.close(self.lock_fd)
                self.lock_fd = None

    def save_receipt(self, admission, receipt):
        name = receipt_name(self.name, admission, receipt["snapshot_digest"])
        data = encode(receipt)
        if len(data) > SNAPSHOT_MAX:
            fail("bound_exceeded", 3)
        checksum = (digest(data) + "\n").encode("ascii")
        # Both private records must be durable before the caller replaces the
        # snapshot. Their names bind the exact inventory and snapshot digest.
        install_matching_record(self.fd, name, data, SNAPSHOT_MAX)
        install_matching_record(self.fd, checksum_name(name), checksum, 65)


def load_qualified_snapshot(path, admission):
    """Read a consistent snapshot and its exact receipt for the supplied binding."""
    projected_config = admission.validate()
    raw = read_file(path, SNAPSHOT_MAX, True)
    value = snapshot(json_load(raw, SNAPSHOT_MAX))
    snapshot_digest = digest(raw)
    parent, name = os.path.split(path)
    name = receipt_name(name, admission, snapshot_digest)
    try:
        raw_receipt = read_file(os.path.join(parent, name), SNAPSHOT_MAX, True)
        checksum = read_file(os.path.join(parent, checksum_name(name)), 65, True)
        if checksum != (digest(raw_receipt) + "\n").encode("ascii"):
            fail("unavailable", 3)
        receipt = json_load(raw_receipt, SNAPSHOT_MAX)
        result = validate_result(receipt["result"])
        diagnostics = validate_input_diagnostics(receipt["input_diagnostics"], value["inputs"], projected_config)
        if (result["command"] != "refresh" or result["generation"] != value["generation"]
                or result["snapshot_digest"] != snapshot_digest
                or result["coverage"] != value["coverage"] or result["reasons"] != value["reasons"]
                or result["counts"]["entities"] != len(value["entities"])
                or receipt != admission.receipt(result, value["observed_at"], diagnostics)):
            fail("unavailable", 3)
    except Refusal as error:
        if error.code == "bound_exceeded":
            raise
        fail("unavailable", 3)
    except (TypeError, KeyError):
        fail("unavailable", 3)
    return value, receipt
