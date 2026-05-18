"""ML service errors and quality gates."""

class InsufficientRealDataError(Exception):
    """Raised when a code path that used to generate synthetic data is reached.

    Synthetic data is banned. Collect real data via scripts/backfill_* instead.
    """
    pass


class DegenerateModelError(Exception):
    """Raised when a model fails pre-save quality gates.

    Checks include: class balance, feature variance, prediction distribution,
    no future leakage, holdout untouched.
    """
    pass
