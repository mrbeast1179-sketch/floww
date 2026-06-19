"""
backend/domain/

Pure-function domain primitives -- stateless math kernels with no I/O, no logging
state, and no network dependencies.

These primitives are the deterministic core of the floww quantitative stack.
Each module re-exports a small, well-specified set of functions (Black-Scholes,
SABR, Hawkes, ...) that downstream services/*.py classes orchestrate around.

Architecture convention (mirrors backend/bs_greeks.py):
  * Module-level functions only -- never classes.
  * Guard clauses return 0.0 for invalid inputs (F <= 0, K <= 0, T <= 0, etc.).
  * Numerical errors are silenced (no log spam at the math kernel).
  * Pure functions are deterministically testable with hand-computed values.
  * Compositionally layered: services/*.py wrap, persist, calibrate; domain/*.py
    compute.
"""

from __future__ import annotations
