import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock

from ghstars.core.models import List, RetriageEntry, Star

_DEFAULT_TIMEOUT = 5.0


class StateStore:
    """Local snapshot of Stars/Lists under a directory, lockfile-guarded.

    Never auto-commits to git and never auto-inits one (ADR 0002). The
    caller decides.
    """

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._file_lock = FileLock(str(self.base_dir / ".lock"))

    @property
    def _stars_path(self) -> Path:
        return self.base_dir / "stars.json"

    @property
    def _lists_path(self) -> Path:
        return self.base_dir / "lists.json"

    @property
    def _retriage_path(self) -> Path:
        return self.base_dir / "retriage.json"

    @contextmanager
    def lock(self, timeout: float = _DEFAULT_TIMEOUT) -> Iterator[None]:
        with self._file_lock.acquire(timeout=timeout):
            yield

    def load_stars(self, *, lock_timeout: float = _DEFAULT_TIMEOUT) -> list[Star]:
        with self.lock(timeout=lock_timeout):
            if not self._stars_path.exists():
                return []
            data = json.loads(self._stars_path.read_text())
        return [Star.model_validate(item) for item in data]

    def save_stars(
        self, stars: list[Star], *, lock_timeout: float = _DEFAULT_TIMEOUT
    ) -> None:
        with self.lock(timeout=lock_timeout):
            payload = [star.model_dump(mode="json") for star in stars]
            _atomic_write(self._stars_path, json.dumps(payload, indent=2))

    def load_lists(self, *, lock_timeout: float = _DEFAULT_TIMEOUT) -> list[List]:
        with self.lock(timeout=lock_timeout):
            if not self._lists_path.exists():
                return []
            data = json.loads(self._lists_path.read_text())
        return [List.model_validate(item) for item in data]

    def save_lists(
        self, lists: list[List], *, lock_timeout: float = _DEFAULT_TIMEOUT
    ) -> None:
        with self.lock(timeout=lock_timeout):
            payload = [lst.model_dump(mode="json") for lst in lists]
            _atomic_write(self._lists_path, json.dumps(payload, indent=2))

    def load_retriage(
        self, *, lock_timeout: float = _DEFAULT_TIMEOUT
    ) -> list[RetriageEntry]:
        """Local-only conflict queue (ticket 05). Never synced to GitHub,
        never a `UserList` -- just another JSON file under `base_dir`,
        same as `stars.json`/`lists.json`.
        """
        with self.lock(timeout=lock_timeout):
            if not self._retriage_path.exists():
                return []
            data = json.loads(self._retriage_path.read_text())
        return [RetriageEntry.model_validate(item) for item in data]

    def save_retriage(
        self, entries: list[RetriageEntry], *, lock_timeout: float = _DEFAULT_TIMEOUT
    ) -> None:
        with self.lock(timeout=lock_timeout):
            payload = [entry.model_dump(mode="json") for entry in entries]
            _atomic_write(self._retriage_path, json.dumps(payload, indent=2))


def _atomic_write(path: Path, content: str) -> None:
    """Write via a same-directory temp file + rename, so a reader never sees
    a truncated file and a process killed mid-write never corrupts `path`.
    """
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(content)
    tmp_path.replace(path)
