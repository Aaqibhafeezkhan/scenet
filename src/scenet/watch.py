"""Dependency-aware file watching for the command-line build."""

import io
import os
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO


def _path(value: object) -> Path | None:
    """Return a resolved path for a file argument, if it names one."""
    try:
        return Path(os.fsdecode(value)).resolve()
    except (TypeError, ValueError, OSError):
        return None


@contextmanager
def track_reads() -> Iterator[set[Path]]:
    """Record files opened for reading while one compilation runs.

    Patching io.open captures pathlib reads as well as ordinary file opens. The patch is
    scoped to the synchronous compile and is always restored, including on a failed build.
    """
    dependencies: set[Path] = set()
    original_open = io.open

    def tracked_open(file: object, mode: str = "r", *args: object, **kwargs: object):
        if "r" in mode or "+" in mode:
            path = _path(file)
            if path is not None and path.is_file():
                dependencies.add(path)
        return original_open(file, mode, *args, **kwargs)

    io.open = tracked_open
    try:
        yield dependencies
    finally:
        io.open = original_open


def snapshot(paths: Iterable[Path]) -> dict[Path, tuple[int, int] | None]:
    """Record modification time and size, retaining missing files for later creation."""
    result: dict[Path, tuple[int, int] | None] = {}
    for path in paths:
        try:
            stat = path.stat()
            result[path] = (stat.st_mtime_ns, stat.st_size)
        except OSError:
            result[path] = None
    return result


def wait_for_change(
    paths: Iterable[Path],
    previous: dict[Path, tuple[int, int] | None],
    *,
    interval: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
) -> set[Path]:
    """Wait until a tracked file is created, removed or modified."""
    watched = set(paths)
    while True:
        sleep(interval)
        current = snapshot(watched)
        changed = {path for path in watched if current.get(path) != previous.get(path)}
        if changed:
            return changed
