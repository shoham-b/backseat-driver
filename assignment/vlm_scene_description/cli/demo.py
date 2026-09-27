"""Demo commands — walk through design patterns without a running server.

Each pattern section shows working code: builds objects, calls services, and
prints observable results so you can see the pattern in action.

Usage::

    vlm_scene_description demo patterns            # all patterns in sequence
    vlm_scene_description demo patterns --verbose  # extra detail per pattern
"""
import asyncio
from typing import Annotated

import typer

from vlm_scene_description.cli import demo_app


@demo_app.command("patterns")
def demo_patterns(
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Print extra detail per pattern")
    ] = False,
) -> None:
    """Walk through all design patterns implemented in this template.

    Runs entirely in memory — no running server required.
    """
    asyncio.run(_run_demo(verbose=verbose))


async def _run_demo(*, verbose: bool) -> None:
    from vlm_scene_description.bl.builder import ItemBuilder
    from vlm_scene_description.bl.cache import cached_for
    from vlm_scene_description.bl.commands import CommandHistory, CreateItemCommand, DeleteItemCommand
    from vlm_scene_description.bl.errors import NotFoundError
    from vlm_scene_description.bl.events import DomainEvent, EventBus, ItemCreated
    from vlm_scene_description.bl.items import ItemService
    from vlm_scene_description.bl.pipeline import (
        DescriptionLengthValidator,
        IdFormatValidator,
        NameNotEmptyValidator,
        ValidationPipeline,
    )
    from vlm_scene_description.bl.strategy import ItemSorter, sort_by_id, sort_by_name
    from vlm_scene_description.config import get_settings
    from vlm_scene_description.db.logging_repository import LoggingRepository
    from vlm_scene_description.db.memory import MemoryRepository
    from vlm_scene_description.models import Item

    # ── 1. Factory Method ───────────────────────────────────────────────────
    _h("1. Factory Method — db/factory.py")
    repo = MemoryRepository()
    _p("In production: get_repository(settings) picks Memory or Sqlite from config")

    # ── 2. Builder ───────────────────────────────────────────────────────────
    _h("2. Builder — bl/builder.py")
    item = ItemBuilder("demo-1").name("First Item").description("Built step by step").build()
    _p(f"Built: {item.id!r} / {item.name!r}")
    try:
        ItemBuilder("bad").build()
    except ValueError as exc:
        _p(f"Missing .name() → ValueError: {exc}", dim=True)

    # ── 3. Decorator ─────────────────────────────────────────────────────────
    _h("3. Decorator — db/logging_repository.py")
    logged_repo = LoggingRepository(repo)
    _p("LoggingRepository(repo) adds structured logging around every call")
    _p("Wrapped repo is unaware; callers use the same ItemRepository interface")
    if verbose:
        await logged_repo.create_item(item)
        _p("→ emitted debug log: create_item item_id='demo-1'", dim=True)

    # ── 4. Strategy ──────────────────────────────────────────────────────────
    _h("4. Strategy — ItemRepository Protocol (db/item_repository.py)")
    _p("ItemService accepts ANY object satisfying ItemRepository (duck-typed Protocol)")
    _p("Swap MemoryRepository ↔ LoggingRepository ↔ SqliteRepository — zero code changes")

    # ── 5. Observer ──────────────────────────────────────────────────────────
    _h("5. Observer — bl/events.py")
    seen: list[str] = []

    async def on_created(event: DomainEvent) -> None:
        if isinstance(event, ItemCreated):
            seen.append(event.item_id)

    bus = EventBus()
    bus.subscribe(ItemCreated, on_created)
    svc = ItemService(repo, bus)
    await svc.create(item)
    _p(f"Service emitted ItemCreated → subscriber received: {seen}")

    # ── 6. Template Method ───────────────────────────────────────────────────
    _h("6. Template Method — Repository ABC (db/base.py)")
    _p("Repository defines abstract healthcheck(); concrete classes fill it in")
    healthy = await repo.healthcheck()
    _p(f"MemoryRepository.healthcheck() → {healthy}", dim=True)

    # ── 7. Singleton ─────────────────────────────────────────────────────────
    _h("7. Singleton — config.py")
    s1, s2 = get_settings(), get_settings()
    _p(f"get_settings() uses @lru_cache — same instance every call: {s1 is s2}")

    # ── 8. Cache (Memoize) ───────────────────────────────────────────────────
    _h("8. Memoize / TTL Cache — bl/cache.py")
    call_count = 0

    @cached_for(ttl=60.0)
    async def expensive_query() -> str:
        nonlocal call_count
        call_count += 1
        return "result"

    r1 = await expensive_query()
    await expensive_query()
    _p(f"Called twice → actual function called {call_count}x, both return {r1!r}")

    # ── 9. Domain Error hierarchy ────────────────────────────────────────────
    _h("9. Domain Error dispatch — bl/errors.py + api/exception_handlers.py")
    try:
        await svc.get("nonexistent")
    except NotFoundError as exc:
        _p("Service raises NotFoundError → handler maps to HTTP 404")
        _p(f"error: {exc}", dim=True)

    # ── 10. Strategy (sort algorithms) ──────────────────────────────────────
    _h("10. Strategy — bl/strategy.py")
    sample = [
        Item(id="c", name="Banana"),
        Item(id="a", name="cherry"),
        Item(id="b", name="apple"),
    ]
    sorter = ItemSorter(strategy=sort_by_name)
    by_name = [i.name for i in sorter.sort(sample)]
    _p(f"sort_by_name:  {by_name}")
    sorter.set_strategy(sort_by_id)
    by_id = [i.id for i in sorter.sort(sample)]
    _p(f"sort_by_id:    {by_id}")
    _p("Swap strategy at runtime — zero changes to callers", dim=True)

    # ── 11. Chain of Responsibility (validation pipeline) ───────────────────
    _h("11. Chain of Responsibility — bl/pipeline.py")
    pipeline = ValidationPipeline(
        NameNotEmptyValidator(),
        IdFormatValidator(),
        DescriptionLengthValidator(max_length=100),
    )
    good = Item(id="ok-item", name="Good Item")
    await pipeline.run(good)
    _p(f"Valid item {good.id!r} passed all validators")
    bad = Item(id="bad id!", name="  ")
    from vlm_scene_description.bl.errors import UnprocessableError
    try:
        await pipeline.run(bad)
    except UnprocessableError as exc:
        _p(f"Chain stopped at first failure: {exc}", dim=True)

    # ── 12. Command + Undo ───────────────────────────────────────────────────
    _h("12. Command + Undo — bl/commands.py")
    fresh_repo = MemoryRepository()
    history = CommandHistory()
    cmd_item = Item(id="cmd-1", name="Command Item")
    await history.execute(CreateItemCommand(repo=fresh_repo, item=cmd_item))
    exists = await fresh_repo.get_item("cmd-1") is not None
    _p(f"CreateItemCommand executed — item exists: {exists}")
    await history.undo_last()
    after_undo = await fresh_repo.get_item("cmd-1") is None
    _p(f"undo_last() reversed it — item gone: {after_undo}")

    # DeleteItemCommand snapshot-and-restore
    await fresh_repo.create_item(cmd_item)
    del_cmd = DeleteItemCommand(repo=fresh_repo, item_id="cmd-1")
    await del_cmd.execute()
    await del_cmd.undo()
    restored = await fresh_repo.get_item("cmd-1") is not None
    _p(f"DeleteItemCommand undo restored snapshot: {restored}", dim=True)

    typer.secho("\n✓ All patterns demonstrated.", fg=typer.colors.GREEN, bold=True)


def _h(title: str) -> None:
    typer.secho(f"\n── {title}", fg=typer.colors.CYAN, bold=True)


def _p(msg: str, *, dim: bool = False) -> None:
    fg = typer.colors.BRIGHT_BLACK if dim else None
    typer.secho(f"   {msg}", fg=fg)
