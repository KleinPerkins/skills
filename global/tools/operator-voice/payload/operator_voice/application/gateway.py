"""The model gateway — build plan §4/§6, D7 + §13 M2 worklist 4.

"Deterministic kernel plus optional gateway: model calls never occur inside the kernel. The
gateway is injected, disabled by default, policy-gated, cancellation-aware, and metadata-audited."

M1 shipped this seam **disabled and unused**. M2 (this module) adds:
  * provider adapters behind the gateway (a bundled no-network ``local-deterministic`` provider,
    plus a generic :class:`CallableProvider` so an operator can inject any local/remote adapter
    through the same protocol — OVT bundles no network client);
  * a layered, fail-closed egress policy: provider/model/data-class allowlist; raw/quarantined
    text is never eligible; a SEPARATE default-deny ``EXTERNAL`` switch that stays denied even when
    operator egress is enabled (enabling operator egress does not enable EXTERNAL egress, §D17);
  * a metadata-only :class:`~operator_voice.domain.models.ModelCallRecord` per call attempt with
    ZERO payload retention (the signal is held in memory only, never persisted);
  * cancellation-awareness (a live off switch closes egress) and bounded failure/timeout
    degradation (a slow/failing provider degrades to a typed outcome, never a crash or a fabricated
    result).

The deterministic kernel still never imports or calls this module (enforced by
``tests/unit/test_kernel_purity.py``); only the explicitly opt-in semantic-review path in the
application service may call :meth:`ModelGateway.call`, and only after policy passes.
"""

from __future__ import annotations

import concurrent.futures
import enum
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Protocol

from operator_voice.domain.models import GatewayConfig

GATEWAY_VERSION = "gateway/v2"

# Data classes that may NEVER egress to a model under any policy (§4/§6: "quarantined/raw text is
# never eligible"). Checked before every other gate, fail-closed.
INELIGIBLE_DATA_CLASSES: frozenset[str] = frozenset({"raw", "quarantined"})
# The data class denoting an EXTERNAL-subject-derived signal. Gated by the SEPARATE external switch.
EXTERNAL_DATA_CLASS = "external"


class GatewayDisabledError(RuntimeError):
    """Raised when a disabled gateway is invoked with the legacy ``call()`` contract. Preserved from
    M1 so a still-disabled instance fails loudly rather than silently returning a fabricated result.
    The M2 policy path returns a typed DENIED_* outcome instead of raising (so a caller can degrade
    gracefully); this exception remains the behavior of the historical enabled=False fast-path."""


class GatewayOutcome(str, enum.Enum):
    SUCCESS = "SUCCESS"
    DENIED_DISABLED = "DENIED_DISABLED"                # operator egress off
    DENIED_PROVIDER = "DENIED_PROVIDER"                # provider not in allowlist / not configured
    DENIED_MODEL = "DENIED_MODEL"                      # model not in allowlist / not configured
    DENIED_DATA_CLASS = "DENIED_DATA_CLASS"            # data class not in allowed_data_classes
    DENIED_INELIGIBLE = "DENIED_INELIGIBLE"            # raw/quarantined text is never eligible
    DENIED_EXTERNAL_EGRESS = "DENIED_EXTERNAL_EGRESS"  # separate EXTERNAL switch is off
    CANCELLED = "CANCELLED"                            # live off switch closed egress
    TIMEOUT = "TIMEOUT"                                # provider exceeded the bounded deadline
    PROVIDER_ERROR = "PROVIDER_ERROR"                  # provider raised; degrade, never crash

    @property
    def allowed(self) -> bool:
        return self is GatewayOutcome.SUCCESS


@dataclass(frozen=True, slots=True)
class GatewayCallRequest:
    """A minimum-necessary, typed, already-escaped signal envelope (§6). ``is_external`` marks a
    signal derived from an EXTERNAL subject; such signals are gated by the separate EXTERNAL switch
    regardless of ``data_class``."""

    purpose: str
    data_class: str
    provider: str
    model: str
    signal: str
    is_external: bool = False


@dataclass(frozen=True, slots=True)
class GatewayDecision:
    outcome: GatewayOutcome
    reason: str = ""


@dataclass(frozen=True, slots=True)
class GatewayCallResult:
    outcome: str
    text: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.outcome == GatewayOutcome.SUCCESS.value


