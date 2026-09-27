"""Domain event bus — Observer pattern for decoupled post-action side-effects.

Services emit typed events; subscribers react without tight coupling to each
other. Wire up subscribers in the app lifespan, or inject a fresh EventBus in
tests for full isolation.

Usage::

    # Emit from a service:
    await bus.emit(ItemCreated(item_id=item.id, name=item.name))

    # Subscribe a handler (e.g. in app.py lifespan):
    bus.subscribe(ItemCreated, _send_welcome_notification)
"""
import contextlib
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass
class DomainEvent:
    """Base class for all domain events."""


@dataclass
class ItemCreated(DomainEvent):
    item_id: str
    name: str


@dataclass
class ItemDeleted(DomainEvent):
    item_id: str


type EventHandler = Callable[[DomainEvent], Awaitable[None]]


class EventBus:
    """Async in-process event bus.

    Not thread-safe. For cross-process or durable delivery, use a message broker.
    """

    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[EventHandler]] = {}

    def subscribe(self, event_type: type[DomainEvent], handler: EventHandler) -> None:
        """Register a coroutine handler for a specific event type."""
        self._handlers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: type[DomainEvent], handler: EventHandler) -> None:
        """Remove a previously registered handler. No-op if not found."""
        with contextlib.suppress(ValueError):
            self._handlers.get(event_type, []).remove(handler)

    async def emit(self, event: DomainEvent) -> None:
        """Dispatch an event to all registered handlers in registration order."""
        for handler in self._handlers.get(type(event), []):
            await handler(event)
