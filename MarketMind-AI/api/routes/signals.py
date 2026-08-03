"""
api/routes/signals.py

Defines `SignalHandler`: the first concrete `api.base.BaseAPIHandler`
implementation, exposing the existing Signal generation flow through
the inbound REST API foundation API Layer Part 1 shipped.

Originally shipped in **API Layer Part 2 (Signal endpoint only)**;
**API Layer Part 3 (Response standardization only, this milestone)**
changes exactly one thing about it: every `APIResult` this handler
returns now carries the standardized response envelope
(`api.response.success_envelope`/`error_envelope`, built via
`BaseAPIHandler._build_success_result`/`_build_error_result`) instead
of the bespoke `{"error": "..."}}`/bare-payload shapes Part 2 used.
See `api/response.py` for the envelope's exact shape. No other
behavior changes -- see `api/routes/__init__.py`.

Scope (deliberately bounded)
-----------------------------
`SignalHandler` is a **thin adapter only**:

    1. Reads `symbol`/`timeframe` off an `api.context.APIRequestContext`
       (`query_params`, falling back to `body` when it is a `dict`).
    2. Calls the already-existing `app.main.MainApplication.run(symbol,
       timeframe)` -- the Data -> Indicators -> Analysis -> Signals
       pipeline (`app.pipeline.MarketPipeline`) `MainApplication`
       already orchestrates.
    3. Wraps the outcome -- the resulting `signals.result.SignalResult`
       on success, or a caught exception on failure -- in the
       standardized response envelope, inside an `api.result.APIResult`.

No new business logic is added here, in this or the prior part.
`SignalHandler` computes nothing itself -- every calculation/
interpretation/decision still happens inside the package that already
owns it (`data/`, `indicators/`, `analysis/`, `signals/`, via
`MainApplication.run`). It never touches `strategies/`, risk/portfolio
management, `execution/`, a broker connection, or AI -- `MainApplication.
run` itself does not either (see `app/main.py`'s module docstring). No
authentication and no web server framework: this handler is a plain
Python object implementing `BaseAPIHandler.handle(context) ->
APIResult` -- nothing in this module parses a real inbound HTTP
request, registers a route, or runs a server; assembling a real
`APIRequestContext` and dispatching to this handler remains the future
`routes/`-registration / `server.py` work `api/__init__.py`'s "Planned
contents" already documents. `app.main.MainApplication` and
`app.pipeline.MarketPipeline` are both used exactly as they already
exist -- neither is modified by this milestone.

Response categories (this milestone's standardization)
---------------------------------------------------------
Every outcome `handle()` can produce now falls into exactly one of
four categories, each built through the same envelope shape (only
`status_code`/`error.type`/`error.message` differ):

    1. **Success** (`_build_success_result`, `200`) -- `MainApplication.
       run` returned a `SignalResult`; `data` is its serialized form
       (`_signal_result_to_body`).
    2. **Validation errors** (`_build_error_result`, `400`) -- `context`
       itself is unusable (`InvalidRequestContextError`) or
       `symbol`/`timeframe` is missing/empty
       (`InsufficientAPIDataError`). Caught here rather than left to
       propagate (API Layer Part 2's prior behavior), so every request
       -- valid or not -- returns one standardized `APIResult`.
    3. **Pipeline errors** (`_build_error_result`, `400`/`404`) --
       `MainApplication.run` rejected its own input
       (`PipelineConfigurationError`, `400`) or had no candle history
       to work with (`PipelineDataError`, `404`): both are conditions
       the pipeline itself already recognizes and names.
    4. **Internal errors** (`_build_error_result`, `500`) -- the
       Analysis or Signals stage failed unexpectedly
       (`PipelineAnalysisError`/`PipelineSignalError`), or any other
       exception escaped `MainApplication.run` that this handler did
       not anticipate (a final, generic `except Exception` safety net,
       reported as `error.type == "InternalError"` with a fixed,
       non-leaking message -- the concrete exception's class name is
       still recorded in `APIResult.metadata["exception_type"]` for
       traceability, matching `BaseAPIHandler`'s documented `metadata`
       convention, without echoing arbitrary internal exception text
       back to a caller).

Per `PROJECT_RULES.md` Section 1 principle 6 / Section 4, this
handler's inbound REST role imports only `app` (`app.main.MainApplication`,
`app.exceptions`) plus its own package (`api.base`, `api.context`,
`api.exceptions`, `api.result`) -- never `core`, `data`, `indicators`,
`analysis`, `signals`, `strategies`, `backtesting`, or `services`
directly, and it never constructs or modifies a `core`/domain object
itself.
"""

