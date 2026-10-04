from collections import namedtuple

from scripts.network_monitor import _external


def test_loopback_is_not_reported_as_external():
    Address=namedtuple('Address','ip port')
    assert not _external(Address('127.0.0.1',8088))
    assert not _external(Address('::1',8087))
    assert _external(Address('203.0.113.10',443))
