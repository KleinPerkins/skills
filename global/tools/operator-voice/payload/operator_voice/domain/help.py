"""Deterministic per-operation help enrichment — build plan v3 §6 ("One typed operation registry
generates CLI commands, MCP tools, JSON schemas, operation cards, examples, error taxonomy,
posture annotations, and deterministic help. Adding a verb edits the registry and service once,
never each surface separately").

Every function here is a pure, deterministic function of the :data:`operator_voice.domain.
operations.OPERATIONS` registry alone — no I/O, no model, no network (kernel purity). The error
taxonomy is an EXPLICIT, per-operation table that was verified line-by-line against the real
handlers in :mod:`operator_voice.application.service`: every entry corresponds either to the
universal interface-boundary argument check, to a concrete ``raise ServiceError(...)`` /
``ConfirmationRequired`` the handler actually produces, or to a documented refusal the handler
returns as a status (e.g. a LOCAL_ONLY skip). It never advertises a failure the service cannot
actually produce, and it is not derived from argument *names* (which systematically over-claim —
many operations declare a ``subject_id`` yet never look the subject up).

This module exists so the eval manifest's ``deterministic_help_coverage_rate`` measure — "a
generated operation card, a worked example, a non-empty error taxonomy, and (where consequential) a
plain-language challenge/consent description, per operation" — is satisfied by construction and
verifiable (see :mod:`operator_voice.eval.coverage` and ``tests/eval/test_help_coverage.py``),
rather than by hand-maintained prose per surface. Every meaning is written for an operator, not an
engineer: no internal section tags, decision-log ids, or filesystem paths.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass

from operator_voice.domain.operations import ArgType, Operation, Posture

HELP_VERSION = "help/v1"


@dataclass(frozen=True, slots=True)
class OperationError:
    """One named failure mode an operation can surface, with a plain-language meaning an operator
    (not an engineer) can act on. ``code`` is a stable, machine-greppable token; ``meaning`` never
    embeds a filesystem path, id value, or secret."""

    code: str
    meaning: str


# Universal boundary failure — every operation's arguments are validated against its ArgSpec tuple
# (required/type/choices) at the one application-service boundary, on every surface (CLI, MCP,
# direct call). This guarantees a non-empty taxonomy for even the simplest read operation.
_INVALID_ARGUMENTS = OperationError(
    "invalid_arguments",
    "An argument was missing, had the wrong type, or wasn't one of the allowed choices — nothing changed.",
)

# The two failure modes every CONSEQUENTIAL operation shares — the challenge/consent gate
# (service `_require_confirmation_or_raise` -> ConfirmationRequired / confirmation mismatch). Added
# automatically for any operation whose posture is CONSEQUENTIAL, so a new consequential verb cannot
# forget them.
_CONFIRMATION_REQUIRED = OperationError(
    "confirmation_required",
    "This action is gated: it first returns an exact confirmation phrase and makes no change until "
    "you re-run it with that phrase.",
)
_CONFIRMATION_MISMATCH = OperationError(
    "confirmation_mismatch",
    "The confirmation phrase you supplied did not match the required one — nothing changed.",
)

# Reusable, service-verified failures shared across several operations.
_UNKNOWN_SUBJECT = OperationError("unknown_subject", "No registered subject has that id — nothing changed.")
_NO_OPERATOR_SUBJECT = OperationError(
    "no_operator_subject",
    "No operator subject is registered; run setup to register one before requesting context.",
)
_INACTIVE_OPERATOR_SUBJECT = OperationError(
    "inactive_operator_subject",
    "Operator subjects exist but are paused; list subjects and pass one opaque id explicitly.",
)
_AMBIGUOUS_OPERATOR_SUBJECT = OperationError(
    "ambiguous_operator_subject",
    "More than one active operator subject exists; pass one listed opaque subject id explicitly.",
)
_UNKNOWN_SOURCE = OperationError("unknown_source", "No registered source has that id — nothing changed.")
_SOURCE_NOT_ACTIVE = OperationError(
    "source_not_active", "The source is registered but paused; re-activate it before ingesting."
)
_UNKNOWN_GENERATION = OperationError("unknown_generation", "No stored generation has that id.")
_UNKNOWN_FACT = OperationError("unknown_fact", "No stored fact has that id — nothing changed.")
_NO_OPEN_REVIEW = OperationError("no_open_review_item", "No OPEN review item has that id.")
_LOCAL_ONLY_SKIP = OperationError(
    "local_only_no_backend",
    "You are in local-only mode with no private-Git backend bound, so this is a safe no-op.",
)

# The one authoritative, per-operation error taxonomy (BEYOND the universal argument check and the
# automatic consequential-gate pair). Each tuple was verified against the named handler in
# application/service.py. Operations absent from this table surface only the universal
# argument-validation error (plus the consequential gate, if applicable) — which is the honest
# taxonomy for a handler that performs no id lookup and raises nothing else.
_OP_ERRORS: dict[str, tuple[OperationError, ...]] = {
    # --- reads that actually look their subject up + negotiate/refuse ---
    "context.get": (
        _UNKNOWN_SUBJECT,
        _NO_OPERATOR_SUBJECT,
        _INACTIVE_OPERATOR_SUBJECT,
        _AMBIGUOUS_OPERATOR_SUBJECT,
        OperationError("operator_only", "This serves your own (OPERATOR) subject; use subject.insights for someone else."),
        OperationError("no_accepted_bundle_version", "The consumer accepted no context version the toolkit offers, so it declines rather than send an unsupported shape."),
        OperationError("insufficient_evidence", "Below the quality floor the toolkit abstains rather than return a thin, misleading bundle."),
    ),
    "subject.insights": (
        _UNKNOWN_SUBJECT,
        OperationError("external_only", "This describes someone else (an EXTERNAL subject); it refuses your own OPERATOR subject."),
        OperationError("subject_not_enrolled", "That person has no approved analysis purpose enrolled yet, so analysis is refused."),
    ),
    # --- mutations that now look their subject/source/fact up (service-verified) ---
    "subject.add": (
        OperationError("external_needs_approved_purpose", "Enrolling someone else requires at least one explicit, allowed analysis purpose."),
    ),
    "subject.alias_add": (
        _UNKNOWN_SUBJECT,
        OperationError("external_only", "Aliases apply to someone else (an EXTERNAL subject); your own identity is established by source role, not an attested alias."),
        OperationError("empty_identifier", "The source identifier was empty; it is required."),
        OperationError("alias_collision_quarantined", "That identifier already points at another subject, so it is held for review rather than silently re-pointed."),
    ),
    "source.add": (_UNKNOWN_SUBJECT,),
    "subject.pause": (_UNKNOWN_SUBJECT,),
    "source.pause": (_UNKNOWN_SOURCE,),
    "slack.import": (
        OperationError(
            "author_id_missing",
            "Your own Slack user id (the top-level author_id) is required — supply it directly, "
            "or via --file/stdin as part of the {author_id, messages} envelope.",
        ),
        OperationError(
            "no_messages_provided",
            "No messages were supplied — provide --messages, --file, or pipe the envelope via stdin.",
        ),
        OperationError("import_file_not_found", "No file exists at the given --file path."),
        OperationError("import_file_not_valid_json", "The --file content (or piped stdin) was not valid JSON."),
    ),
    "drive.import": (
        OperationError(
            "owner_id_missing",
            "Your own Drive user id (the top-level owner_id) is required — supply it directly, or "
            "via --file/stdin as part of the {owner_id, files} envelope.",
        ),
        OperationError(
            "no_files_provided",
            "No files were supplied — provide --files, --file, or pipe the envelope via stdin.",
        ),
        OperationError("import_file_not_found", "No file exists at the given --file path."),
        OperationError("import_file_not_valid_json", "The --file content (or piped stdin) was not valid JSON."),
    ),
    "gmail.import": (
        OperationError(
            "author_email_missing",
            "Your own email address (the top-level author_email) is required — supply it directly, "
            "or via --file/stdin as part of the {author_email, messages} envelope.",
        ),
        OperationError(
            "no_messages_provided",
            "No messages were supplied — provide --messages, --file, or pipe the envelope via stdin.",
        ),
        OperationError("import_file_not_found", "No file exists at the given --file path."),
        OperationError("import_file_not_valid_json", "The --file content (or piped stdin) was not valid JSON."),
    ),
    "reanalyze": (_UNKNOWN_SUBJECT,),
    "ingest": (_UNKNOWN_SOURCE, _SOURCE_NOT_ACTIVE),
    "curate": (
        OperationError("skipped_off", "While the toolkit is off, a curation tick is an inert no-op — never a partial run."),
    ),
    "feedback.add": (_UNKNOWN_SUBJECT,),
    "fact.correct": (_UNKNOWN_SUBJECT,),
    "fact.deprecate": (_UNKNOWN_FACT,),
    "review.resolve": (
        OperationError("invalid_status", "The status must be RESOLVED or DISMISSED."),
        _NO_OPEN_REVIEW,
    ),
    "gateway.configure": (
        OperationError("ineligible_data_class", "Raw or quarantined data can never be allowed to leave the machine, so it cannot be allowlisted."),
    ),
    "draft.validate": (
        OperationError("semantic_review_unavailable", "A high-stakes (semantic) review was requested but model egress is disabled; the deterministic checks still ran and the result is not marked validated."),
    ),
    # --- backend-dependent operations: honest LOCAL_ONLY / conflict refusals ---
    "profile.publish": (_LOCAL_ONLY_SKIP,),
    "profile.pull": (
        _LOCAL_ONLY_SKIP,
        OperationError("divergent_remote_head", "The remote history diverged from your last publish; the pull stops rather than force anything."),
    ),
    "profile.restore": (_LOCAL_ONLY_SKIP,),
    "profile.reconcile": (
        _LOCAL_ONLY_SKIP,
        OperationError("conflict_queued_for_review", "A conflicting correction or identity change is queued for your review, never auto-merged."),
    ),
    # --- lifecycle ---
    "portability.export": (
        _UNKNOWN_SUBJECT,
        OperationError("weak_passphrase", "The passphrase must be at least 8 characters; it is never stored."),
    ),
    "portability.import": (
        OperationError("archive_not_found", "No portable archive exists at that path."),
        OperationError("wrong_passphrase_or_tampered", "A wrong passphrase or a tampered/corrupt archive is refused; your local corrections are never overwritten."),
    ),
    "key.recover": (
        OperationError("unusable_recovery_material", "The supplied recovery material does not look like a usable recovery secret."),
    ),
    "key.rotate": (
        OperationError("unknown_purpose", "The key purpose must be 'content' or 'profile_pack'."),
    ),
    "erase": (
        OperationError("unknown_scope", "The erase scope must be one of the allowed granularities."),
    ),
    "rebuild": (_UNKNOWN_GENERATION,),
}

# A per-consequence phrase for the plain-language confirmation description (challenge/consent), so
# the operator learns *why* the action is gated, in their own terms.
_CONSEQUENCE_PHRASING: dict[str, str] = {
    "export": "sensitive: it writes your profile facts to a file you name",
    "erase": "destructive and irreversible: it permanently removes the scope you name",
    "profile.remote_bind": "shared: it binds a private backend that others you share it with could later read the encrypted pack from",
    "portability.export": "sensitive: it writes an encrypted, movable copy of your whole profile",
    "key.rotate": "irreversible: it destroys the previous key, so anything still encrypted under it can never be read again",
    "uninstall": "consequential: it removes the installed runtime (your profile, config, and keys are left untouched)",
}


def error_taxonomy(op: Operation) -> tuple[OperationError, ...]:
    """Ordered, de-duplicated, non-empty taxonomy of the failure modes ``op`` can surface. Order:
    the universal argument-validation error first, then the operation's explicit service-verified
    errors (in table order), then — for a consequential operation — the two challenge-gate errors.
    Never empty (the universal error guarantees at least one)."""
    out: list[OperationError] = [_INVALID_ARGUMENTS]
    seen: set[str] = {_INVALID_ARGUMENTS.code}

    def _add(err: OperationError) -> None:
        if err.code not in seen:
            out.append(err)
            seen.add(err.code)

    for err in _OP_ERRORS.get(op.name, ()):
        _add(err)
    if op.posture == Posture.CONSEQUENTIAL:
        _add(_CONFIRMATION_REQUIRED)
        _add(_CONFIRMATION_MISMATCH)
    return tuple(out)


# Placeholder VALUES are raw (unquoted) and free of apostrophes; synthesized_example() applies
# shlex.quote() uniformly, so an example is always a single valid, copy-pasteable shell invocation.
_PLACEHOLDER_BY_ARG: dict[str, str] = {
    "subject_id": "subj_abc123",
    "consumer_id": "demo-cli",
    "source_id": "src_abc123",
    "generation_id": "gen_abc123",
    "fact_id": "fact_abc123",
    "target_fact_id": "fact_abc123",
    "review_id": "rev_abc123",
    "canonical_root": "./my-notes",
    "destination": "./my-profile-export.md",
    "source": "./my-profile-export.ovtpack",
    "remote_url": "git@github.com:me/private-profile.git",
    "passphrase": "correct-horse-battery-staple",
    "recovery_material": "RECOVERY-XXXX-XXXX",
    "utterance": "that is not how I would say it",
    "request": "make this sound like me",
    "draft_text": "Hey team, quick update",
    "display_label": "operator",
    "key": "some_flag",
    "value": "true",
    "facet": "tone",
    "policy_name": "default",
    "reason": "operator correction",
}


def _placeholder(name: str, arg_type: ArgType, choices: tuple[str, ...] | None) -> str:
    if choices:
        return choices[0]
    if name in _PLACEHOLDER_BY_ARG:
        return _PLACEHOLDER_BY_ARG[name]
    if arg_type == ArgType.INT:
        return "10"
    if arg_type == ArgType.FLOAT:
        return "1.0"
    if arg_type == ArgType.JSON:
        return "[]"
    return f"<{name}>"


def synthesized_example(op: Operation) -> str:
    """A single valid, copy-pasteable CLI invocation derived from ``op``'s required arguments (the
    same ``--dashed`` flag mapping the CLI builder uses). Every value is ``shlex.quote``-d so spaces
    or shell-special characters never break parsing. Optional arguments are omitted for brevity.
    Used only when the registry declares no curated example for the operation."""
    parts = [f"operator-voice {op.cli_name}"]
    for arg in op.args:
        if not arg.required:
            continue
        flag = f"--{arg.name.replace('_', '-')}"
        if arg.type == ArgType.BOOL:
            parts.append(flag)
        else:
            parts.append(f"{flag} {shlex.quote(_placeholder(arg.name, arg.type, arg.choices))}")
    return " ".join(parts)


def worked_examples(op: Operation) -> tuple[str, ...]:
    """The curated examples if the registry declares any, else exactly one synthesized example.
    Guaranteed non-empty for every operation."""
    return op.examples if op.examples else (synthesized_example(op),)


def challenge_description(op: Operation) -> str | None:
    """A plain-language challenge/consent description for a CONSEQUENTIAL operation, else ``None``.
    Explains, in operator terms, why the action is gated and how the typed confirmation works."""
    if op.posture != Posture.CONSEQUENTIAL:
        return None
    why = _CONSEQUENCE_PHRASING.get(op.name, "consequential")
    return (
        f"`{op.name}` is {why}. The first time you run it, it makes **no change** and returns an "
        f"exact confirmation phrase; re-run it with `challenge_literal` set to that phrase to "
        f"actually proceed. Nothing happens until you do, and the phrase is specific to this "
        f"action and its target."
    )


__all__ = [
    "HELP_VERSION",
    "OperationError",
    "error_taxonomy",
    "synthesized_example",
    "worked_examples",
    "challenge_description",
]
