"""Data-quality checks as code: SQL invariants over the RAW -> CORE pipeline and cross-source reconciliation."""
from .checks import CHECKS, Check, Result, run_checks

__all__ = ["CHECKS", "Check", "Result", "run_checks"]
