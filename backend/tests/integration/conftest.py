import os


def pytest_configure(config) -> None:  # noqa: ARG001
    os.environ.setdefault("BIONIC_BOT_INTEGRATION_TIMEOUT_S", "180")

