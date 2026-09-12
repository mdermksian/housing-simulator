"""Replace a destination only after its complete contents have been written."""

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile


@contextmanager
def atomic_destination(path: str | Path) -> Iterator[Path]:
    destination = Path(path)
    with NamedTemporaryFile(dir=destination.parent, delete=False) as temporary:
        temporary_path = Path(temporary.name)
    try:
        yield temporary_path
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)
