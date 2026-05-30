"""Regression: paper_trader.py wraps Mongo inserts in error logging."""
import inspect


def test_paper_trader_inserts_are_logged():
    import services.paper_trader as pt
    src = inspect.getsource(pt)
    assert 'asyncio.create_task(self.mongo.insert_one(order))' not in src
    assert 'asyncio.create_task(self.mongo.insert_one(doc))' not in src
    assert '_log_failed_insert' in src, "helper _log_failed_insert missing"
