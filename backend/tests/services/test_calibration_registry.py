"""Calibration provenance registry: which signal bands are pinned vs claimed.

Every production signal band records its value, the basis the code itself
states, and the test that pins it — or None when no test does. Status
"pinned" means a test fails if the band moves; "claimed" means the code
asserts a calibration basis with no attached artifact. The registry is
self-validating: pinned entries must name test paths that exist on disk.

This changes no threshold and wires nothing. It makes the next calibration
decision explicit: work the `unpinned()` list, attach evidence, flip status.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.calibration_registry import (  # noqa: E402
    get_band,
    list_bands,
    unpinned,
)

BACKEND = Path(__file__).resolve().parents[2]


def test_every_band_has_basis_and_code_ref():
    for band in list_bands():
        assert band["signal"] and band["parameter"]
        assert band["value"] is not None
        assert isinstance(band["basis"], str) and band["basis"].strip()
        assert (BACKEND / band["code_ref"].split(":")[0]).exists()


def test_pinned_bands_name_existing_tests():
    pinned = [b for b in list_bands() if b["status"] == "pinned"]
    assert pinned, "registry must pin at least one band"
    for band in pinned:
        assert band["test_path"], f"{band['signal']} pinned without a test"
        assert (BACKEND / band["test_path"]).exists(), band["test_path"]


def test_claimed_bands_name_no_test():
    for band in unpinned():
        assert band["status"] == "claimed"
        assert band["test_path"] is None


def test_known_unpinned_are_exactly_the_gap_list():
    """The calibration work queue is enumerated, not open-ended."""
    names = sorted(f"{b['signal']}:{b['parameter']}" for b in unpinned())
    assert names == sorted([
        "composite:weights",
        "fragility:weights",
        "fragility:bands",
        "gex_plus:bands",
        "vex_scale:convention_factor",
    ])


def test_lookup_returns_full_record():
    band = get_band("kyle_lambda", "bands")
    assert band["value"] == [0.001, 0.005]
    assert band["status"] == "pinned"
