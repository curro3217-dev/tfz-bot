"""
ML signal-quality filter — scores live signals with the trained model.

Loads ml_model.joblib (built by ml_train.py) and exposes the predicted win
probability for a signal, plus a pass/fail gate at the recommended cutoff.
Reuses ml_dataset._row so the live feature vector matches training exactly.

If the model file is missing, predict_win_prob returns None and passes() lets
everything through (fail-open) so the bot still works without the filter.
"""

import os
import numpy as np

from ml_dataset import _row, FEATURES

_MODEL_PATH = os.path.join(os.path.dirname(__file__), "ml_model.joblib")
_cache = {"loaded": False, "model": None, "features": None, "cutoff": 0.5}


def _load():
    if _cache["loaded"]:
        return _cache["model"]
    _cache["loaded"] = True
    if not os.path.exists(_MODEL_PATH):
        return None
    import joblib
    blob = joblib.load(_MODEL_PATH)
    _cache["model"] = blob["model"]
    _cache["features"] = blob.get("features", FEATURES)
    _cache["cutoff"] = blob.get("cutoff", 0.5)
    return _cache["model"]


def predict_win_prob(sig, trend_strength: float):
    """Return predicted win probability for a signal, or None if no model."""
    model = _load()
    if model is None:
        return None
    row = _row(sig, trend_strength, 0.0)
    x = np.array([[row[f] for f in _cache["features"]]], dtype=float)
    return float(model.predict_proba(x)[:, 1][0])


def passes(sig, trend_strength: float, cutoff: float = None) -> bool:
    """True if the signal clears the ML cutoff. Fail-open if no model."""
    p = predict_win_prob(sig, trend_strength)
    if p is None:
        return True
    return p >= (cutoff if cutoff is not None else _cache["cutoff"])


def cutoff() -> float:
    _load()
    return _cache["cutoff"]
