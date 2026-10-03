"""Production entrypoint: ``python -m backseat_driver.api``.

Binds the host and port from ``Settings`` so the container honors BACKSEAT_DRIVER_API_HOST/PORT; ``fastapi run``
only takes them from its command line, which an exec-form Dockerfile CMD can't fill from the environment.
"""

import uvicorn

from backseat_driver.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run("backseat_driver.api.app:app", host=settings.api_host, port=settings.api_port)
