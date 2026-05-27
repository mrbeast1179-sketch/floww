"""Regression: replay engine.start() task is stored for cancellation."""
import inspect
import re


def test_engine_start_task_is_stored():
    import routes.replay as r
    src = inspect.getsource(r)
    # Bare fire-and-forget: create_task with no assignment and no global decl
    lines = src.splitlines()
    bare_creates = [
        i for i, line in enumerate(lines)
        if re.search(r'^\s+asyncio\.create_task\(engine\.start\(\)\)', line)
        and 'global' not in lines[max(0, i-1)]
    ]
    assert not bare_creates, \
        f"engine.start() still fire-and-forget at lines {[i+1 for i in bare_creates]}"
    assert '_engine_task' in src, \
        "_engine_task not stored — cannot be cancelled"
