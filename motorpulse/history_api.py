"""MP-040: strict, read-only localhost REST query contract for MP-012 history.

No SQL or simulator control lives here. Exact UTC range filtering occurs in
SQLite with microsecond timestamps and session-scoped, monotonic row-ID cursors.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qsl

from .storage import _time_bounds, _filter_text

HISTORY_API_VERSION = "1.0.0"
DEFAULT_LIMIT = 50
MAX_HTTP_LIMIT = 100
MAX_QUERY_BYTES = 2048
ROUTES = {
    "/api/history/sessions": "sessions",
    "/api/history/snapshots": "snapshots",
    "/api/history/events": "events",
    "/api/history/alerts": "alerts",
}
COMMON = frozenset(("limit", "before_id"))
ALLOW = {
    "sessions": COMMON,
    "snapshots": COMMON | {"session_id", "start_utc", "end_utc"},
    "events": COMMON | {"session_id", "asset_id", "start_utc", "end_utc"},
    "alerts": COMMON | {"session_id", "asset_id", "start_utc", "end_utc"},
}
_HEX = frozenset("0123456789ABCDEFabcdef")
_DIGITS = re.compile(r"[1-9][0-9]*\Z")


def _unsigned(value: str, key: str, maximum: int) -> int:
    if _DIGITS.fullmatch(value) is None or len(value) > 19:
        raise ValueError(f"{key} must be a positive decimal integer")
    number = int(value)
    if number > maximum:
        raise ValueError(f"{key} exceeds allowed maximum {maximum}")
    return number


def parse_query(resource: str, raw_query: str) -> dict:
    """Reject duplicate/unknown keys, malformed encoding and ambiguous timestamps."""
    if resource not in ALLOW:
        raise ValueError("unknown history resource")
    if type(raw_query) is not str or len(raw_query.encode("utf-8")) > MAX_QUERY_BYTES:
        raise ValueError("history query is too long")
    for i, char in enumerate(raw_query):
        if char == "%" and (
            i+2 >= len(raw_query) or raw_query[i+1] not in _HEX
            or raw_query[i+2] not in _HEX
        ):
            raise ValueError("malformed percent encoding")
    try:
        pairs = parse_qsl(raw_query, keep_blank_values=True, strict_parsing=True,
                          encoding="utf-8", errors="strict", max_num_fields=8)
    except (ValueError, UnicodeError) as exc:
        raise ValueError("invalid history query encoding or field count") from exc
    raw = {}
    for key, value in pairs:
        if key not in ALLOW[resource]:
            raise ValueError(f"unsupported query parameter {key!r} for {resource}")
        if key in raw:
            raise ValueError(f"duplicate query parameter {key!r}")
        if not value or value != value.strip():
            raise ValueError(f"empty or padded query parameter {key!r}")
        raw[key] = value
    limit = _unsigned(raw.pop("limit", str(DEFAULT_LIMIT)), "limit", MAX_HTTP_LIMIT)
    before = raw.pop("before_id", None)
    params = {"limit": limit}
    if before is not None:
        params["before_id"] = _unsigned(before, "before_id", 2**63-1)
    for key in ("session_id", "asset_id"):
        if key in raw:
            _filter_text(raw[key], key)
            params[key] = raw[key]
    start, end = raw.get("start_utc"), raw.get("end_utc")
    _time_bounds(start, end)
    if start is not None:
        params["start_utc"] = start
    if end is not None:
        params["end_utc"] = end
    return params


def history_page(controller, resource: str, params: dict) -> dict:
    """Fetch limit+1 rows to distinguish a complete page from the last page."""
    if resource not in ALLOW:
        raise ValueError("unknown history resource")
    limit = params["limit"]
    if resource == "sessions":
        rows = controller.history_sessions(limit=limit + 1,
                                           before_id=params.get("before_id"))
    elif resource == "snapshots":
        rows = controller.history_snapshots(**{**params, "limit": limit + 1})
    elif resource == "events":
        rows = controller.history_events(**{**params, "limit": limit + 1})
    else:
        rows = controller.history_alerts(**{**params, "limit": limit + 1})
    has_more = len(rows) > limit
    selected = rows[:limit]
    return {
        "api_version": HISTORY_API_VERSION,
        "source": "synthetic",
        "resource": resource,
        "items": selected,
        "page": {
            "limit": limit,
            "count": len(selected),
            "has_more": has_more,
            "next_before_id": selected[-1]["id"] if has_more else None,
            "order": "id_desc",
        },
        "filters": {key: value for key, value in params.items() if key != "limit"},
    }
