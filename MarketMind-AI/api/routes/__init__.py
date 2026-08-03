"""
api/routes package
-------------------
Purpose:
    Concrete `BaseAPIHandler` implementations, one module per resource
    -- this is the `routes/` package `api/__init__.py`'s "Planned
    contents" section already anticipated for a future API Layer part.

    **API Layer Part 2 (this milestone)** adds the first of these:
    `SignalHandler`, exposing the existing Signal generation flow
    (`app.main.MainApplication.run`) through the inbound REST API
    foundation API Layer Part 1 shipped (`api.base.BaseAPIHandler`,
    `api.context.APIRequestContext`, `api.result.APIResult`).

Contents:
    - `signals.py`: `SignalHandler` -- a thin adapter that reads
      `symbol`/`timeframe` off an `APIRequestContext`, calls
      `app.main.MainApplication.run(symbol, timeframe)` (the existing
      Data -> Indicators -> Analysis -> Signals pipeline), and wraps
      the resulting `signals.result.SignalResult` in an `APIResult`.
      No business logic of its own -- see `signals.py`'s module
      docstring for the full scope boundary.

Still not shipped by this package (future API Layer parts):
    - Route registration/dispatch (a router mapping method+path to a
      handler instance).
    - `server.py` (an actual HTTP server assembling a real
      `APIRequestContext` per inbound request).
    - Request/response schemas (`schemas/`) for real wire-format
      (de)serialization.
    - Authentication, broker connection, trading execution (`strategies/`,
      risk/portfolio management, `execution/`), or AI.
"""

from __future__ import annotations

from api.routes.signals import SignalHandler

__all__ = ["SignalHandler"]