class Provider(Protocol):
    """A model provider adapter. OVT bundles only the no-network ``local-deterministic`` provider;
    any local/remote adapter (an operator-configured HTTP client, an on-device model, ...) satisfies
    this protocol and is injected — never bundled — so the default posture ships no network client."""

    name: str

    def models(self) -> tuple[str, ...]: ...

    def complete(self, *, model: str, signal: str, purpose: str) -> str: ...


class LocalDeterministicProvider:
    """A bundled, no-network provider used for tests/dev. It performs a deterministic, purely-local
    transformation of the signal (never leaves the machine), so the whole gated egress path can be
    exercised without any real external egress."""

    name = "local-deterministic"

    def models(self) -> tuple[str, ...]:
        return ("review-v0",)

    def complete(self, *, model: str, signal: str, purpose: str) -> str:
        # Deterministic, content-free-ish echo suitable for a semantic-review hypothesis. Never
        # persisted (zero payload retention); returned to the in-memory caller only.
        return f"[local-deterministic:{model}] reviewed({purpose}): {len(signal)} chars"


class CallableProvider:
    """Adapter that wraps an arbitrary callable as a :class:`Provider` (operator-injected local or
    remote client). Bundles no transport itself."""

    def __init__(self, name: str, models: tuple[str, ...], fn: Callable[[str, str, str], str]):
        self.name = name
        self._models = models
        self._fn = fn

    def models(self) -> tuple[str, ...]:
        return self._models

    def complete(self, *, model: str, signal: str, purpose: str) -> str:
        return self._fn(model, signal, purpose)


def default_provider_registry() -> dict[str, Provider]:
    p = LocalDeterministicProvider()
    return {p.name: p}


