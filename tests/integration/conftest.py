"""CDP Spark integration test fixtures."""

from __future__ import annotations

import pytest

from guide_validator.cdp_spark import build_spark_session, cdp_configured
from guide_validator.template_renderer import CdpEnv


@pytest.fixture(scope="session")
def cdp_env() -> CdpEnv:
    # cdp_configured() loads .env; build env only after that so a file-based
    # .env (not exported to the shell) is picked up correctly.
    if not cdp_configured():
        pytest.skip("CDP integration env not configured (CDP_SPARK_MASTER, TEST_DATABASE, TEST_TABLE)")
    env = CdpEnv.from_env()
    if not env.is_configured():
        pytest.skip("TEST_DATABASE and TEST_TABLE must be set for CDP integration tests")
    return env


@pytest.fixture(scope="session")
def spark(cdp_env):  # noqa: ARG001 - cdp_env triggers skip when unset
    session = build_spark_session()
    yield session
    session.stop()
