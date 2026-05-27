"""Regression: _prefetch_paid_oi is wrapped in _logged_task, not fire-and-forget."""
import inspect


def test_prefetch_call_uses_logged_task():
    import server
    src = inspect.getsource(server)
    assert 'asyncio.create_task(_prefetch_paid_oi())' not in src, \
        "_prefetch_paid_oi() still fire-and-forget"
    assert '_logged_task(_prefetch_paid_oi()' in src, \
        "_prefetch_paid_oi() not wrapped in _logged_task"
