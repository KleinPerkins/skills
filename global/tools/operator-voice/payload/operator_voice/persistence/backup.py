"""Local encrypted backup/restore — build plan v3 §11: "ships migration metadata, encrypted
backup/restore, schema compatibility checks, and downgrade refusal where a safe reverse
migration does not exist."

Every sensitive column is already AEAD ciphertext (see :mod:`operator_voice.persistence.crypto`),
so a verified whole-file snapshot IS an encrypted backup — this module adds the safe
snapshot/verify/restore/prune mechanics around that fact; it does not add a second encryption
layer over already-encrypted content.
"""

from __future__ import annotations

import shutil
import sqlite3
import time
from pathlib import Path

from operator_voice.persistence import migrations
from operator_voice.persistence.sqlite import connect

BACKUP_RETENTION_COUNT = 10


def create_backup(db_path: Path, backups_dir: Path) -> Path:
    backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    dest = backups_dir / f"operator-voice-{stamp}-{time.time_ns():020d}.sqlite3"
    # Reserve the name rather than ever opening an existing verified snapshot for writes.
    with dest.open("xb"):
        pass

    src_conn = connect(db_path)
    try:
        dest_conn = sqlite3.connect(str(dest))
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        src_conn.close()

    ok, detail = verify_backup(dest)
    if not ok:
        dest.unlink(missing_ok=True)
        raise RuntimeError(f"backup verification failed, snapshot discarded: {detail}")

    _prune_old_backups(backups_dir)
    return dest


def verify_backup(backup_path: Path) -> tuple[bool, str]:
    if not backup_path.exists():
        return False, "backup file does not exist"
    conn = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            return False, f"integrity_check failed: {integrity}"
        compatible, detail = migrations.check_compatible(conn)
        if not compatible:
            return False, detail
        return True, "ok"
    finally:
        conn.close()


def restore_backup(backup_path: Path, db_path: Path, *, live_connection: sqlite3.Connection | None = None) -> None:
    ok, detail = verify_backup(backup_path)
    if not ok:
        raise RuntimeError(f"refusing to restore unverified backup: {detail}")

    if db_path.exists():
        live_conn = sqlite3.connect(str(db_path))
        live_conn.row_factory = sqlite3.Row
        try:
            live_version = migrations.current_version(live_conn)
        finally:
            live_conn.close()
        backup_conn = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
        backup_conn.row_factory = sqlite3.Row
        try:
            backup_version = migrations.current_version(backup_conn)
        finally:
            backup_conn.close()
        if backup_version < live_version:
            raise RuntimeError(
                f"refusing to restore backup schema v{backup_version} over newer live schema "
                f"v{live_version} (downgrade refusal, build plan §11)"
            )

    if live_connection is not None:
        source = sqlite3.connect(f"file:{backup_path}?mode=ro", uri=True)
        try:
            source.backup(live_connection)
        finally:
            source.close()
        return

    for suffix in ("", "-wal", "-shm"):
        stale = Path(str(db_path) + suffix)
        stale.unlink(missing_ok=True)
    shutil.copy2(backup_path, db_path)


def _prune_old_backups(backups_dir: Path) -> None:
    snapshots = sorted(backups_dir.glob("operator-voice-*.sqlite3"))
    excess = len(snapshots) - BACKUP_RETENTION_COUNT
    for stale in snapshots[:max(0, excess)]:
        stale.unlink(missing_ok=True)