class ModelGateway:
    """The one injection seam the application service holds for an optional model gateway.

    Constructed from persisted :class:`GatewayConfig` (both egress switches default OFF). ``enabled``
    mirrors ``config.operator_egress_enabled`` for backward-compatible status checks. Policy is
    evaluated fail-closed in :meth:`evaluate`; :meth:`call` runs a provider only after policy passes,
    under a bounded deadline, and returns a typed outcome on cancel/timeout/error."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        config: Optional[GatewayConfig] = None,
        providers: Optional[dict[str, Provider]] = None,
        is_off: Optional[Callable[[], bool]] = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.config = config if config is not None else GatewayConfig(operator_egress_enabled=enabled)
        # `enabled` is derived from operator egress so a single source (config) drives status.
        self.enabled = bool(self.config.operator_egress_enabled)
        self.providers = providers if providers is not None else default_provider_registry()
        self._is_off = is_off or (lambda: False)
        self._clock = clock

    def status(self) -> dict[str, object]:
        return {
            "gateway_version": GATEWAY_VERSION,
            "enabled": self.enabled,
            "external_egress_enabled": bool(self.config.external_egress_enabled),
            "provider": self.config.provider,
            "model": self.config.model,
            "allowed_data_classes": list(self.config.allowed_data_classes),
        }

    def evaluate(self, request: GatewayCallRequest) -> GatewayDecision:
        """Pure, fail-closed policy decision — NO provider call, NO I/O. Order matters: the
        never-eligible and default-deny gates come before provider/model checks so a
        raw/quarantined or un-approved-EXTERNAL signal is denied even if the provider matches."""
        cfg = self.config
        # Case/whitespace-normalize the data class before EVERY gate so a mixed-case label
        # (e.g. "Raw", "EXTERNAL") can never dodge the never-eligible or EXTERNAL default-deny
        # checks — fail closed regardless of how the class was spelled (security-review hardening).
        dc = (request.data_class or "").strip().lower()
        allowlist = {c.strip().lower() for c in cfg.allowed_data_classes}
        if dc in INELIGIBLE_DATA_CLASSES:
            return GatewayDecision(GatewayOutcome.DENIED_INELIGIBLE, "raw/quarantined text is never eligible for egress")
        if not cfg.operator_egress_enabled:
            return GatewayDecision(GatewayOutcome.DENIED_DISABLED, "operator model egress is disabled")
        # SEPARATE EXTERNAL switch (§D17): enabling operator egress does not enable EXTERNAL egress.
        if (request.is_external or dc == EXTERNAL_DATA_CLASS) and not cfg.external_egress_enabled:
            return GatewayDecision(
                GatewayOutcome.DENIED_EXTERNAL_EGRESS,
                "EXTERNAL-subject egress is a separate switch and is disabled",
            )
        if dc not in allowlist:
            return GatewayDecision(GatewayOutcome.DENIED_DATA_CLASS, f"data class {request.data_class!r} not in allowlist")
        if not cfg.provider or request.provider != cfg.provider or request.provider not in self.providers:
            return GatewayDecision(GatewayOutcome.DENIED_PROVIDER, f"provider {request.provider!r} not approved/available")
        provider = self.providers[request.provider]
        if not cfg.model or request.model != cfg.model or request.model not in provider.models():
            return GatewayDecision(GatewayOutcome.DENIED_MODEL, f"model {request.model!r} not approved/available")
        return GatewayDecision(GatewayOutcome.SUCCESS)

    def call(self, request: GatewayCallRequest) -> GatewayCallResult:
        """Legacy-compatible entrypoint. When the gateway is disabled it raises
        :class:`GatewayDisabledError` (M1 contract). When enabled it evaluates policy and, only on
        allow, runs the provider under a bounded deadline. The transient signal is never persisted
        (zero payload retention); this method returns metadata + the in-memory result text only."""
        if not self.enabled:
            raise GatewayDisabledError(
                "model gateway is disabled; no provider is configured (operator egress is off)"
            )
        result, _ = self.attempt(request)
        return result

    def attempt(self, request: GatewayCallRequest) -> tuple[GatewayCallResult, GatewayDecision]:
        """Policy-evaluate then (on allow) invoke the provider. Returns (result, decision) so the
        caller can persist a metadata-only ModelCallRecord for EVERY attempt, including denials.
        Never raises for policy/timeout/provider failures — always a typed outcome."""
        started = self._clock()
        decision = self.evaluate(request)
        if not decision.outcome.allowed:
            return self._result(request, decision.outcome, started, text=None), decision
        # Cancellation: a live off switch closes egress even after policy passes.
        if self._is_off():
            return self._result(request, GatewayOutcome.CANCELLED, started, text=None), decision

        provider = self.providers[request.provider]
        timeout_s = max(0.001, self.config.timeout_ms / 1000.0)
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                future = ex.submit(provider.complete, model=request.model, signal=request.signal, purpose=request.purpose)
                try:
                    text = future.result(timeout=timeout_s)
                except concurrent.futures.TimeoutError:
                    future.cancel()
                    return self._result(request, GatewayOutcome.TIMEOUT, started, text=None), decision
        except Exception:  # provider raised — degrade, never propagate a provider fault
            return self._result(request, GatewayOutcome.PROVIDER_ERROR, started, text=None), decision
        return self._result(request, GatewayOutcome.SUCCESS, started, text=text), decision

    def _result(
        self, request: GatewayCallRequest, outcome: GatewayOutcome, started: float, *, text: Optional[str]
    ) -> GatewayCallResult:
        duration_ms = int((self._clock() - started) * 1000)
        return GatewayCallResult(
            outcome=outcome.value,
            text=text if outcome.allowed else None,
            metadata={
                "provider": request.provider, "model": request.model, "data_class": request.data_class,
                "purpose": request.purpose, "duration_ms": duration_ms,
                "cancelled": outcome is GatewayOutcome.CANCELLED,
                "gateway_version": GATEWAY_VERSION,
            },
        )


# The one shared disabled instance the service defaults to when the caller injects no gateway and no
# config is available — never `None`, so `service.gateway.status()` always answers.
DISABLED_GATEWAY = ModelGateway(enabled=False)


def default_gateway() -> ModelGateway:
    return DISABLED_GATEWAY


def gateway_from_config(
    config: GatewayConfig,
    *,
    providers: Optional[dict[str, Provider]] = None,
    is_off: Optional[Callable[[], bool]] = None,
) -> ModelGateway:
    """Build a gateway reflecting persisted operator policy. A fresh/disabled config yields a
    disabled gateway (enabled=False), identical in behavior to :data:`DISABLED_GATEWAY`."""
    return ModelGateway(
        enabled=config.operator_egress_enabled, config=config, providers=providers, is_off=is_off
    )
