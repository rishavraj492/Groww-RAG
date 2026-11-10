import socket

import pytest

_BLOCKED_HOST_MARKERS = (
    "groww.in",
    "hdfcfund.com",
    "sebi.gov.in",
    "amfiindia.com",
    "groq.com",
    "openai.com",
)


@pytest.fixture(autouse=True)
def block_corpus_network(monkeypatch):
    """Default tests must not resolve Groww, the AMC, SEBI, or AMFI."""
    real_getaddrinfo = socket.getaddrinfo

    def guarded(host, *args, **kwargs):
        if isinstance(host, str) and any(marker in host for marker in _BLOCKED_HOST_MARKERS):
            raise AssertionError(f"test tried to resolve {host}")
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", guarded)
