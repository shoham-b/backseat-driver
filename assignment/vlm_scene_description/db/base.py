from abc import ABC, abstractmethod


class Repository(ABC):
    """Abstract data-access interface.

    Implement in memory.py for tests/dev and sqlite.py (or postgres.py) for production.
    The factory in factory.py selects the implementation based on Settings.db_backend.
    """

    @abstractmethod
    async def healthcheck(self) -> bool:
        """Return True if the backend is reachable."""
        ...
