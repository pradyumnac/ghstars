import subprocess
import zipfile
from pathlib import Path


def test_wheel_contains_py_typed(tmp_path: Path) -> None:
    project_root = Path(__file__).parent.parent
    subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(tmp_path)],
        check=True,
        cwd=project_root,
        capture_output=True,
        text=True,
    )
    wheel = next(tmp_path.glob("ghstars-*.whl"))

    with zipfile.ZipFile(wheel) as archive:
        assert "ghstars/py.typed" in archive.namelist()
