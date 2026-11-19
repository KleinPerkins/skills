"""XDG Base Directory layout — build plan v3 §4/§5.1: "one generic product/service/registry/XDG
runtime." Every path an install touches is derived from exactly these three roots, honoring
``$XDG_CONFIG_HOME``/``$XDG_DATA_HOME``/``$XDG_STATE_HOME`` when set (macOS has no native
equivalent env vars, so this also matches the precedent set by ``chaos-scheduler``/AWA in this
same workspace, §OPERATING-MANUAL "XDG Base Directory Specification").
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "operator-voice"


def _xdg(env_var: str, default_subdir: str) -> Path:
    override = os.environ.get(env_var)
    if override:
        return Path(override).expanduser()
    return Path.home() / default_subdir


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    config_dir: Path
    data_dir: Path
    state_dir: Path

    @property
    def config_file(self) -> Path:
        return self.config_dir / "config.json"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "operator-voice.sqlite3"

    @property
    def backups_dir(self) -> Path:
        return self.state_dir / "backups"

    @property
    def receipt_path(self) -> Path:
        return self.state_dir / "install-receipt.json"

    @property
    def profile_pack_clone_dir(self) -> Path:
        return self.state_dir / "profile-pack-clone"

    @property
    def slack_export_dir(self) -> Path:
        """Fixed materialization target for ``slack.import`` and the ``slack_export`` adapter's
        ``canonical_root`` (§ OVT Slack Adapter). Created by :meth:`ensure` so ``source.add``'s
        registration guard — which expects ``canonical_root`` to already exist — is always
        satisfied by the time ``setup()`` registers this source."""
        return self.state_dir / "slack-export"

    @property
    def drive_export_dir(self) -> Path:
        """Fixed materialization target for ``drive.import`` and the ``drive_export`` adapter's
        ``canonical_root`` (§ docs/drive-adapter.md). Holds the timestamp-prefixed, one-file-per-
        revision Markdown `drive.import` writes after server-side owner + not-shared-drive
        verification. Created by :meth:`ensure` so ``source.add``'s registration guard — which
        expects ``canonical_root`` to already exist — is satisfied when ``setup()`` registers it."""
        return self.state_dir / "drive-export"

    @property
    def gmail_export_dir(self) -> Path:
        """Fixed materialization target for ``gmail.import`` and the ``gmail_export`` adapter's
        ``canonical_root`` (§ docs/gmail-adapter.md). Holds the timestamp-prefixed, one-file-per-
        message Markdown `gmail.import` writes after server-side author verification. Created by
        :meth:`ensure` so ``source.add``'s registration guard is satisfied when ``setup()`` registers it."""
        return self.state_dir / "gmail-export"

    def ensure(self) -> None:
        for d in (self.config_dir, self.data_dir, self.state_dir, self.backups_dir,
                  self.slack_export_dir, self.drive_export_dir, self.gmail_export_dir):
            d.mkdir(parents=True, exist_ok=True, mode=0o700)


def default_paths() -> RuntimePaths:
    return RuntimePaths(
        config_dir=_xdg("XDG_CONFIG_HOME", ".config") / APP_NAME,
        data_dir=_xdg("XDG_DATA_HOME", ".local/share") / APP_NAME,
        state_dir=_xdg("XDG_STATE_HOME", ".local/state") / APP_NAME,
    )


__all__ = ["RuntimePaths", "default_paths", "APP_NAME"]
