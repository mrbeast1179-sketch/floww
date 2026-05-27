"""ML service errors and quality gates."""

class DegenerateModelError(Exception):
    """Raised when a model fails pre-save quality gates.

    Checks include: class balance, feature variance, prediction distribution,
    no future leakage, holdout untouched.
    """
    pass
