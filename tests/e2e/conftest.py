"""End-to-end test fixtures: bring up a real Home Assistant container
with this integration mounted, so test_smoke_startup.py can verify it
actually loads - something the headless tests/unit/ suite cannot prove.

Run separately from the unit suite (it needs Docker):

    pytest tests/e2e
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

E2E_DIR = Path(__file__).parent
COMPOSE_FILE = E2E_DIR / "docker-compose.yml"


@pytest.fixture(scope="session")
def docker_compose_up():
    # --wait blocks until the container's own healthcheck (which runs
    # inside the container via loopback - see docker-compose.yml) passes,
    # which is what actually proves the frontend came up. Deliberately
    # not duplicated with an external HTTP request from the test process:
    # that would be exposed to a runner network topology this suite
    # can't control (see git history/PR discussion on a Docker-outside-
    # of-Docker runner where the job container couldn't route to the
    # launched container's bridge network at all).
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
