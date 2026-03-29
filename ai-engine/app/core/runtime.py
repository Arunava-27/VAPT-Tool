"""
Runtime configuration overrides.

Allows changing active provider/model via API without restarting the container.
Values reset to defaults on container restart; for persistence across restarts
these should be saved to Redis (future work).
"""

_overrides: dict = {}


def get(key: str, default=None):
    return _overrides.get(key, default)


def set_override(key: str, value) -> None:
    _overrides[key] = value


def all_overrides() -> dict:
    return dict(_overrides)
