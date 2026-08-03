"""
database_repository.py
--------------------------
Purpose:
    Defines the `DatabaseRepository` interface: a generic persistence
    contract (the Repository pattern) that any concrete storage backend
    must implement, parameterized over the entity type it stores.

    Using `Generic[T]` allows the same interface shape to be reused for
    repositories of different entities (e.g. a repository of `Trade`,
    a repository of `Position`) without duplicating the contract.

    No implementation, no database/SQL code here -- concrete repositories
    will live in the future `database/repositories/` package (e.g.
    backed by SQLite via SQLAlchemy, per `config.settings.database_url`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")


class DatabaseRepository(ABC, Generic[T]):
    """Abstract contract for persisting and retrieving entities of type T."""

    @abstractmethod
    def save(self, entity: T) -> None:
        """
        Persist an entity, creating or updating it as appropriate.

        Args:
            entity: The entity instance to persist.
        """
        raise NotImplementedError

    @abstractmethod
    def get_by_id(self, entity_id: str) -> T | None:
        """
        Retrieve a single entity by its identifier.

        Args:
            entity_id: Unique identifier of the entity to retrieve.

        Returns:
            The matching entity, or `None` if not found.
        """
        raise NotImplementedError

    @abstractmethod
    def get_all(self) -> list[T]:
        """
        Retrieve all stored entities of this type.

        Returns:
            A list of all stored entities (possibly empty).
        """
        raise NotImplementedError

    @abstractmethod
    def delete(self, entity_id: str) -> None:
        """
        Remove an entity by its identifier.

        Args:
            entity_id: Unique identifier of the entity to remove.
        """
        raise NotImplementedError
