"""Bounded private feature copies for synchronous local physical operations."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator, Sequence

from .physical_dataset import MAX_CARDS, MAX_FEATURE_BYTES

MAX_SNAPSHOT_BYTES = 4 * MAX_FEATURE_BYTES
_ACTIVE: ContextVar[tuple[tuple[Path, ...], int] | None] = ContextVar(
    "physical_feature_snapshot", default=None
)


@contextmanager
def snapshot_features(
    paths: Sequence[str | Path], *, max_bytes: int = MAX_SNAPSHOT_BYTES
) -> Iterator[list[Path]]:
    """Capture one cohort; reuse exact active paths during synchronous replay."""
    if type(paths) not in (list, tuple) or not 3 <= len(paths) <= MAX_CARDS:
        raise ValueError("invalid number of physical feature files")
    sources = tuple(Path(path) for path in paths)
    active = _ACTIVE.get()
    if active is not None and sources == active[0]:
        if active[1] > max_bytes:
            raise ValueError("physical feature snapshot exceeds size limit")
        yield list(active[0])
        return

    total = 0
    with TemporaryDirectory(prefix="motorpulse-physical-") as directory:
        snapshots = []
        for index, source in enumerate(sources):
            if not source.is_file() or source.is_symlink():
                raise ValueError("feature source must be an existing non-symlink file")
            target = Path(directory) / f"{index}.jsonl"
            size = 0
            with source.open("rb") as incoming, target.open("xb") as outgoing:
                while chunk := incoming.read(1024 * 1024):
                    size += len(chunk)
                    total += len(chunk)
                    if size > MAX_FEATURE_BYTES or total > max_bytes:
                        raise ValueError("physical feature snapshot exceeds size limit")
                    outgoing.write(chunk)
            if size == 0:
                raise ValueError("physical feature snapshot is empty")
            snapshots.append(target)
        token = _ACTIVE.set((tuple(snapshots), total))
        try:
            yield list(snapshots)
        finally:
            _ACTIVE.reset(token)
