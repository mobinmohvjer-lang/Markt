"""
events.interfaces package
----------------------------
Purpose:
    Abstract contracts for the event-driven architecture: the shape all
    events share (`Event`), and the pub/sub mechanics any concrete
    message bus must implement (`EventBus`, `EventHandler`).

    No implementation, no network code, no async here -- concrete
    implementations (e.g. an in-memory synchronous bus for local use, or
    an async/Redis-backed bus later) belong to future outer layers.

Contents:
    - event.py          -> Event
    - event_bus.py       -> EventBus
    - event_handler.py    -> EventHandler
"""
