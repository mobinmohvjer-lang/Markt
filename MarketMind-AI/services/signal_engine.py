"""
services/signal_engine.py

Defines `SignalEngine` -- Services Part 2A + Part 2B.

`SignalEngine` is a `BaseService` that publishes an already-produced
`core.entities.signal.Signal` as an
`events.event_types.signal_generated.SignalGenerated` event through an
injected `events.interfaces.event_bus.EventBus`. It is *not* related to
(and does not import) the `signals/` package -- `signals/` standardizes
`analysis.result.AnalysisResult`s into a `signals.result.SignalResult`
for one symbol/timeframe (a much earlier pipeline stage); `SignalEngine`
here sits at the `services/` layer, whose only allowed project-internal
dependencies are `core` and `events` (`PROJECT_RULES.md` Section 4) --
it never imports `signals/`, `strategies/` (including
`strategies.risk_management`/`strategies.portfolio_management`),
`analysis/`, or any other trading-decision package, and it never
returns a `signals.result.SignalResult`. The name collision is
coincidental: this is "an engine that handles a
`core.entities.signal.Signal`", not "the Signal Engine". Running an
already-produced `Signal` through the Signals -> Strategy -> Risk ->
Portfolio decision pipeline is `strategies/`'s (and, end-to-end,
`app/`'s) responsibility, not this engine's -- `SignalEngine` only
publishes a `Signal` it is handed as an event.

This module mirrors the exact "first concrete implementation" shape
`BasicRiskManager`, `BasicStrategy`, `BasicPortfolioManager`, and
`BasicBacktester` each established one layer down for their own
package's Part 1 foundation -- built in two parts:

    - **Part 2A:** constructor, dependency injection (an optional
      `EventBus`), validation (of the injected `EventBus` and of engine
      configuration), and engine configuration (`SignalEngine.config`,
      a validated, merged-with-defaults settings dict) -- the public
      interfaces a caller and Part 2B both need.
    - **Part 2B (this module, this milestone):** the actual
      orchestration in `execute()` -- interpreting `context.payload` as
      (or building) a `Signal`, validating it against this engine's
      configuration (`require_min_confidence`/`min_confidence`),
      publishing it via `self.event_bus` when one is injected, and
      returning a `ServiceResult` that reflects what actually happened.
      Still strictly a `core`/`events`-only orchestration: it consumes
      a caller-supplied `Signal` (or the raw fields to build one) and
      emits a `SignalGenerated` event -- it does not run any
      analysis/signal-generation/strategy/risk/portfolio logic itself.

No notification delivery, no AI/LLM call, no scheduler logic, no
concrete `EventBus` implementation, no networking, no threading, no
async, and no Signals/Strategy/Risk/Portfolio decision logic of any
kind ships in this module.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from core.entities.signal import Signal
from core.enums import SignalDirection

from events.event_types.signal_generated import SignalGenerated
from events.interfaces.event_bus import EventBus

from services.base import BaseService
from services.context import ServiceContext
from services.exceptions import InsufficientServiceDataError, ServiceConfigurationError
from services.result import ServiceResult
from services.utils import validate_dict

__all__ = ["SignalEngine"]


class SignalEngine(BaseService):
    """
    A `BaseService` that publishes a `core.entities.signal.Signal` as a
    `SignalGenerated` event via an injected `EventBus`.

    Part 2A provides construction, dependency injection, configuration,
    and configuration/dependency validation. Part 2B (this milestone)
    adds `execute()`'s real orchestration -- see its own docstring
    below. Both parts depend only on `core`/`events`, never on
    `signals/`, `strategies/`, or `analysis/`.

    Attributes:
        event_bus: The injected `events.interfaces.event_bus.EventBus`
            this engine will publish `SignalGenerated` events through,
            or `None` when no bus was supplied (a valid configuration
            for this part -- `SignalEngine` does not require one to be
            constructed, only to actually publish, which is Part 2B's
            responsibility). Never hard-wired to a concrete `EventBus`
            implementation, matching this project's dependency-
            injection convention (`PROJECT_RULES.md` Section 5) --
            no concrete `EventBus` exists anywhere in the repository
            yet (see `services/__init__.py`'s "Planned contents").
        config: This engine's validated, merged-with-defaults
            configuration (see `DEFAULT_CONFIG` below). Always a
            `dict[str, Any]` containing exactly `DEFAULT_CONFIG`'s
            keys -- never partial, never containing unknown keys.
    """

    #: Default engine configuration, merged with any caller-supplied
    #: overrides in `_validate_config`. Every key here is the complete
    #: set of configuration this engine recognizes -- `_validate_config`
    #: rejects any key not already present here.
    DEFAULT_CONFIG: dict[str, Any] = {
        # Whether execute()'s orchestration (Part 2B) generates its own
        # `Signal.signal_id`/`generated_at` when payload does not
        # already supply them, rather than treating their absence as
        # an error. Only consulted when building a Signal from raw
        # payload fields (i.e. payload has no "signal" key already).
        "auto_generate_signal_metadata": True,
        # Whether execute()'s orchestration (Part 2B) requires
        # `Signal.confidence >= min_confidence` before publishing,
        # rather than publishing every signal regardless of confidence.
        "require_min_confidence": True,
        # The confidence floor execute()'s orchestration (Part 2B)
        # enforces when `require_min_confidence` is True. Always a
        # `float` in `[0.0, 1.0]`.
        "min_confidence": 0.0,
    }

    def __init__(
        self,
        event_bus: Optional[EventBus] = None,
        *,
        config: Optional[dict[str, Any]] = None,
        name: Optional[str] = None,
    ) -> None:
        """
        Construct a `SignalEngine`.

        Args:
            event_bus: Optional `EventBus` this engine will publish
                `SignalGenerated` events through in a future
                orchestration part. Dependency-injected rather than
                hard-wired; `None` is a valid value for this part.
            config: Optional configuration overrides, merged onto
                `DEFAULT_CONFIG`. Every key must already exist in
                `DEFAULT_CONFIG` and every value must pass this
                engine's validation (see `_validate_config`).
            name: Human-readable name for this service instance
                (passed through to `BaseService.__init__`).

        Raises:
            ServiceConfigurationError: If `event_bus` is neither
                `None` nor an `EventBus` instance, or if `config` is
                not a `dict`, contains an unrecognized key, or
                contains a value that fails validation.
        """
        super().__init__(name=name)
        self.event_bus = self._validate_event_bus(event_bus)
        self.config = self._validate_config(config)

    # ------------------------------------------------------------------
    # Dependency injection / validation
    # ------------------------------------------------------------------
    def _validate_event_bus(self, event_bus: Optional[EventBus]) -> Optional[EventBus]:
        """
        Validate an injected `EventBus` dependency.

        Raises:
            ServiceConfigurationError: If `event_bus` is neither `None`
                nor an `EventBus` instance.
        """
        if event_bus is not None and not isinstance(event_bus, EventBus):
            raise ServiceConfigurationError(
                f"{self.name} expected event_bus to be None or an EventBus, "
                f"got {type(event_bus).__name__}"
            )
        return event_bus

    def _validate_config(self, config: Optional[dict[str, Any]]) -> dict[str, Any]:
        """
        Merge `config` onto `DEFAULT_CONFIG` and validate the result.

        Raises:
            ServiceConfigurationError: If `config` is not a `dict`,
                contains a key absent from `DEFAULT_CONFIG`, or any
                merged value fails its own type/range validation.
        """
        merged: dict[str, Any] = dict(self.DEFAULT_CONFIG)

        if config is not None:
            try:
                validate_dict(config, name="config")
            except Exception as exc:  # services.exceptions.ServiceValidationError
                raise ServiceConfigurationError(str(exc)) from exc

            unknown_keys = set(config) - set(self.DEFAULT_CONFIG)
            if unknown_keys:
                raise ServiceConfigurationError(
                    f"{self.name} received unrecognized config key(s): "
                    f"{sorted(unknown_keys)}; expected a subset of "
                    f"{sorted(self.DEFAULT_CONFIG)}"
                )
            merged.update(config)

        for bool_key in ("auto_generate_signal_metadata", "require_min_confidence"):
            if not isinstance(merged[bool_key], bool):
                raise ServiceConfigurationError(
                    f"{self.name} config[{bool_key!r}] must be a bool, "
                    f"got {type(merged[bool_key]).__name__}"
                )

        min_confidence = merged["min_confidence"]
        if (
            not isinstance(min_confidence, (int, float))
            or isinstance(min_confidence, bool)
            or not math.isfinite(float(min_confidence))
            or not (0.0 <= float(min_confidence) <= 1.0)
        ):
            raise ServiceConfigurationError(
                f"{self.name} config['min_confidence'] must be a finite "
                f"number in [0.0, 1.0], got {min_confidence!r}"
            )
        merged["min_confidence"] = float(min_confidence)

        return merged

    # ------------------------------------------------------------------
    # Public interfaces
    # ------------------------------------------------------------------
    def has_event_bus(self) -> bool:
        """Whether this engine was constructed with an `EventBus`."""
        return self.event_bus is not None

    def get_configuration(self) -> dict[str, Any]:
        """
        Return a copy of this engine's current configuration.

        A copy is returned (rather than `self.config` directly) so a
        caller mutating the result can never affect this engine's own
        configuration -- the same immutability-by-convention every
        other `metadata`/config-shaped dict in this project follows.
        """
        return dict(self.config)

    def execute(self, context: ServiceContext) -> ServiceResult:
        """
        Resolve a `Signal` from `context.payload`, apply this engine's
        `min_confidence` configuration, publish it as a
        `SignalGenerated` event via `self.event_bus` (when one was
        injected), and return a `ServiceResult` reflecting what
        actually happened.

        `context.payload` may supply the `Signal` directly:

            payload = {"signal": <core.entities.signal.Signal instance>}

        or the raw fields to build one:

            payload = {
                "symbol": "BTCUSDT",
                "direction": SignalDirection.BUY,  # or "buy"
                "confidence": 0.8,
                "source": "some-strategy",
                "timeframe": "1h",
                # optional: "signal_id", "generated_at", "metadata"
            }

        `symbol`, `direction`, `confidence`, `source`, and `timeframe`
        are always required. `signal_id`/`generated_at` may be omitted
        when `self.config["auto_generate_signal_metadata"]` is `True`
        (the default) -- a `uuid4` hex and the current UTC time are
        generated for them respectively; otherwise their absence is an
        error.

        When `self.config["require_min_confidence"]` is `True` (the
        default) and the resolved `Signal.confidence` is below
        `self.config["min_confidence"]`, the signal is *not* published
        and a `success=False` `ServiceResult` is returned instead.

        Args:
            context: The `ServiceContext` for this call. Only
                `context.payload` is interpreted; `context.service_name`
                and `context.metadata` are not.

        Returns:
            A `ServiceResult` whose `success` reflects whether the
            signal was actually published (`False` when it was
            rejected for confidence, or when no `EventBus` was
            injected), and whose `metadata` always records the
            resolved `signal_id`, `symbol`, and `confidence`, plus
            `event_id`/`published` once a publish attempt is made.

        Raises:
            InvalidServiceContextError: If `context` is not a
                `ServiceContext` instance (via `self.validate_context`).
            InsufficientServiceDataError: If `context.payload` does not
                carry (or carry enough data to build) a usable `Signal`.
        """
        self.validate_context(context)
        signal = self._resolve_signal(context.payload)

        if self.config["require_min_confidence"] and signal.confidence < self.config["min_confidence"]:
            return self._build_result(
                success=False,
                summary=(
                    f"{self.name} did not publish signal {signal.signal_id!r}: "
                    f"confidence {signal.confidence} is below the required "
                    f"minimum {self.config['min_confidence']}"
                ),
                metadata={
                    "signal_id": signal.signal_id,
                    "symbol": signal.symbol,
                    "confidence": signal.confidence,
                    "min_confidence": self.config["min_confidence"],
                    "published": False,
                },
            )

        if not self.has_event_bus():
            return self._build_result(
                success=False,
                summary=(
                    f"{self.name} could not publish signal {signal.signal_id!r}: "
                    "no EventBus was injected"
                ),
                metadata={
                    "signal_id": signal.signal_id,
                    "symbol": signal.symbol,
                    "confidence": signal.confidence,
                    "published": False,
                },
            )

        event = SignalGenerated(
            event_id=str(uuid4()),
            occurred_at=datetime.now(timezone.utc),
            signal=signal,
        )
        self.event_bus.publish(event)

        return self._build_result(
            success=True,
            summary=f"{self.name} published signal {signal.signal_id!r} for {signal.symbol}",
            metadata={
                "signal_id": signal.signal_id,
                "symbol": signal.symbol,
                "confidence": signal.confidence,
                "event_id": event.event_id,
                "published": True,
            },
        )

    # ------------------------------------------------------------------
    # execute() helpers
    # ------------------------------------------------------------------
    def _resolve_signal(self, payload: dict[str, Any]) -> Signal:
        """
        Resolve a `Signal` from `payload`: either an already-built
        `Signal` under the `"signal"` key, or the raw fields to build
        one.

        Raises:
            InsufficientServiceDataError: If `payload` carries neither
                a valid `"signal"` entry nor enough raw fields to build
                one.
        """
        existing = payload.get("signal")
        if existing is not None:
            if not isinstance(existing, Signal):
                raise InsufficientServiceDataError(
                    f"{self.name} expected payload['signal'] to be a Signal, "
                    f"got {type(existing).__name__}"
                )
            return existing

        return self._build_signal(payload)

    def _build_signal(self, payload: dict[str, Any]) -> Signal:
        """
        Build a `Signal` from raw `payload` fields.

        Raises:
            InsufficientServiceDataError: If a required field is
                missing/invalid, or if `signal_id`/`generated_at` are
                missing while `self.config["auto_generate_signal_metadata"]`
                is `False`.
        """
        required = ("symbol", "direction", "confidence", "source", "timeframe")
        missing = [field for field in required if field not in payload]
        if missing:
            raise InsufficientServiceDataError(
                f"{self.name} cannot build a Signal from payload: missing "
                f"required field(s) {missing}"
            )

        direction = payload["direction"]
        if isinstance(direction, str):
            try:
                direction = SignalDirection(direction)
            except ValueError as exc:
                raise InsufficientServiceDataError(
                    f"{self.name} received an invalid direction {payload['direction']!r}"
                ) from exc
        elif not isinstance(direction, SignalDirection):
            raise InsufficientServiceDataError(
                f"{self.name} expected payload['direction'] to be a "
                f"SignalDirection or str, got {type(direction).__name__}"
            )

        confidence = payload["confidence"]
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            raise InsufficientServiceDataError(
                f"{self.name} expected payload['confidence'] to be a number, "
                f"got {type(confidence).__name__}"
            )

        auto_generate = self.config["auto_generate_signal_metadata"]

        signal_id = payload.get("signal_id")
        if signal_id is None:
            if not auto_generate:
                raise InsufficientServiceDataError(
                    f"{self.name} cannot build a Signal: missing 'signal_id' "
                    "and config['auto_generate_signal_metadata'] is False"
                )
            signal_id = str(uuid4())

        generated_at = payload.get("generated_at")
        if generated_at is None:
            if not auto_generate:
                raise InsufficientServiceDataError(
                    f"{self.name} cannot build a Signal: missing 'generated_at' "
                    "and config['auto_generate_signal_metadata'] is False"
                )
            generated_at = datetime.now(timezone.utc)

        metadata = payload.get("metadata", {})

        return Signal(
            signal_id=signal_id,
            symbol=payload["symbol"],
            direction=direction,
            confidence=float(confidence),
            source=payload["source"],
            timeframe=payload["timeframe"],
            generated_at=generated_at,
            metadata=metadata,
        )

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        return (
            f"{self.__class__.__name__}(name={self.name!r}, "
            f"has_event_bus={self.has_event_bus()}, config={self.config!r})"
        )