from __future__ import annotations

from typing import Any, Optional

from app.exceptions import (
    PipelineAnalysisError,
    PipelineConfigurationError,
    PipelineDataError,
    PipelineSignalError,
)
from app.main import MainApplication

from api.base import BaseAPIHandler
from api.context import APIRequestContext
from api.exceptions import (
    APIHandlerConfigurationError,
    InsufficientAPIDataError,
    InvalidRequestContextError,
)
from api.result import APIResult


def _extract_field(context: APIRequestContext, field_name: str) -> str:
    """
    Read `field_name` off `context.query_params`, falling back to
    `context.body` when it is a `dict`.

    Query params are checked first since `SignalHandler` is expected to
    be reached via a `GET`-style request once a real router exists;
    falling back to `body` costs nothing and keeps this handler usable
    from a `POST`-style request too, without this foundation needing to
    know which one a future `server.py` will actually use.

    Raises:
        InsufficientAPIDataError: `field_name` is absent from both
            `query_params` and `body`, or is present but not a
            non-empty string.
    """
    value = context.query_params.get(field_name)
    if value is None and isinstance(context.body, dict):
        value = context.body.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise InsufficientAPIDataError(
            f"{field_name} is required and must be a non-empty string "
            "(checked query_params and body)"
        )
    return value


def _signal_result_to_body(signal_result: Any) -> dict[str, Any]:
    """
    Translate a `signals.result.SignalResult` into a plain, JSON-shaped
    `dict` -- this becomes the standardized envelope's `"data"` value.

    Field-for-field only -- no renaming, no recomputation, no
    reinterpretation of `SignalResult`'s data. `direction` (a
    `core.enums.SignalDirection`) is reduced to its plain `str` `.value`
    since `SignalResult` itself is not serialized here (`api/` never
    modifies a `core`/domain object -- this only reads one).
    """
    return {
        "direction": signal_result.direction.value,
        "strength": signal_result.strength,
        "confidence": signal_result.confidence,
        "summary": signal_result.summary,
        "metadata": signal_result.metadata,
    }


