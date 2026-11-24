"""Optional owner admission for Dev-projected Skills configurations."""

from dataclasses import dataclass, field
import re
from typing import Callable

from .contracts import INPUT_MAX, REASONS, config, digest, fail, json_load, relative


def checked_digest(value):
    if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        fail("invalid_input")


def validate_input_diagnostics(value, inputs, projected_config):
    if type(value) is not dict or len(value) > 50000:
        fail("unavailable", 3)
    snapshot_states = {item["key"]: item["state"] for item in inputs}
    configured_keys = set()
    for root in projected_config["roots"]:
        key = "inventory/" + root["key"]
        configured_keys.add(key)
        if root["git"]:
            configured_keys.add(key + "/git")
        configured_keys.update(key + "/" + source["path"] for source in root["sources"])
    if snapshot_states.keys() | value.keys() != configured_keys:
        fail("unavailable", 3)
    for key, entry in value.items():
        if not isinstance(key, str) or not key.startswith("inventory/") or len(key) > 1024:
            fail("unavailable", 3)
        root, separator, path = key.removeprefix("inventory/").partition("/")
        relative(root)
        if len(root) > 128:
            fail("unavailable", 3)
        if separator:
            relative(path)
        if type(entry) is not dict or set(entry) != {"state", "reason"} or entry["reason"] not in REASONS:
            fail("unavailable", 3)
        state, reason = entry["state"], entry["reason"]
        if state not in {"omitted", "unavailable", "stale", "conflict"}:
            fail("unavailable", 3)
        if (state == "omitted") != (reason == "excluded"):
            fail("unavailable", 3)
        expected = {"stale": "stale", "conflict": "current"}.get(state)
        if snapshot_states.get(key) != expected:
            fail("unavailable", 3)
    if any(state == "stale" and value.get(key, {}).get("state") != "stale" for key, state in snapshot_states.items()):
        fail("unavailable", 3)
    return value


@dataclass(frozen=True)
class CheckoutAdmission:
    """A projection and owner-provided gates for one refresh.

    probe and commit receive the same Dev version that the receipt records.
    probe also receives the checkout and exact roles and paths for one read.
    commit receives the contributing checkouts and the final publication step.
    The owner revalidates live authority and holds its guard during each action.
    Physical qualification uses commit_current to recheck current checkout relationships
    after the receipt is prepared and before the snapshot is replaced.

    The exact projected configuration binds the full input set, including
    failures and policy omissions that have no snapshot record.
    """

    inventory_version: tuple[str, int, str]
    config_digest: str
    projection_digest: str
    skills_revision: str
    probe: Callable
    commit: Callable
    physical_binding_digest: str | None = None
    commit_current: Callable | None = None
    config_bytes: bytes = field(kw_only=True, repr=False)

    def validate(self):
        if not isinstance(self.inventory_version, tuple) or len(self.inventory_version) != 3:
            fail("invalid_input")
        policy, generation, inventory_digest = self.inventory_version
        if not isinstance(policy, str) or not policy.strip() or type(generation) is not int or not 0 < generation < 2**63:
            fail("invalid_input")
        checked_digest(inventory_digest)
        checked_digest(self.config_digest)
        checked_digest(self.projection_digest)
        if self.physical_binding_digest is not None:
            checked_digest(self.physical_binding_digest)
        if not isinstance(self.skills_revision, str) or re.fullmatch(r"[a-f0-9]{40}", self.skills_revision) is None:
            fail("invalid_input")
        if not callable(self.probe) or not callable(self.commit):
            fail("invalid_input")
        if self.commit_current is not None and not callable(self.commit_current):
            fail("invalid_input")
        if self.physical_binding_digest is not None and self.commit_current is None:
            fail("invalid_input")
        if (type(self.config_bytes) is not bytes or not 0 < len(self.config_bytes) <= INPUT_MAX
                or digest(self.config_bytes) != self.config_digest):
            fail("invalid_input")
        return config(json_load(self.config_bytes, INPUT_MAX))

    def read(self, checkout, locations, collect):
        return self.probe(self.inventory_version, checkout, locations, collect)

    def publish(self, checkouts, current_checkouts, replace):
        if self.commit_current is not None:
            return self.commit_current(self.inventory_version, checkouts, current_checkouts, replace)
        return self.commit(self.inventory_version, checkouts, lambda: replace(lambda: None))

    def receipt(self, result, observed_at, input_diagnostics):
        policy, generation, digest = self.inventory_version
        return {
            "schema": "ecosystem-index/refresh-receipt/v1",
            "inventory_policy": policy,
            "inventory_generation": generation,
            "inventory_digest": digest,
            "projected_config_digest": self.config_digest,
            "projection_manifest_digest": self.projection_digest,
            "physical_binding_digest": self.physical_binding_digest,
            "skills_revision": self.skills_revision,
            "snapshot_generation": result["generation"],
            "snapshot_digest": result["snapshot_digest"],
            "observed_at": observed_at,
            "result": result,
            "input_diagnostics": input_diagnostics,
        }
