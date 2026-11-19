"""Durable host-delegated daily control plane; no connector, model or scheduler.

Only the host can attest exhaustive fetch completion. The encrypted journal stores
opaque continuation metadata and aggregates, never writing samples or credentials.
"""
from contextlib import contextmanager
import base64
from datetime import datetime, timedelta
import fcntl
import hashlib
import hmac
import json
import os
from pathlib import Path
import time
import uuid
from zoneinfo import ZoneInfo

from operator_voice.persistence.atomic import atomic_write
from operator_voice.persistence.crypto import aead_decrypt, aead_encrypt

INTEGRATIONS = ("slack", "gmail", "drive")
OUTCOMES = {"success", "incomplete", "transient_error", "auth_error", "unavailable", "identity_error", "paused"}
RETRY_SECONDS = 900
LEASE_SECONDS = 7200
STALE_SECONDS = 48 * 3600
_AAD = b"operator-voice:daily-control/v1"


class CycleError(ValueError):
    pass


class DailyCycle:
    def __init__(self, state_dir, crypto):
        self.directory = Path(state_dir)
        self.path = self.directory / "daily-cycle.enc"
        self.crypto = crypto

    @contextmanager
    def locked(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(self.directory / ".daily-cycle.lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise CycleError("busy") from exc
            yield
        finally:
            os.close(fd)

    def read(self):
        if not self.path.exists():
            return {"schema": "daily-cycle/v1", "enabled": False}
        try:
            envelope = json.loads(self.path.read_bytes())
            dek = self.crypto.unwrap_dek(base64.b64decode(envelope["wrapped_key"]))
            state = json.loads(aead_decrypt(dek, base64.b64decode(envelope["ciphertext"]), _AAD))
            if state.get("schema") != "daily-cycle/v1":
                raise ValueError()
            return state
        except Exception as exc:
            raise CycleError("daily control state cannot be verified; stop and inspect") from exc

    def save(self, state):
        dek, wrapped = self.crypto.wrap_new_dek()
        encrypted = aead_encrypt(dek, json.dumps(state, sort_keys=True).encode(), _AAD)
        atomic_write(self.path, json.dumps({"wrapped_key": base64.b64encode(wrapped).decode(),
                                           "ciphertext": base64.b64encode(encrypted).decode()}).encode())

    def identity_hash(self, integration, identity):
        if integration not in INTEGRATIONS or not isinstance(identity, str) or not identity.strip():
            raise CycleError("valid integration and identity required")
        normalized = identity.strip() if integration == "slack" else identity.strip().casefold()
        return hmac.new(self.crypto.hmac_secret, ("daily-account/v1:" + integration + ":" + normalized).encode(), hashlib.sha256).hexdigest()

    def verify_identity(self, integration, identity):
        actual = self.identity_hash(integration, identity)
        expected = self.read().get("identities", {}).get(integration)
        if expected and not hmac.compare_digest(expected, actual):
            raise CycleError("connected identity differs from daily enrollment; operator review required")
        return expected is not None

    @staticmethod
    def slot(state, now):
        local = datetime.fromtimestamp(now, ZoneInfo(state["timezone"]))
        due = local.replace(hour=state["hour"], minute=0, second=0, microsecond=0)
        if local < due:
            due -= timedelta(days=1)
        return due.date().isoformat(), due.timestamp()

    def configure(self, *, timezone, hour, identities, now=None, enabled=True):
        now = time.time() if now is None else now
        ZoneInfo(timezone)
        if type(hour) is not int or not 0 <= hour <= 23 or set(identities) != set(INTEGRATIONS):
            raise CycleError("hour 0..23 and all three connected identities required")
        hashes = {k: self.identity_hash(k, v) for k, v in identities.items()}
        with self.locked():
            state = self.read()
            if state.get("identities") and state["identities"] != hashes:
                raise CycleError("enrolled identity cannot be silently replaced")
            state.update(timezone=timezone, hour=hour, identities=hashes, enabled=enabled)
            state.setdefault("configured_at", now)
            state.setdefault("last_slot", self.slot(state, now)[0])
            state.setdefault("sources", {k: {"last_success_at": None, "since": None, "outcome": "never",
                                               "failure_since": None, "notified": [], "checkpoint": {}}
                                          for k in INTEGRATIONS})
            self.save(state)
        return {"status": "configured", "enabled": enabled, "timezone": timezone, "hour": hour}

    def _status(self, state, now, conflict=False):
        if not state.get("enabled"):
            return {"status": "disabled", "due": False, "attention": [], "sources": {}}
        slot, _ = self.slot(state, now)
        active = state.get("active")
        busy = bool(active and active["lease_until"] > now)
        retry_due = state.get("retry_due")
        due = not busy and (slot > state["last_slot"] or bool(active)
                           or (retry_due is not None and retry_due <= now))
        attention = []
        sources = {}
        for name, source in state["sources"].items():
            age = now - (source["last_success_at"] or state["configured_at"])
            reason = source["outcome"] if source["outcome"] in {"auth_error", "identity_error"} else "stale" if age >= STALE_SECONDS else None
            if source["outcome"] == "paused":
                reason = None
            if reason and reason not in source["notified"]:
                attention.append(name + ":" + reason)
            sources[name] = {k: source.get(k) for k in ("last_success_at", "outcome", "counts")}
        for name, health in state.get("health", {}).items():
            if health.get("since") is not None and (health["reason"] == "conflict" or now - health["since"] >= STALE_SECONDS):
                notice = name + ":" + health["reason"]
                if not health.get("notified"):
                    attention.append(notice)
        prior_publication = state.get("health", {}).get("publication", {})
        if conflict and not (prior_publication.get("reason") == "conflict" and prior_publication.get("notified")):
            if "publication:conflict" not in attention:
                attention.append("publication:conflict")
        return {"status": "busy" if busy else "due" if due else "waiting", "due": due,
                "attention": attention, "sources": sources, "retry_due": retry_due,
                "last_cycle": state.get("last_cycle"), "timezone": state["timezone"], "hour": state["hour"]}

    def status(self, *, now=None, conflict=False):
        return self._status(self.read(), time.time() if now is None else now, conflict)

    def begin(self, *, now=None, force=False):
        now = time.time() if now is None else now
        try:
            with self.locked():
                state = self.read()
                status = self._status(state, now)
                if not state.get("enabled"):
                    return {"status": "disabled"}
                if status["status"] == "busy":
                    return {"status": "busy"}
                if not force and not status["due"]:
                    return {"status": "not_due"}
                slot, _ = self.slot(state, now)
                active = state.get("active")
                recovering = bool(active)
                new_day = slot > state["last_slot"]
                backlog = any(v.get("attempt_outcome") in {"pending", "incomplete"}
                              for v in state["sources"].values())
                if (force or (new_day and not backlog)) and not recovering:
                    integrations = list(INTEGRATIONS)
                    state["last_slot"] = slot
                    state["window_end"] = now
                    state["retry_used"] = False
                    state["window_totals"] = {"documents_new": 0, "observations_new": 0, "profile_changed": False}
                    state["window_counted"] = False
                    for source in state["sources"].values():
                        source["attempt_outcome"] = "pending"
                        # A new window replays from the last completed checkpoint. Tokens
                        # from an abandoned failed window cannot attest its expanded bound.
                        source["checkpoint"] = {}
                else:
                    integrations = [k for k, v in state["sources"].items()
                                    if v.get("attempt_outcome") in {"pending", "incomplete", "transient_error"}]
                    if not recovering:
                        state["retry_used"] = True
                state["retry_due"] = None
                run_id = uuid.uuid4().hex
                state["active"] = {"run_id": run_id, "lease_until": now + LEASE_SECONDS,
                                   "integrations": integrations}
                self.save(state)
                local = datetime.fromtimestamp(now, ZoneInfo(state["timezone"]))
                return {"status": "started", "run_id": run_id, "integrations": integrations,
                        "window_end": state["window_end"], "weekly_audit": local.weekday() == 4,
                        "resume": {k: {"since": state["sources"][k]["since"],
                                        "checkpoint": state["sources"][k]["checkpoint"]} for k in integrations}}
        except CycleError as exc:
            if str(exc) == "busy":
                return {"status": "busy"}
            raise

    @staticmethod
    def require_owner(state, run_id, now):
        active = state.get("active")
        if not active or active["run_id"] != run_id or active["lease_until"] <= now:
            raise CycleError("cycle lease is absent or expired")

    def record(self, run_id, integration, outcome, *, counts=None, checkpoint=None, now=None):
        now = time.time() if now is None else now
        counts = counts or {}
        checkpoint = checkpoint or {}
        if integration not in INTEGRATIONS or outcome not in OUTCOMES:
            raise CycleError("invalid integration or outcome")
        if any(k not in {"fetched", "imported", "duplicates", "filtered", "pages"}
               or type(v) is not int or v < 0 for k, v in counts.items()):
            raise CycleError("counts must be allowed nonnegative aggregates")
        # Provider-owned opaque progress, encrypted at rest; no source content accepted.
        allowed = {"page_token", "cursor", "folder_queue", "folder_id", "phase", "window_start", "window_end"}
        if not isinstance(checkpoint, dict) or set(checkpoint) - allowed or len(json.dumps(checkpoint)) > 65536:
            raise CycleError("invalid continuation checkpoint")
        with self.locked():
            state = self.read()
            self.require_owner(state, run_id, now)
            if integration not in state["active"]["integrations"]:
                raise CycleError("integration is not part of this cycle")
            source = state["sources"][integration]
            source.update(outcome=outcome, attempt_outcome=outcome, counts=counts, checkpoint=checkpoint)
            if outcome == "success":
                source.update(last_success_at=now, since=state["window_end"], failure_since=None,
                              notified=[], checkpoint={})
            else:
                source["failure_since"] = source["failure_since"] or now
            state["active"]["lease_until"] = now + LEASE_SECONDS
            self.save(state)
        return {"status": "recorded", "integration": integration, "outcome": outcome}

    def finish(self, run_id, *, curation, now=None):
        now = time.time() if now is None else now
        with self.locked():
            state = self.read()
            self.require_owner(state, run_id, now)
            if callable(curation):
                curation = curation()
                now = time.time()
            outcomes = [v.get("attempt_outcome") for v in state["sources"].values()]
            unfinished = any(v in {"pending", "incomplete"} for v in outcomes)
            transient = "transient_error" in outcomes
            publication = str(curation.get("publish_status", ""))
            backlog = bool(curation.get("pending_continuation"))
            pending = publication == "PENDING_PUBLICATION"
            publish_failed = publication.startswith("failed:")
            failed = bool(curation.get("sources_failed")) or publish_failed
            retry = unfinished or backlog or ((transient or failed or pending) and not state.get("retry_used"))
            state["retry_due"] = now + RETRY_SECONDS if retry else None
            totals = state.setdefault("window_totals", {"documents_new": 0, "observations_new": 0, "profile_changed": False})
            for key in ("documents_new", "observations_new"):
                totals[key] += int(curation.get(key, 0))
            changed = totals["profile_changed"] = bool(totals["profile_changed"] or curation.get("generation_ids") or curation.get("profile_changed"))
            successful = not (unfinished or transient or failed or backlog or pending) and publication != "CONFLICT" and all(v in {"success", "paused"} for v in outcomes)
            if successful and not state.get("window_counted"):
                state["unchanged_cycles"] = state.get("unchanged_cycles", 0) + 1 if not changed else 0
                state["window_counted"] = True
            elif not successful:
                state["unchanged_cycles"] = 0
            health = state.setdefault("health", {})
            for name, reason in (("curation", "failed" if curation.get("sources_failed") else "unfinished" if backlog else None),
                                 ("publication", "conflict" if publication == "CONFLICT" else "unfinished" if pending or publish_failed else None)):
                if reason is None:
                    health.pop(name, None)
                elif health.get(name, {}).get("reason") != reason:
                    health[name] = {"reason": reason, "since": now, "notified": False}
            state["last_cycle"] = {"finished_at": now, "incomplete_sources": sum(v not in {"success", "paused"} for v in outcomes),
                                   "curation_failed": bool(curation.get("sources_failed")),
                                   "curation_pending": backlog,
                                   "publication_pending": pending, "publication_failed": publish_failed,
                                   "profile_changed": changed, "unchanged_cycles": state["unchanged_cycles"],
                                   "documents_new": totals["documents_new"],
                                   "observations_new": totals["observations_new"]}
            state["active"] = None
            self.save(state)
        return self.status(now=now)

    def acknowledge(self, notices, *, now=None, conflict=False):
        now = time.time() if now is None else now
        with self.locked():
            state = self.read()
            allowed = self._status(state, now, conflict)["attention"]
            if not isinstance(notices, list) or any(n not in allowed for n in notices):
                raise CycleError("only currently due notices can be acknowledged")
            for notice in notices:
                integration, reason = notice.split(":")
                if integration in INTEGRATIONS:
                    state["sources"][integration]["notified"].append(reason)
                else:
                    state.setdefault("health", {})[integration] = {"reason": reason, "since": now, "notified": True}
            self.save(state)
        return {"status": "acknowledged", "count": len(notices)}
