"""Shared runtime construction for every entrypoint (CLI, MCP, skill) — build plan v3 §4 "one
generic product/service/registry/XDG runtime." This is the ONLY place that opens the SQLite
connection, runs pending migrations, and constructs the two independent :class:`CryptoContext`
instances (local-content vs profile-pack, §5.1) — every interface calls :func:`open_runtime`
instead of duplicating this wiring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from operator_voice.application.service import OperatorVoiceService
from operator_voice.persistence import migrations
from operator_voice.persistence.crypto import CryptoContext, KeyStore, MacKeychainKeyStore
from operator_voice.persistence.sqlite import connect
from operator_voice.runtime.paths import RuntimePaths, default_paths


@dataclass
class Runtime:
    paths: RuntimePaths
    service: OperatorVoiceService

    def close(self) -> None:
        self.service.conn.close()


def open_runtime(paths: Optional[RuntimePaths] = None, keystore_factory: Optional[type] = None) -> Runtime:
    """``keystore_factory`` is overridable ONLY by tests (a disposable keychain / in-memory
    store, each called twice for two INDEPENDENT keystore instances — content vs profile-pack,
    §5.1); production callers (CLI, MCP) always get the real default Keychain."""
    resolved_paths = paths or default_paths()
    resolved_paths.ensure()
    conn = connect(resolved_paths.db_path)
    migrations.migrate(conn)

    keystore_cls: type[KeyStore] = keystore_factory or MacKeychainKeyStore
    content_crypto = CryptoContext(keystore_cls())
    profile_pack_crypto = CryptoContext(
        keystore_cls(), kek_account=CryptoContext.PROFILE_PACK_KEK_ACCOUNT
    )
    service = OperatorVoiceService(conn, content_crypto, profile_pack_crypto=profile_pack_crypto, paths=resolved_paths)
    return Runtime(paths=resolved_paths, service=service)


__all__ = ["Runtime", "open_runtime"]
