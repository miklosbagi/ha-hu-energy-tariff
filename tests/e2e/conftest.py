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
CONTAINER_NAME = "e2e-homeassistant-1"


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


def _container_bridge_ip() -> str | None:
    """Fallback address for when localhost:8123 isn't reachable from the
    test process's own network namespace - happens when the CI runner
    itself runs inside a container and launches this stack via a
    mounted host docker socket (Docker-outside-of-Docker): the launched
    container's published port lands on the *docker host*'s network,
    not the runner-job container's, but the job container can typically
    still reach the other container's bridge-network IP directly."""
    try:
        result = subprocess.run(
            [
                "docker",
                "inspect",
                "-f",
                "{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}",
                CONTAINER_NAME,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout.strip() or None
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None


def wait_for_frontend(timeout: float = 90.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    bridge_ip: str | None = None
    while time.monotonic() < deadline:
        urls = [HA_BASE_URL]
        if bridge_ip:
            urls.append(f"http://{bridge_ip}:8123")
        for url in urls:
            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    return
            except requests.RequestException as err:
                last_error = err
        # Give localhost ~20s alone first (the common case, and instant
        # on setups where port publishing is directly reachable) before
        # paying for the docker-inspect fallback lookup.
        if bridge_ip is None and time.monotonic() > deadline - timeout + 20:
            bridge_ip = _container_bridge_ip()
        time.sleep(2)
    raise TimeoutError(f"Home Assistant frontend never became reachable: {last_error}")
