"""Client capability facts for save-game discovery and manual compaction.

These are descriptive adapters only. They do not invoke a client, install a
link, run compaction, or claim that live client discovery has succeeded.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Optional, Tuple


OBSERVATIONAL_ONLY = "observational_only"
CAN_BLOCK = "can_block"
HALT_ONLY_NO_BLOCK = "halt_only_no_block"
PRE_COMPACTION_CAPABILITY_CLASSES = frozenset(
    {OBSERVATIONAL_ONLY, CAN_BLOCK, HALT_ONLY_NO_BLOCK}
)

CODEX_ACCEPTANCE_STATUS = (
    "exposed via legacy path, acceptance unverified — pending live discovery canary"
)
LIVE_CANARY_REQUIRED_STATUS = (
    "disk exposure configured; acceptance requires a live discovery canary"
)


@dataclass(frozen=True)
class ClientCapability:
    """Static client facts verified in the accepted plan's evidence ledger."""

    client_id: str
    discovery_path: str
    explicit_invocation: str
    manual_compaction_command: str
    pre_compaction_capability: str
    acceptance_status: str
    documented_discovery_path: Optional[str] = None

    def resolved_discovery_path(self, home: Optional[Path] = None) -> Path:
        """Resolve this adapter's configured exposure path under ``home``."""

        home_path = Path.home() if home is None else Path(home)
        prefix = "~/"
        if not self.discovery_path.startswith(prefix):
            raise ValueError(
                f"discovery path must be user-relative: {self.discovery_path!r}"
            )
        return home_path / self.discovery_path[len(prefix) :]


_CLIENT_CAPABILITIES = {
    "cursor": ClientCapability(
        client_id="cursor",
        discovery_path="~/.cursor/skills/save-game",
        explicit_invocation="/save-game",
        manual_compaction_command="/summarize",
        pre_compaction_capability=OBSERVATIONAL_ONLY,
        acceptance_status=LIVE_CANARY_REQUIRED_STATUS,
    ),
    "claude": ClientCapability(
        client_id="claude",
        discovery_path="~/.claude/skills/save-game",
        explicit_invocation="/save-game",
        manual_compaction_command="/compact",
        pre_compaction_capability=CAN_BLOCK,
        acceptance_status=LIVE_CANARY_REQUIRED_STATUS,
    ),
    "codex": ClientCapability(
        client_id="codex",
        discovery_path="~/.codex/skills/save-game",
        documented_discovery_path="~/.agents/skills/save-game",
        explicit_invocation="$save-game",
        manual_compaction_command="/compact",
        pre_compaction_capability=HALT_ONLY_NO_BLOCK,
        acceptance_status=CODEX_ACCEPTANCE_STATUS,
    ),
}

CLIENT_CAPABILITIES: Mapping[str, ClientCapability] = MappingProxyType(
    _CLIENT_CAPABILITIES
)


def client_ids() -> Tuple[str, ...]:
    """Return supported client IDs in stable display order."""

    return tuple(CLIENT_CAPABILITIES)


def list_clients() -> Tuple[ClientCapability, ...]:
    """Return every supported client capability record."""

    return tuple(CLIENT_CAPABILITIES.values())


def get_client(client_id: str) -> ClientCapability:
    """Return one client capability, rejecting unsupported client IDs."""

    normalized = client_id.strip().lower()
    try:
        return CLIENT_CAPABILITIES[normalized]
    except KeyError as exc:
        raise KeyError(f"unsupported save-game client: {client_id!r}") from exc


def discovery_path_for(client_id: str, home: Optional[Path] = None) -> Path:
    """Resolve a client's configured discovery link under ``home``."""

    return get_client(client_id).resolved_discovery_path(home)


def codex_acceptance_status() -> str:
    """Return the frozen, deliberately non-parity Codex acceptance statement."""

    return CODEX_ACCEPTANCE_STATUS
