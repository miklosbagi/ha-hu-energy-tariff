"""End-to-end test fixtures: bring up a real Home Assistant container
with this integration mounted, so test_smoke_startup.py can verify it
actually loads - something the headless tests/unit/ suite cannot prove.

Run separately from the unit suite (it needs Docker):

    pytest tests/e2e
"""
from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest
import requests

E2E_DIR = Path(__file__).parent
COMPOSE_FILE = E2E_DIR / "docker-compose.yml"
HA_BASE_URL = "http://localhost:8123"


@pytest.fixture(scope="session")
def docker_compose_up():
    subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d", "--wait"],
        check=True,
        timeout=180,
    )
    try:
        yield
    finally:
        subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE_FILE), "down", "-v"], check=False
        )


def container_logs() -> str:
    result = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "logs", "homeassistant"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def wait_for_frontend(timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            response = requests.get(HA_BASE_URL, timeout=5)
            if response.status_code == 200:
                return
        except requests.RequestException as err:
            last_error = err
        time.sleep(2)
    raise TimeoutError(f"Home Assistant frontend never became reachable: {last_error}")
