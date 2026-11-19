"""Intent aliases + router-off fallback — build plan v3 §6: "OVT works without an intent router or
a shared external MCP-bootstrap library." When no external intent router is installed, an agent
(or the skill) can call
:func:`resolve` directly with the operator's plain-language request; it does a small, deterministic
substring match against a hand-curated alias table and returns the single best-matching operation
name, or ``None`` if nothing matches confidently enough (never a guess — the caller should fall
back to the ``help`` operation's ranked-list behavior instead).

This is deliberately NOT the same algorithm as ``OperatorVoiceService.help`` (which ranks and
returns several candidates for a human to read): :func:`resolve` is for a caller that needs to act,
so it only returns a single operation when confident, and empty aliases lists are a design smell
this module's own test suite would catch."""

from __future__ import annotations

from operator_voice.domain.operations import OPERATIONS, OPERATIONS_BY_NAME

INTENTS_VERSION = "intents/v1"

# Each operation may have zero or more everyday phrasings. Curated, not learned — every phrase
# here was chosen because it plausibly maps to exactly one operation with no ambiguity.
ALIASES: dict[str, tuple[str, ...]] = {
    "help": ("what can you do", "how do i", "help me"),
    "status": ("how is this set up", "is this working", "what's the status"),
    "doctor": ("check everything is working", "run a health check", "diagnose"),
    "context.get": ("make this sound like me", "write this in my voice", "match my voice", "draft this for slack", "slack message in my voice"),
    "subject.insights": ("analyze how this person writes", "insights about a person", "how does this person communicate"),
    "subject.alias_add": ("link an account to this person", "add an identifier for this person"),
    "draft.validate": ("check this draft", "does this sound like me", "validate this draft"),
    "feedback.add": ("that's wrong", "don't say", "i actually meant", "that's not how i'd say it"),
    "fact.correct": ("correct this", "fix this fact"),
    "source.add": ("add a source", "start reading my", "add my chatgpt export", "add my claude export"),
    "ingest": ("scan for new", "pick up new messages", "update from my source"),
    "curate": ("curate now", "run curation", "process my sources now", "catch up now"),
    "curation.status": ("curation status", "how is curation going", "when did you last check", "is it keeping up"),
    "learning.status": ("are you still learning me", "how much have you learned", "learning status", "did my corrections stick"),
    "export": ("export my profile", "give me a readable copy", "show me everything you know"),
    "erase": ("delete everything", "forget everything", "erase my data", "wipe my profile"),
    "off": ("turn this off", "stop watching", "disable this", "pause everything"),
    "on": ("turn this back on", "resume", "enable this again"),
    "profile.publish": ("back up my profile", "sync my profile", "publish my profile"),
    "profile.sync_status": ("is my profile backed up", "is my profile synced"),
    "profile.reconcile": ("reconcile my profile", "reconcile across machines", "merge my profile from another machine", "resolve a profile conflict"),
    "portability.export": ("move my profile to another machine", "make a portable copy of my profile", "portable profile export"),
    "portability.import": ("import a portable profile", "load my profile from a file", "bring my profile to this machine"),
    "dashboard.data": ("show the dashboard", "dashboard data", "dashboard snapshot"),
    "setup": ("get started", "set this up", "install this"),
    "slack.import": ("harvest slack", "pick up my slack", "refresh slack voice", "sync slack messages", "import my slack"),
    "slack.status": ("slack voice status", "is slack set up", "when did you last read slack"),
    "drive.import": (
        "harvest drive", "pick up my drive", "refresh drive voice", "sync my google docs",
        "import my drive", "pull my docs into voice", "pull my google docs",
    ),
    "drive.status": ("drive voice status", "is drive set up", "when did you last read drive"),
    "gmail.import": (
        "harvest gmail", "pick up my sent mail", "refresh gmail voice", "sync my sent email",
        "import my gmail",
    ),
    "gmail.status": (
        "gmail voice status", "is gmail set up", "when did you last read gmail",
        "check if my sent mail is synced", "is my sent mail synced",
    ),
    "google.status": (
        "google voice status", "is google set up", "when did you last read google",
        "drive and gmail status", "google freshness", "refresh my google voice",
        "is my google stuff synced",
    ),
}


def resolve(utterance: str) -> str | None:
    text = utterance.strip().lower()
    if not text:
        return None
    matches = [name for name, phrases in ALIASES.items() if any(phrase in text for phrase in phrases)]
    unique = sorted(set(matches))
    if len(unique) == 1:
        return unique[0]
    return None  # ambiguous or no match — caller should fall back to `help`


def known_operation_names_with_aliases() -> list[str]:
    return sorted(ALIASES.keys())


assert set(ALIASES.keys()).issubset(OPERATIONS_BY_NAME.keys()), "intents.ALIASES references an unknown operation name"

__all__ = ["ALIASES", "resolve", "known_operation_names_with_aliases"]
