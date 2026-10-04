"""Run the dev server in distributed mode (RabbitMQ + Postgres).

Usage: dev_distributed.py <host> <port>
"""

import os
import subprocess
import sys

host, port = sys.argv[1:]

subprocess.run(
    ["uv", "run", "fastapi", "dev", "backseat_driver/api/app.py", "--host", host, "--port", port],
    env={**os.environ, "BACKSEAT_DRIVER_MODE": "distributed"},
    check=True,
)
