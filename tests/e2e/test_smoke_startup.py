"""Smoke test: the integration loads cleanly inside a real Home
Assistant container.

This intentionally does not walk through the config flow to create a
live config entry - that requires completing HA onboarding/auth, which
is a heavier fast-follow (see README "Testing" section). It verifies
the two things most likely to silently break the integration: the
frontend comes up at all with custom_components/hu_energy_tariff
mounted, and the container logs show no import/setup traceback for our
domain - HA validates every custom_components manifest at startup even
without a configured entry, so a broken import/manifest surfaces here.

"Frontend comes up" is verified by the docker-compose healthcheck
alone (`docker compose up --wait`, in the docker_compose_up fixture) -
deliberately not by an additional HTTP request from the test process
itself. The healthcheck runs inside the container via loopback, so
it's immune to a class of runner network topology (Docker-outside-of-
Docker job containers that can't route to sibling bridge networks -
confirmed present on at least one runner this suite runs on) that an
external request would be exposed to.
"""
from __future__ import annotations

from .conftest import container_logs


def test_home_assistant_boots_with_integration_mounted(docker_compose_up):
    logs = container_logs()
    error_lines = [
        line
        for line in logs.splitlines()
        if "hu_energy_tariff" in line and ("ERROR" in line or "Traceback" in line)
    ]
    assert not error_lines, "hu_energy_tariff raised errors during startup:\n" + "\n".join(
        error_lines
    )
