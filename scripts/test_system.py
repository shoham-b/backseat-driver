"""Run the system tests: against $API_URL if set, else against a freshly built Docker Compose stack.

Usage: test_system.py <docker compose command...>
"""

import os
import subprocess
import sys

compose = sys.argv[1:]
api_url = os.environ.get("API_URL")

if api_url:
    subprocess.run(["uv", "run", "pytest", "tests/systemtests", "-v", "--api-url", api_url], check=True)
else:
    try:
        subprocess.run([*compose, "--profile", "test", "run", "--build", "--rm", "systemtest"], check=True)
    finally:
        subprocess.run([*compose, "--profile", "test", "down"], check=True)
