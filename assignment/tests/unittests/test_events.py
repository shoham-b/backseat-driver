"""Unit tests for the EventBus — Observer pattern."""
from vlm_scene_description.bl.events import DomainEvent, EventBus, ItemCreated, ItemDeleted


async def test_subscriber_receives_emitted_event() -> None:
    bus = EventBus()
    received: list[DomainEvent] = []

    async def handler(event: DomainEvent) -> None:
        received.append(event)

    bus.subscribe(ItemCreated, handler)
    await bus.emit(ItemCreated(item_id="1", name="Widget"))

    assert len(received) == 1
    assert isinstance(received[0], ItemCreated)
    assert received[0].item_id == "1"  # type: ignore[union-attr]


async def test_unsubscribed_event_type_is_ignored() -> None:
    bus = EventBus()
    received: list[DomainEvent] = []

    async def handler(event: DomainEvent) -> None:
        received.append(event)

    bus.subscribe(ItemCreated, handler)
    await bus.emit(ItemDeleted(item_id="1"))  # no handler registered for this

    assert received == []


async def test_multiple_subscribers_all_called() -> None:
    bus = EventBus()
    log: list[str] = []

    async def first(event: DomainEvent) -> None:
        log.append("first")

    async def second(event: DomainEvent) -> None:
        log.append("second")

    bus.subscribe(ItemCreated, first)
    bus.subscribe(ItemCreated, second)
    await bus.emit(ItemCreated(item_id="1", name="X"))

    assert log == ["first", "second"]


async def test_emit_with_no_subscribers_does_nothing() -> None:
    bus = EventBus()
    await bus.emit(ItemCreated(item_id="x", name="Y"))  # should not raise


async def test_unsubscribe_stops_delivery() -> None:
    bus = EventBus()
    received: list[DomainEvent] = []

    async def handler(event: DomainEvent) -> None:
        received.append(event)

    bus.subscribe(ItemCreated, handler)
    bus.unsubscribe(ItemCreated, handler)
    await bus.emit(ItemCreated(item_id="1", name="Widget"))

    assert received == []


async def test_unsubscribe_nonexistent_handler_is_noop() -> None:
    bus = EventBus()

    async def handler(event: DomainEvent) -> None:
        pass

    bus.unsubscribe(ItemCreated, handler)  # should not raise


async def test_unsubscribe_only_removes_matching_handler() -> None:
    bus = EventBus()
    log: list[str] = []

    async def keep(event: DomainEvent) -> None:
        log.append("keep")

    async def remove(event: DomainEvent) -> None:
        log.append("remove")

    bus.subscribe(ItemCreated, keep)
    bus.subscribe(ItemCreated, remove)
    bus.unsubscribe(ItemCreated, remove)
    await bus.emit(ItemCreated(item_id="1", name="X"))

    assert log == ["keep"]
