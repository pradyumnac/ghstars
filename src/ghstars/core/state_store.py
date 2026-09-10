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

    def __init__(self, base_dir: Path, *, create: bool = True) -> None:
        self.base_dir = Path(base_dir)
        if create:
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
            data = _read_json(self._stars_path)
        return [Star.model_validate(item) for item in data]

    def save_stars(
        self, stars: list[Star], *, lock_timeout: float = _DEFAULT_TIMEOUT
    ) -> None:
        with self.lock(timeout=lock_timeout):
            payload = [star.model_dump(mode="json") for star in stars]
            atomic_write(self._stars_path, json.dumps(payload, indent=2))

    def load_lists(self, *, lock_timeout: float = _DEFAULT_TIMEOUT) -> list[List]:
        with self.lock(timeout=lock_timeout):
            if not self._lists_path.exists():
                return []
            data = _read_json(self._lists_path)
        return [List.model_validate(item) for item in data]

    def load_stars_and_lists(
        self, *, lock_timeout: float = _DEFAULT_TIMEOUT
    ) -> tuple[list[Star], list[List]]:
        """Read Stars and Lists under one lock for a consistent snapshot."""
        with self.lock(timeout=lock_timeout):
            return self.load_stars(lock_timeout=lock_timeout), self.load_lists(
                lock_timeout=lock_timeout
            )

    def read_existing_stars_and_lists(self) -> tuple[list[Star], list[List]]:
        """Read an existing snapshot without creating directories or locks."""
        if not self.base_dir.exists():
            return [], []
        lock_path = self.base_dir / ".lock"
        if lock_path.exists():
            with FileLock(str(lock_path)):
                return self._read_existing_stars_and_lists()
        return self._read_existing_stars_and_lists()

    def _read_existing_stars_and_lists(self) -> tuple[list[Star], list[List]]:
        stars_data = _read_json(self._stars_path) if self._stars_path.exists() else []
        lists_data = _read_json(self._lists_path) if self._lists_path.exists() else []
        return (
            [Star.model_validate(item) for item in stars_data],
            [List.model_validate(item) for item in lists_data],
        )

    def save_lists(
        self, lists: list[List], *, lock_timeout: float = _DEFAULT_TIMEOUT
    ) -> None:
        with self.lock(timeout=lock_timeout):
            payload = [lst.model_dump(mode="json") for lst in lists]
            atomic_write(self._lists_path, json.dumps(payload, indent=2))

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
            data = _read_json(self._retriage_path)
        return [RetriageEntry.model_validate(item) for item in data]

    def save_retriage(
        self, entries: list[RetriageEntry], *, lock_timeout: float = _DEFAULT_TIMEOUT
    ) -> None:
        with self.lock(timeout=lock_timeout):
            payload = [entry.model_dump(mode="json") for entry in entries]
            atomic_write(self._retriage_path, json.dumps(payload, indent=2))


def _read_json(path: Path) -> list[object]:
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, list):
            raise TypeError(f"state file {path} must contain a JSON array")
        return data
    except (OSError, json.JSONDecodeError) as exc:
        raise exc from None


def atomic_write(path: Path, content: str) -> None:
    """Write via a same-directory temp file + rename, so a reader never sees
    a truncated file and a process killed mid-write never corrupts `path`.

    Public (not module-private) because `ghstars.core.export.run_export`
    shares it -- an export output file, read by some downstream pipeline
    of the user's own, needs the same guarantee as `stars.json`/
    `lists.json` here.
    """
    tmp_path = path.with_name(f"{path.name}.tmp")
    tmp_path.write_text(content)
    tmp_path.replace(path)
