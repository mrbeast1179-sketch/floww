"""Tests for services/position_reconciler.py — Round 11 Agent 01.

The module is currently a stub (constants + docstring only).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services import position_reconciler


class TestReconcilerConstants:
    def test_reconcile_interval_is_60_seconds(self):
        assert position_reconciler.RECONCILE_INTERVAL_S == 60

    def test_reconcile_interval_is_positive(self):
        assert isinstance(position_reconciler.RECONCILE_INTERVAL_S, int)
        assert position_reconciler.RECONCILE_INTERVAL_S > 0

    def test_reconcile_interval_is_reasonable(self):
        assert 10 <= position_reconciler.RECONCILE_INTERVAL_S <= 3600


class TestReconcilerModule:
    def test_module_has_docstring(self):
        assert position_reconciler.__doc__ is not None
        assert len(position_reconciler.__doc__) > 20

    def test_no_public_classes_yet(self):
        public_classes = [
            name for name, obj in vars(position_reconciler).items()
            if isinstance(obj, type) and not name.startswith("_")
        ]
        assert len(public_classes) == 0
