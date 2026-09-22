from __future__ import annotations

import subprocess
from pathlib import Path

from . import identity


class NetError(RuntimeError):
    pass


def script_path() -> Path:
    installed = Path("/usr/local/bin/net-rotate")
    if installed.is_file():
        return installed
    repo = Path(__file__).resolve().parents[1] / "net-rotate.sh"
    if repo.is_file():
        return repo
    raise NetError("找不到 net-rotate")


def rotate(name: str, start: bool = True, progress=None) -> dict:
    if not identity.valid_name(name):
        raise NetError(f"名字不合法: {name}")
    log = progress or (lambda _msg: None)
    cmd = [str(script_path()), name]
    if not start:
        cmd.append("--no-start")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert proc.stdout is not None
    lines: list[str] = []
    for line in proc.stdout:
        line = line.rstrip("\n")
        lines.append(line)
        log(line)
    rc = proc.wait()
    if rc != 0:
        tail = next((x for x in reversed(lines) if x.strip()), "")
        raise NetError(tail or f"net-rotate 退出 {rc}")
    return {"name": name, "start": start}
