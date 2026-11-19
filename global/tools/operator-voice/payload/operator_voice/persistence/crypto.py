"""Envelope encryption + OS Keychain integration — build plan v3 §5.1: "Profile objects use
independent data keys. A profile-pack wrapping-key generation protects their envelopes. Erasure
rotates the wrapping key, rewraps retained objects, destroys old key generations in registered
key sinks, and makes affected historical ciphertext inaccessible." and §4.4 threat model:
"OS-Keychain-backed encryption for local state and profile-pack keys ... Keys never enter Git or
logs."

Design (a deliberate, documented reading of "encrypted local SQLite/WAL" — see
``docs/architecture.md#crypto``):

- **KEK** (Key-Encryption-Key): one random 256-bit key per install, held ONLY in the OS Keychain
  (never on disk in any other form). It never encrypts content directly.
- **DEK** (Data-Encryption-Key): one random 256-bit key per *key generation*. All sensitive
  content is AES-256-GCM-encrypted under the CURRENT DEK. The DEK itself is wrapped (AES-256-GCM)
  by the KEK and the wrapped bytes are stored in the local database (safe: unusable without the
  KEK).
- **Rotation / crypto-shredding**: creating a new generation wraps a fresh DEK; destroying a
  generation deletes its wrapped-DEK row. Any ciphertext still encrypted under a destroyed DEK
  becomes permanently unrecoverable — this is what "erasure ... makes affected historical
  ciphertext inaccessible" means when ciphertext bytes themselves cannot be scrubbed (e.g. old
  Git history, §5.1).
- We deliberately do NOT use a modified/compiled SQLite (e.g. SQLCipher): the stdlib ``sqlite3``
  module stores ciphertext blobs in ordinary columns, keeping the dependency footprint minimal
  and auditable (§4.4 "Sensitive data at rest" is satisfied at the field level, not the
  whole-file level — every column that could carry raw text, feature values, prompts, or PII is
  encrypted; IDs/timestamps/enums used for indexing are not sensitive and stay in the clear).

Uses the macOS ``security`` CLI directly via ``subprocess`` rather than a third-party keyring
abstraction, so the entire Keychain interaction surface is a handful of reviewable lines here.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import subprocess
from dataclasses import dataclass
from typing import Optional, Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

CRYPTO_VERSION = "crypto/v1"
KEY_LENGTH_BYTES = 32
NONCE_LENGTH_BYTES = 12


class KeyStoreError(RuntimeError):
    pass


class KeyStore(Protocol):
    def get_or_create(self, account: str) -> bytes: ...

    def get(self, account: str) -> Optional[bytes]: ...

    def set(self, account: str, key: bytes) -> None: ...

    def delete(self, account: str) -> None: ...


@dataclass
class MacKeychainKeyStore:
    """Production + disposable-test-keychain backend. When ``keychain_path`` is None, targets
    the user's default Keychain (production). When set (tests only), every ``security`` call is
    scoped to that specific keychain file — see
    ``tests/security/test_keychain_integration.py`` for the disposable-keychain fixture that
    creates, uses, and destroys a throwaway keychain per test run."""

    service: str = "operator-voice"
    keychain_path: Optional[str] = None

    def _keychain_args(self) -> list[str]:
        return [self.keychain_path] if self.keychain_path else []

    def get(self, account: str) -> Optional[bytes]:
        cmd = [
            "/usr/bin/security", "find-generic-password",
            "-a", account, "-s", self.service, "-w",
            *self._keychain_args(),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            return None
        b64 = proc.stdout.strip()
        if not b64:
            return None
        return base64.b64decode(b64)

    def set(self, account: str, key: bytes) -> None:
        b64 = base64.b64encode(key).decode("ascii")
        command = [
            "add-generic-password", "-a", account, "-s", self.service,
            "-w", b64, "-U", *self._keychain_args(),
        ]
        # The interactive CLI accepts one command on stdin. Keep wrapping keys out
        # of process argv, and refuse line delimiters before entering its parser.
        if any(any(char in token for char in "\r\n\0") for token in command):
            raise KeyStoreError("Keychain command fields must be single-line values")
        # Apple's split_line parser ends an argument at its closing quote; it
        # does not support the adjacent quote fragments emitted by shlex.quote.
        escaped = (token.replace("\\", "\\\\").replace('"', '\\"') for token in command)
        command_line = " ".join('"' + token + '"' for token in escaped) + "\n"
        if len(command_line.encode("utf-8")) >= 4096:
            raise KeyStoreError("Keychain command exceeds the interactive input limit")
        proc = subprocess.run(
            ["/usr/bin/security", "-q", "-i"],
            input=command_line,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if proc.returncode != 0:
            # Parser diagnostics may echo the command; never relay key material.
            raise KeyStoreError("Keychain write failed")

    def delete(self, account: str) -> None:
        cmd = [
            "/usr/bin/security", "delete-generic-password",
            "-a", account, "-s", self.service,
            *self._keychain_args(),
        ]
        subprocess.run(cmd, capture_output=True, text=True)  # best-effort; absence is not an error

    def get_or_create(self, account: str) -> bytes:
        existing = self.get(account)
        if existing is not None:
            return existing
        fresh = secrets.token_bytes(KEY_LENGTH_BYTES)
        self.set(account, fresh)
        return fresh


@dataclass
class InMemoryKeyStore:
    """Fast, dependency-free backend for unit tests that only need crypto-correctness coverage,
    not real Keychain plumbing. The real Keychain path is exercised by
    ``tests/security/test_keychain_integration.py`` against a disposable keychain, never faked
    away entirely."""

    _store: dict[str, bytes] | None = None

    def __post_init__(self) -> None:
        if self._store is None:
            self._store = {}

    def get(self, account: str) -> Optional[bytes]:
        return self._store.get(account)

    def set(self, account: str, key: bytes) -> None:
        self._store[account] = key

    def delete(self, account: str) -> None:
        self._store.pop(account, None)

    def get_or_create(self, account: str) -> bytes:
        existing = self.get(account)
        if existing is not None:
            return existing
        fresh = secrets.token_bytes(KEY_LENGTH_BYTES)
        self.set(account, fresh)
        return fresh


def aead_encrypt(key: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    """AES-256-GCM encrypt. Output = nonce(12) || ciphertext_with_tag."""
    nonce = secrets.token_bytes(NONCE_LENGTH_BYTES)
    ct = AESGCM(key).encrypt(nonce, plaintext, aad)
    return nonce + ct


def aead_decrypt(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    nonce, ct = blob[:NONCE_LENGTH_BYTES], blob[NONCE_LENGTH_BYTES:]
    return AESGCM(key).decrypt(nonce, ct, aad)


def deterministic_aead_encrypt(key: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    """Nonce-committing AES-256-GCM: the nonce is HMAC-SHA256(key, aad || plaintext)[:12] instead
    of random. Used ONLY by the profile-pack publisher for content-addressed objects, where the
    digest of the (already redacted) plaintext IS the object's identity — a random nonce would
    make every republish of unchanged content mint a brand-new object forever, defeating CAS
    dedup and the "same digest is a no-op" invariant. Everywhere else in this codebase, random-
    nonce :func:`aead_encrypt` is correct and MUST be used instead. Decrypting either form uses
    the same :func:`aead_decrypt` — GCM decryption only needs the nonce embedded in the blob, not
    a recomputation of how it was derived. Determinism here trades a small, well-understood
    equality-of-plaintext leak (inherent to any CAS design, same as Git's own blob addressing)
    for real dedup."""
    nonce = hmac.new(key, aad + plaintext, hashlib.sha256).digest()[:NONCE_LENGTH_BYTES]
    ct = AESGCM(key).encrypt(nonce, plaintext, aad)
    return nonce + ct


@dataclass
class KeyGeneration:
    generation_id: str
    wrapped_dek: bytes  # AES-256-GCM(KEK, dek)
    created_at: float
    destroyed_at: Optional[float] = None


class CryptoContext:
    """Ties KEK (Keychain) + DEK (wrapped, DB-resident) together. One instance per open store.

    ``kek_account`` defaults to the local-content KEK. The profile-pack publisher constructs a
    SECOND instance with ``kek_account=PROFILE_PACK_KEK_ACCOUNT`` so "profile objects use
    independent data keys [under] a profile-pack wrapping-key generation" (§5.1) is a real,
    distinct Keychain entry — recovering the profile pack on a clean machine never requires, and
    never grants, the local-content key.
    """

    KEK_ACCOUNT = "local-kek-v1"
    HMAC_SECRET_ACCOUNT = "local-hmac-secret-v1"
    PROFILE_PACK_KEK_ACCOUNT = "profile-pack-kek-v1"

    def __init__(self, keystore: KeyStore, kek_account: Optional[str] = None):
        self.keystore = keystore
        self.kek_account = kek_account or self.KEK_ACCOUNT
        self._kek: Optional[bytes] = None

    @property
    def kek(self) -> bytes:
        if self._kek is None:
            self._kek = self.keystore.get_or_create(self.kek_account)
        return self._kek

    @property
    def hmac_secret(self) -> bytes:
        return self.keystore.get_or_create(self.HMAC_SECRET_ACCOUNT)

    def wrap_new_dek(self) -> tuple[bytes, bytes]:
        """Returns (dek, wrapped_dek)."""
        dek = secrets.token_bytes(KEY_LENGTH_BYTES)
        wrapped = aead_encrypt(self.kek, dek, aad=b"dek-wrap")
        return dek, wrapped

    def unwrap_dek(self, wrapped_dek: bytes) -> bytes:
        return aead_decrypt(self.kek, wrapped_dek, aad=b"dek-wrap")

    def destroy_local_keys(self) -> None:
        """Full local-key destruction (used by ``erase --scope full_system``). The KEK itself is
        destroyed; every wrapped DEK in the database becomes permanently unwrappable, which is
        the crypto-shredding guarantee for any ciphertext still resident in e.g. old Git history
        (§5.1)."""
        self.keystore.delete(self.kek_account)
        if self.kek_account == self.KEK_ACCOUNT:
            self.keystore.delete(self.HMAC_SECRET_ACCOUNT)
        self._kek = None


def new_generation_id() -> str:
    return f"keygen_{secrets.token_hex(8)}"


def disposable_test_keychain(tmp_dir: str, password: str = "test-password-not-secret") -> str:
    """Create a throwaway macOS keychain file for integration tests and return its path. Callers
    MUST call :func:`destroy_test_keychain` afterward. This is the "disposable unlocked test
    Keychain" the operator prompt requires for automated Keychain-dependent tests."""
    path = os.path.join(tmp_dir, "ovt-test.keychain-db")
    subprocess.run(
        ["/usr/bin/security", "create-keychain", "-p", password, path],
        check=True, capture_output=True, text=True,
    )
    subprocess.run(
        ["/usr/bin/security", "set-keychain-settings", path], check=True, capture_output=True
    )
    subprocess.run(
        ["/usr/bin/security", "unlock-keychain", "-p", password, path],
        check=True, capture_output=True, text=True,
    )
    return path


def destroy_test_keychain(path: str) -> None:
    subprocess.run(["/usr/bin/security", "delete-keychain", path], capture_output=True, text=True)
    for suffix in ("", "-db"):
        try:
            os.remove(path + suffix if not path.endswith(suffix) else path)
        except OSError:
            pass
