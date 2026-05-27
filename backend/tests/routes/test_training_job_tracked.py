"""Regression: _run_training_job uses _logged_task for visibility."""
import inspect


def test_training_job_uses_logged_task():
    import routes.ml_predict_api as m
    src = inspect.getsource(m)
    assert 'asyncio.create_task(_run_training_job(' not in src
    assert '_logged_task' in src, "_logged_task wrap missing"
