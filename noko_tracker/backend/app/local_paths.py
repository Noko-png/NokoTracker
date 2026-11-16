import os
from pathlib import Path


def check_local_path(path: str | Path) -> None:
    if os.fspath(path).replace("\\", "/").startswith("//"):
        raise ValueError("Netzwerkpfade sind nicht erlaubt.")
    if os.name == "nt":
        from ctypes import windll

        drive_remote = 4
        if windll.kernel32.GetDriveTypeW(Path(path).absolute().anchor) == drive_remote:
            raise ValueError("Netzwerkpfade sind nicht erlaubt.")


def resolve_local_path(path: str | Path) -> Path:
    check_local_path(path)
    resolved = Path(path).resolve()
    check_local_path(resolved)
    return resolved
