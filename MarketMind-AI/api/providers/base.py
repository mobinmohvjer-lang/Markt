"""
api/providers/base.py

Shared base class for all data providers.

Providers are thin, clean wrappers around a single external REST API.
They translate provider-specific endpoints/params into calls against
an injected HTTPClient and return raw decoded JSON (dicts/lists).

Providers deliberately do NOT:
- compute indicators or statistics
- generate trading signals
- run any AI/model inference
- hold trading state

Those concerns belong to other layers of MarketMind-AI.
"""

from __future__ import annotations

import logging
from typing import Optional

from api.http_client import HTTPClient


class BaseProvider:
    """Common plumbing (client + logger) shared by concrete providers."""

    def __init__(self, http_client: HTTPClient, logger: Optional[logging.Logger] = None) -> None:
        self.client = http_client
        self.logger = logger or logging.getLogger(self.__class__.__name__)
