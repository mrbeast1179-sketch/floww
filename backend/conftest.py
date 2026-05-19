"""backend/conftest.py — shared test fixtures."""
import os

os.environ.setdefault("TESTING", "1")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_confluence_decoder")
