from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

from . import config, virt

TARGET_FILE = "rdp-target"


class RdpError(RuntimeError):
    pass


def _cfg():
    return config.load()


def _target_path() -> Path:
    return config.state_dir() / TARGET_FILE


def saved_target() -> str:
    p = _target_path()
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8").strip()


def save_target(name: str) -> None:
    _target_path().write_text(name + "\n", encoding="utf-8")


def _run(args: list[str]) -> str:
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "").strip()
        raise RdpError(f"{' '.join(args)}: {err or r.returncode}")
    return r.stdout


def _iptables(args: list[str]) -> str:
    return _run(["iptables"] + args)


def _delete_matching(table: str | None, chain: str, needle: str, extra: list[str] | None = None) -> int:
    n = 0
    extra = extra or []
    while True:
        cmd = ["-L", chain, "--line-numbers", "-n"]
        if extra:
            cmd.extend(extra)
        if table:
            out = _iptables(["-t", table] + cmd)
        else:
            out = _iptables(cmd)
        line_no = ""
        for line in out.splitlines():
            if needle in line and re.match(r"^\d+", line.strip()):
                line_no = line.split()[0]
                break
        if not line_no:
            return n
        if table:
            _iptables(["-t", table, "-D", chain, line_no])
        else:
            _iptables(["-D", chain, line_no])
        n += 1


def live_dnat_ip() -> str:
    cfg = _cfg()
    port = str(cfg["host_rdp_port"])
    try:
        out = _iptables(["-t", "nat", "-L", "PREROUTING", "-n"])
    except RdpError:
        return ""
    for line in out.splitlines():
        if f"dpt:{port}" not in line:
            continue
        m = re.search(r"to:([\d.]+):\d+", line)
        if m:
            return m.group(1)
    return ""


def wait_ip(name: str, timeout: int = 30) -> str:
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        last = virt.domain_ip(name)
        if last:
            return last
        time.sleep(1)
    raise RdpError(f"30 秒内没拿到 {name} 的 IP（网络是否 up？）")


def apply(name: str, ip: str | None = None) -> dict:
    cfg = _cfg()
    if not virt.exists(name):
        raise RdpError(f"VM '{name}' 不存在")
    if not virt.is_running(name):
        raise RdpError(f"VM '{name}' 未运行")
    ip = ip or wait_ip(name)
    host_port = str(cfg["host_rdp_port"])
    guest_port = str(cfg["guest_rdp_port"])
    comment = cfg["rdp_comment"]
    ext_if = cfg["ext_if"]

    _delete_matching("nat", "PREROUTING", f"dpt:{host_port}")
    _delete_matching(None, "LIBVIRT_FWI", comment, extra=["-v"])

    _iptables([
        "-t", "nat", "-A", "PREROUTING",
        "-i", ext_if, "-p", "tcp", "--dport", host_port,
        "-m", "comment", "--comment", comment,
        "-j", "DNAT", "--to-destination", f"{ip}:{guest_port}",
    ])
    try:
        _iptables([
            "-I", "LIBVIRT_FWI", "1",
            "-d", f"{ip}/32", "-p", "tcp", "--dport", guest_port,
            "-m", "comment", "--comment", comment,
            "-j", "ACCEPT",
        ])
        fwi = True
    except RdpError:
        fwi = False

    save_target(name)
    _persist()
    host_ip = config.host_ipv4(ext_if)
    return {
        "name": name,
        "ip": ip,
        "host": f"{host_ip or '<宿主机>'}:{host_port}",
        "ext_if": ext_if,
        "fwi": fwi,
    }


def switch(name: str, start_if_down: bool = False) -> dict:
    if start_if_down and virt.exists(name) and not virt.is_running(name):
        virt.start(name)
        time.sleep(2)
    return apply(name)


def hook(name: str) -> dict | None:
    if saved_target() != name:
        return None
    if not virt.is_running(name):
        return None
    return apply(name)


def rebind_saved() -> dict | None:
    name = saved_target()
    if not name:
        return None
    if not virt.exists(name) or not virt.is_running(name):
        return None
    return apply(name)


def status() -> dict:
    cfg = _cfg()
    name = saved_target()
    dnat_ip = live_dnat_ip()
    ip = ""
    running = False
    if name and virt.exists(name):
        running = virt.is_running(name)
        if running:
            ip = virt.domain_ip(name)
    host_ip = config.host_ipv4(cfg["ext_if"])
    return {
        "name": name,
        "ip": ip,
        "dnat_ip": dnat_ip,
        "running": running,
        "host": f"{host_ip or '<宿主机>'}:{cfg['host_rdp_port']}",
        "ext_if": cfg["ext_if"],
        "stale": bool(dnat_ip and ip and dnat_ip != ip),
    }


def _persist() -> None:
    helper = "/usr/lib/netfilter-persistent/plugins.d/15-ip4tables"
    try:
        if Path(helper).is_file():
            subprocess.run(["netfilter-persistent", "save"], capture_output=True, check=False)
            return
        rules = Path("/etc/iptables/rules.v4")
        if rules.parent.is_dir():
            out = subprocess.check_output(["iptables-save"], text=True)
            rules.write_text(out, encoding="utf-8")
    except OSError:
        pass