class SignalHandler(BaseAPIHandler):
    """
    Thin `BaseAPIHandler` adapter over `app.main.MainApplication.run`.

    Every `APIResult` this handler returns carries the standardized
    response envelope (`api.response.success_envelope`/`error_envelope`)
    in its `body` -- see this module's docstring, "Response
    categories", for the exact success/validation/pipeline/internal
    breakdown.

    Parameters
    ----------
    app:
        The composition root to call `.run(symbol, timeframe)` on.
        Defaults to a plain `MainApplication()` (dependency injection,
        matching this repository's convention -- see `PROJECT_RULES.md`
        Section 5) -- inject a real instance or a test fake instead of
        relying on this default in tests, so no real network/database
        access is required.
    name:
        Forwarded to `BaseAPIHandler.__init__` (see its docstring).

    Raises
    ------
    api.exceptions.APIHandlerConfigurationError
        `app` is supplied and is not a `MainApplication` instance.
    """

    def __init__(
        self,
        app: Optional[MainApplication] = None,
        *,
        name: Optional[str] = None,
    ) -> None:
        super().__init__(name=name)
        if app is not None and not isinstance(app, MainApplication):
            raise APIHandlerConfigurationError(
                f"app must be a MainApplication, got {type(app).__name__}"
            )
        self.app: MainApplication = app if app is not None else MainApplication()

    def handle(self, context: APIRequestContext) -> APIResult:
        """
        Handle one inbound "generate a signal" request.

        Unlike API Layer Part 2, this never raises
        `InvalidRequestContextError`/`InsufficientAPIDataError` out of
        `handle()` itself -- both are now caught and reported as a
        standardized `400` validation-error `APIResult`, so every call
        to this method returns an `APIResult`, valid input or not.

        Parameters
        ----------
        context:
            Ideally carries `symbol` and `timeframe` in `query_params`
            (or `body`, if it is a `dict`) -- see `_extract_field`.
            Missing/invalid data is reported in the returned
            `APIResult`, not raised.

        Returns
        -------
        api.result.APIResult
            `body` always follows the standardized envelope shape
            (`api.response`, `{"success", "status_code", "data",
            "error"}`):

            - `200`, `data` set to the serialized `SignalResult`
              (`_signal_result_to_body`), on success.
            - `400`, `error.type` one of `"InvalidRequestContextError"`/
              `"InsufficientAPIDataError"`, when `context` itself is
              unusable or `symbol`/`timeframe` is missing/empty.
            - `400`, `error.type == "PipelineConfigurationError"`, when
              `MainApplication.run` rejects `symbol`/`timeframe` itself.
            - `404`, `error.type == "PipelineDataError"`, when no
              candle history is available for `symbol`/`timeframe`.
            - `500`, `error.type` one of `"PipelineAnalysisError"`/
              `"PipelineSignalError"`/`"InternalError"`, when the
              Analysis/Signals stage -- or anything else unanticipated
              -- fails.

            `metadata` always records `symbol`/`timeframe` (once
            successfully extracted) and, for failures, which stage
            raised (`"stage"`) -- mirroring `BaseAPIHandler`'s
            documented `metadata` convention.
        """
        try:
            self.validate_context(context)
            symbol = _extract_field(context, "symbol")
            timeframe = _extract_field(context, "timeframe")
        except (InvalidRequestContextError, InsufficientAPIDataError) as exc:
            return self._build_error_result(
                status_code=400,
                error_type=type(exc).__name__,
                message=str(exc),
                metadata={"stage": "validation"},
            )

        try:
            signal_result = self.app.run(symbol, timeframe)
        except PipelineConfigurationError as exc:
            return self._build_error_result(
                status_code=400,
                error_type=type(exc).__name__,
                message=str(exc),
                metadata={"symbol": symbol, "timeframe": timeframe, "stage": "configuration"},
            )
        except PipelineDataError as exc:
            return self._build_error_result(
                status_code=404,
                error_type=type(exc).__name__,
                message=str(exc),
                metadata={"symbol": symbol, "timeframe": timeframe, "stage": "data"},
            )
        except PipelineAnalysisError as exc:
            return self._build_error_result(
                status_code=500,
                error_type=type(exc).__name__,
                message=str(exc),
                metadata={"symbol": symbol, "timeframe": timeframe, "stage": "analysis"},
            )
        except PipelineSignalError as exc:
            return self._build_error_result(
                status_code=500,
                error_type=type(exc).__name__,
                message=str(exc),
                metadata={"symbol": symbol, "timeframe": timeframe, "stage": "signal"},
            )
        except Exception as exc:  # noqa: BLE001 - last-resort safety net, see module docstring
            return self._build_error_result(
                status_code=500,
                error_type="InternalError",
                message="An unexpected internal error occurred.",
                metadata={
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "stage": "internal",
                    "exception_type": type(exc).__name__,
                },
            )

        return self._build_success_result(
            status_code=200,
            data=_signal_result_to_body(signal_result),
            metadata={"symbol": symbol, "timeframe": timeframe},
        )
