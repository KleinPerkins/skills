"""Zero-link mechanical enforcement for this capability (the plan's own required check).

The repo's shared `.github/scripts/verify-skills.sh` already scans all of global/ and
local/ for the *other* half of this repo's zero-link boundary (the sibling governed-repo
family this skill must never reference) — that half is deliberately NOT duplicated here,
both because it is already covered and because duplicating those literal tokens in this
file's own source would trip that same shared scanner on this file. This test instead
covers the half nothing else checks: workspace-safety-tool-specific tokens/paths. The
global payload must stay host-agnostic, so none of these may appear anywhere save-game
writes (see this build's EVIDENCE.md, which deliberately describes its own build
environment generically rather than naming that tool).

This file's own source is excluded from the walk (via THIS_FILE) because it must contain
the forbidden literals verbatim as pattern strings in order to check for them elsewhere.
"""

import re
import unittest
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
THIS_FILE = Path(__file__).resolve()

EXCLUDED_DIR_NAMES = {".git", "__pycache__"}

FORBIDDEN_PATTERNS = {
    "standalone 'awa' token": re.compile(r"\bawa\b", re.IGNORECASE),
    ".local/share/awa path": re.compile(r"\.local/share/awa", re.IGNORECASE),
    "awa_durability literal": re.compile(r"awa_durability", re.IGNORECASE),
    "Commit/Retain/Mixed/Close choice-word set": re.compile(
        r"commit\s*[/,|]\s*retain\s*[/,|]\s*mixed\s*[/,|]\s*close", re.IGNORECASE
    ),
}


def _iter_scannable_files():
    for path in sorted(SKILL_DIR.rglob("*")):
        if not path.is_file():
            continue
        if path.resolve() == THIS_FILE:
            continue
        if any(part in EXCLUDED_DIR_NAMES for part in path.relative_to(SKILL_DIR).parts):
            continue
        yield path


def _read_text_or_none(path: Path):
    try:
        return path.read_text(encoding="utf-8", errors="strict")
    except (UnicodeDecodeError, OSError):
        return None  # binary/unreadable: no textual token to find either way


class TestZeroLink(unittest.TestCase):
    def test_no_forbidden_tokens_in_save_game_tree(self):
        hits = []
        for path in _iter_scannable_files():
            text = _read_text_or_none(path)
            if not text:
                continue
            for label, pattern in FORBIDDEN_PATTERNS.items():
                if pattern.search(text):
                    hits.append(f"{path.relative_to(SKILL_DIR)} ({label})")
        self.assertFalse(hits, f"forbidden token(s) found: {hits}")

    def test_exclusion_of_this_file_is_not_vacuous(self):
        # Proves the self-exclusion is doing real work rather than accidentally
        # excluding everything (which would make the assertion above pass trivially).
        own_text = THIS_FILE.read_text(encoding="utf-8")
        self.assertTrue(any(p.search(own_text) for p in FORBIDDEN_PATTERNS.values()))
        scanned = {p.resolve() for p in _iter_scannable_files()}
        self.assertNotIn(THIS_FILE, scanned)
        self.assertGreater(len(scanned), 5)


if __name__ == "__main__":
    unittest.main()
