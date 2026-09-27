from vlm_scene_description.db.memory import MemoryRepository


async def test_memory_repository_healthcheck() -> None:
    repo = MemoryRepository()

    result = await repo.healthcheck()

    assert result is True
