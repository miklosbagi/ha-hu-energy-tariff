"""Smoke test: the integration loads cleanly inside a real Home
Assistant container.

This intentionally does not walk through the config flow to create a
live config entry - that requires completing HA onboarding/auth, which
is a heavier fast-follow (see README "Testing" section). It verifies
the two things most likely to silently break the integration: the
frontend comes up at all with custom_components/hu_energy_tariffs
mounted, and the container logs show no import/setup traceback for our
domain - HA validates every custom_components manifest at startup even
without a configured entry, so a broken import/manifest surfaces here.
"""
from __future__ import annotations

from .conftest import container_logs, wait_for_frontend


def test_home_assistant_boots_with_integration_mounted(docker_compose_up):
    wait_for_frontend()

    logs = container_logs()
    error_lines = [
        line
        for line in logs.splitlines()
        if "hu_energy_tariffs" in line and ("ERROR" in line or "Traceback" in line)
    ]
    assert not error_lines, "hu_energy_tariffs raised errors during startup:\n" + "\n".join(
        error_lines
    )
