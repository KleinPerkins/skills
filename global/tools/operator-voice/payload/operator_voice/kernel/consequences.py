"""Consequence computation and one-use challenges — build plan v3 §6: "preview(operation,
targets) is mandatory when live consequences indicate destruction, irreversibility,
shared-reference impact, or sensitive export. execute requires the bound one-use challenge and
the exact literal shown by preview ... The kernel enforces this; Skill wording or approval UI
cannot bypass it."

The kernel computes *live* consequences (never a static per-operation table alone — §6.4/AWA
precedent: "a safe-looking verb with a destructive consequence MUST confirm; a benign verb MUST
NOT nag"), issues a single-use, operation+target+generation-bound
:class:`~operator_voice.domain.models.OperationChallenge`, and verifies it. This module has no
persistence of its own; the application service is responsible for storing/consuming the
returned challenge exactly once (§6: "CLI/MCP cannot bypass it").
"""

from __future__ import annotations

import secrets
import time

from operator_voice.domain.models import ConsequenceDescriptor, OperationChallenge, new_id
from operator_voice.domain.operations import Operation, Posture

CONSEQUENCE_VERSION = "consequences/v1"
CHALLENGE_TTL_SECONDS = 5 * 60

# A short, plain-language, human-readable wordlist for challenge literals (§6: "never a
# generation ID, digest, or nonce"). Deliberately mundane/unambiguous words: easy to type
# correctly, hard to guess in advance of seeing the preview.
_CHALLENGE_WORDS: tuple[str, ...] = (
    "harbor", "lantern", "meadow", "compass", "cedar", "granite", "willow", "ember",
    "orchard", "ridge", "quartz", "thistle", "juniper", "hollow", "beacon", "canyon",
    "driftwood", "foxglove", "kestrel", "marigold", "pinewood", "saltmarsh", "tidepool", "wren",
)


def compute_consequence(operation: Operation, scope: str | None = None) -> ConsequenceDescriptor:
    """Live consequence: mostly driven by the operation's declared posture, but ``erase`` and
    ``export`` additionally vary by scope (full_system erase is worse than a single fact)."""
    if operation.posture == Posture.SAFE:
        return ConsequenceDescriptor(False, False, False, False, "No destructive or irreversible effect.")
    if operation.posture == Posture.REVERSIBLE:
        return ConsequenceDescriptor(
            False, False, False, False, "Reversible: this can be undone (deprecate, pause, off)."
        )

    # CONSEQUENTIAL
    if operation.name == "erase":
        full = scope == "full_system"
        return ConsequenceDescriptor(
            destructive=True,
            irreversible=True,
            shared_reference=False,
            sensitive_export=False,
            summary=(
                "This permanently deletes all local profile data and cannot be undone."
                if full
                else f"This permanently deletes the '{scope}' scope and cannot be undone."
            ),
        )
    if operation.name == "export":
        return ConsequenceDescriptor(
            destructive=False,
            irreversible=True,
            shared_reference=False,
            sensitive_export=True,
            summary="This writes human-readable profile facts to a file outside the toolkit's control.",
        )
    if operation.name == "portability.export":
        return ConsequenceDescriptor(
            destructive=False,
            irreversible=True,
            shared_reference=False,
            sensitive_export=True,
            summary=(
                "This writes a passphrase-encrypted copy of your whole profile (facts, corrections, "
                "and profile-pack keys) to a file outside the toolkit's control. Anyone with the "
                "file AND the passphrase can reconstruct the profile on another machine."
            ),
        )
    if operation.name == "uninstall":
        return ConsequenceDescriptor(
            destructive=True,
            irreversible=False,
            shared_reference=False,
            sensitive_export=False,
            summary="This removes the installed runtime. Your profile data, config, and keys are kept.",
        )
    if operation.name == "profile.remote_bind":
        return ConsequenceDescriptor(
            destructive=False,
            irreversible=False,
            shared_reference=False,
            sensitive_export=False,
            summary="This binds a private encrypted Git backend and will publish future generations to it.",
        )
    if operation.name == "key.rotate":
        return ConsequenceDescriptor(
            destructive=True,
            irreversible=True,
            shared_reference=False,
            sensitive_export=False,
            summary=(
                "This destroys the current data-encryption key generation; any content already "
                "encrypted under it (including previously published profile-pack objects) becomes "
                "permanently unreadable. A fresh key is minted for everything going forward."
            ),
        )
    return ConsequenceDescriptor(True, True, False, False, "This operation has significant, hard-to-reverse effects.")


def issue_challenge(operation: Operation, targets: list[str], generation_id: str | None) -> OperationChallenge:
    consequence = compute_consequence(operation)
    literal = secrets.choice(_CHALLENGE_WORDS)
    now = time.time()
    return OperationChallenge(
        challenge_id=new_id("chal"),
        operation=operation.name,
        targets=list(targets) + ([generation_id] if generation_id else []),
        literal=literal,
        consequence=consequence,
        issued_at=now,
        expires_at=now + CHALLENGE_TTL_SECONDS,
        used=False,
    )


def verify_challenge(
    challenge: OperationChallenge, *, operation_name: str, targets: list[str], provided_literal: str | None
) -> tuple[bool, str]:
    if challenge.used:
        return False, "challenge already used"
    if time.time() > challenge.expires_at:
        return False, "challenge expired"
    if challenge.operation != operation_name:
        return False, "challenge does not match this operation"
    bound_targets = set(challenge.targets)
    if not set(targets).issubset(bound_targets):
        return False, "challenge does not cover all requested targets"
    if provided_literal is None or provided_literal.strip() != challenge.literal:
        return False, "confirmation literal did not match exactly"
    return True, "ok"
