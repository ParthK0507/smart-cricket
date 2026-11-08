"""Standard result format returned by every engine function."""


def success(data, sample=None, warnings=None, chart=None):
    return {"ok": True, "data": data, "sample": sample or {},
            "warnings": warnings or [], "chart": chart}


def failure(message, candidates=None):
    return {"ok": False, "error": message, "candidates": candidates or [],
            "data": {}, "sample": {}, "warnings": [], "chart": None}


def small_sample(n, minimum, label):
    """Return a warning string when n is below minimum, otherwise None."""
    if n < minimum:
        return f"small sample: only {n} {label} (fewer than {minimum})"
    return None