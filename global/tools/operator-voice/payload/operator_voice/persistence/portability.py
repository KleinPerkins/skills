"""Deterministic, passphrase-encrypted profile portability — build plan v4 §13 M4 worklist 4
("deterministic encrypted export/import of a profile across machines, round-trip fidelity") and
§4.4 threat model ("Keys never enter Git or logs").

This is a DELIBERATELY tiny, self-contained crypto surface (so the M4 security/privacy review can
audit it in one read). It seals a plain ``payload`` dict — the operator's whole profile
(subjects, facts, corrections, aliases, generations, and the profile-pack key material a second
machine needs to decrypt/reconcile the ENCRYPTED_GIT pack) — into a single archive that is:

* **Deterministic given (payload, passphrase, salt).** The nonce is derived from the derived key
  and plaintext (nonce-committing AES-GCM), so a re-seal of identical inputs is byte-identical —
  round-trip fidelity is testable without wall-clock nondeterminism. The salt is random per export
  by default (so two exports of the same profile are not linkable) but may be pinned for a
  reproducibility test.
* **Confidential + tamper-evident under the operator passphrase.** The key is scrypt-derived from
  the passphrase; the payload is AES-256-GCM sealed. A wrong passphrase or any bit-flip fails the
  GCM tag and raises :class:`PortabilityError` — never a partial/garbage decrypt.
* **Self-describing, signed-manifest + version-gated.** The clear archive header is a *manifest*
  ``{schema, version, kdf}`` that is cryptographically bound into the AEAD as additional
  authenticated data — so it is effectively **signed** by the passphrase-derived key: any tamper to
  the schema, version, or KDF parameters fails the GCM tag rather than silently changing how the
  archive is opened. Import enforces an explicit **version-compatibility check** (same major
  version) and refuses an unknown schema/version instead of guessing.

The archive contains NO plaintext profile data and NO key that is usable without the passphrase.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Any

from cryptography.exceptions import InvalidTag

from operator_voice.persistence.crypto import KEY_LENGTH_BYTES, NONCE_LENGTH_BYTES
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PORTABILITY_VERSION = "portability/v1"
PORTABLE_PROFILE_SCHEMA = "operator-voice-portable-profile/v1"
# Semantic archive version. Import accepts the same MAJOR only (a future breaking change bumps the
# major and older readers refuse it rather than mis-parsing).
PORTABLE_PROFILE_VERSION = "1.0"
SUPPORTED_MAJOR = 1

# scrypt work factors (interactive-desktop grade; RFC 7914). N must be a power of two.
SCRYPT_N = 2 ** 15
SCRYPT_R = 8
SCRYPT_P = 1
SALT_LENGTH_BYTES = 16


class PortabilityError(RuntimeError):
    """Wrong passphrase, tampered/corrupt archive, or an unsupported archive schema/version."""


def _canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _manifest(kdf: dict[str, Any]) -> dict[str, Any]:
    """The signed (AAD-bound) manifest. Deterministic + canonical so seal/open agree byte-for-byte."""
    return {"schema": PORTABLE_PROFILE_SCHEMA, "version": PORTABLE_PROFILE_VERSION, "kdf": kdf}


def _major(version: str) -> int:
    try:
        return int(str(version).split(".", 1)[0])
    except (ValueError, AttributeError):
        return -1


def derive_key(passphrase: str, salt: bytes, *, n: int = SCRYPT_N, r: int = SCRYPT_R, p: int = SCRYPT_P) -> bytes:
    if not passphrase:
        raise PortabilityError("a non-empty passphrase is required")
    return hashlib.scrypt(
        passphrase.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=KEY_LENGTH_BYTES,
        maxmem=n * r * 128 * 2 + (1 << 20),
    )


def _seal_bytes(key: bytes, plaintext: bytes, aad: bytes) -> bytes:
    """Nonce-committing AES-256-GCM (nonce = HMAC(key, plaintext)[:12]) so identical inputs seal to
    identical bytes — deterministic round-trip without a random nonce. Output = nonce || ct. ``aad``
    is the canonical signed manifest, so the header is tamper-evident under the derived key."""
    nonce = hmac.new(key, plaintext, hashlib.sha256).digest()[:NONCE_LENGTH_BYTES]
    ct = AESGCM(key).encrypt(nonce, plaintext, aad)
    return nonce + ct


def _open_bytes(key: bytes, blob: bytes, aad: bytes) -> bytes:
    nonce, ct = blob[:NONCE_LENGTH_BYTES], blob[NONCE_LENGTH_BYTES:]
    return AESGCM(key).decrypt(nonce, ct, aad)


@dataclass(frozen=True, slots=True)
class SealedArchive:
    schema: str
    version: str
    kdf: dict[str, Any]
    ciphertext_b64: str
    created_at: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema, "version": self.version, "kdf": self.kdf,
            "ciphertext": self.ciphertext_b64, "created_at": self.created_at,
        }


def seal(passphrase: str, payload: dict[str, Any], *, salt: bytes | None = None, created_at: float = 0.0) -> SealedArchive:
    """Seal ``payload`` under ``passphrase``. The manifest ``{schema, version, kdf}`` is bound into
    the AEAD (signed). ``created_at`` and a content digest live INSIDE the sealed plaintext so they
    are authenticated by the GCM tag too — integrity is provable after decryption independent of the
    outer header."""
    salt = salt if salt is not None else _random_salt()
    key = derive_key(passphrase, salt)
    kdf = {"algo": "scrypt", "n": SCRYPT_N, "r": SCRYPT_R, "p": SCRYPT_P,
           "dklen": KEY_LENGTH_BYTES, "salt": base64.b64encode(salt).decode("ascii")}
    aad = _canonical_json(_manifest(kdf))
    inner = {
        "schema": PORTABLE_PROFILE_SCHEMA,
        "version": PORTABLE_PROFILE_VERSION,
        "created_at": created_at,
        "content_digest": hashlib.sha256(_canonical_json(payload)).hexdigest(),
        "payload": payload,
    }
    blob = _seal_bytes(key, _canonical_json(inner), aad)
    return SealedArchive(
        schema=PORTABLE_PROFILE_SCHEMA, version=PORTABLE_PROFILE_VERSION, kdf=kdf,
        ciphertext_b64=base64.b64encode(blob).decode("ascii"), created_at=created_at,
    )


def open_archive(passphrase: str, archive: dict[str, Any]) -> dict[str, Any]:
    """Verify + decrypt an archive dict, returning the original ``payload``. Raises
    :class:`PortabilityError` for an unsupported schema/version, a wrong passphrase, or any tamper
    (including a modified manifest header, which is AAD-signed)."""
    schema = archive.get("schema")
    if schema != PORTABLE_PROFILE_SCHEMA:
        raise PortabilityError(f"unsupported portable-profile schema: {schema!r}")
    version = archive.get("version", "0")
    if _major(version) != SUPPORTED_MAJOR:
        raise PortabilityError(
            f"incompatible portable-profile version {version!r}; this build supports major "
            f"{SUPPORTED_MAJOR}.x only"
        )
    kdf = archive.get("kdf") or {}
    if kdf.get("algo") != "scrypt":
        raise PortabilityError(f"unsupported KDF: {kdf.get('algo')!r}")
    try:
        salt = base64.b64decode(kdf["salt"])
        blob = base64.b64decode(archive["ciphertext"])
    except (KeyError, ValueError, TypeError) as exc:
        raise PortabilityError(f"malformed archive: {exc}") from exc
    # Fail closed on the KDF work factors BEFORE deriving a key. This build seals at major 1 with
    # exactly (SCRYPT_N, SCRYPT_R, SCRYPT_P, dklen=KEY_LENGTH_BYTES); accepting attacker-chosen
    # parameters from an untrusted archive would allow either a scrypt DOWNGRADE (weaken the KDF on a
    # file an operator is about to import) or a resource-exhaustion DoS (inflate n so the import-time
    # allocation explodes). Different work factors are a different scheme → a future version bump, not
    # a silent reinterpretation here.
    try:
        n, r, p = int(kdf.get("n")), int(kdf.get("r")), int(kdf.get("p"))
        dklen = int(kdf.get("dklen", KEY_LENGTH_BYTES))
    except (TypeError, ValueError) as exc:
        raise PortabilityError(f"malformed KDF parameters: {exc}") from exc
    if (n, r, p, dklen) != (SCRYPT_N, SCRYPT_R, SCRYPT_P, KEY_LENGTH_BYTES):
        raise PortabilityError(
            f"unsupported scrypt parameters (got n={n}, r={r}, p={p}, dklen={dklen}); this build "
            f"opens n={SCRYPT_N}, r={SCRYPT_R}, p={SCRYPT_P}, dklen={KEY_LENGTH_BYTES} only"
        )
    # AAD = the exact manifest we expect; any tamper to schema/version/kdf makes this diverge and
    # the GCM tag fails. (We reconstruct from constants + the archive's kdf so a downgraded/edited
    # header cannot silently take effect.)
    aad = _canonical_json(_manifest(kdf))
    key = derive_key(passphrase, salt, n=n, r=r, p=p)
    try:
        plaintext = _open_bytes(key, blob, aad)
    except InvalidTag as exc:
        raise PortabilityError("passphrase incorrect or archive corrupted (authentication failed)") from exc
    try:
        inner = json.loads(plaintext)
    except json.JSONDecodeError as exc:  # pragma: no cover — GCM tag makes this practically unreachable
        raise PortabilityError("archive decrypted to invalid content") from exc
    payload = inner.get("payload")
    if inner.get("schema") != PORTABLE_PROFILE_SCHEMA or _major(inner.get("version", "0")) != SUPPORTED_MAJOR or not isinstance(payload, dict):
        raise PortabilityError("archive inner schema/version mismatch")
    expected = hashlib.sha256(_canonical_json(payload)).hexdigest()
    if not hmac.compare_digest(expected, str(inner.get("content_digest"))):
        raise PortabilityError("archive content digest mismatch (integrity check failed)")
    return payload


def _random_salt() -> bytes:
    import secrets

    return secrets.token_bytes(SALT_LENGTH_BYTES)


__all__ = [
    "PORTABILITY_VERSION",
    "PORTABLE_PROFILE_SCHEMA",
    "PORTABLE_PROFILE_VERSION",
    "SUPPORTED_MAJOR",
    "PortabilityError",
    "SealedArchive",
    "derive_key",
    "seal",
    "open_archive",
]
