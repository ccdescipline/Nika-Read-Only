from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

URI = os.environ.get("LIBVIRT_DEFAULT_URI", "qemu:///system")
STATE_DIR = Path(os.environ.get("VMCTL_STATE", "/var/lib/vmctl"))
CONFIG_PATH = Path(os.environ.get("VMCTL_CONFIG", "/etc/vmctl.json"))
IMAGES_DIR = Path("/var/lib/libvirt/images")
NVRAM_DIR = Path("/var/lib/libvirt/qemu/nvram")
HOST_RDP_PORT = 3389
GUEST_RDP_PORT = 3389
RDP_COMMENT = "vmctl-rdp"
BIND = "0.0.0.0"
PORT = 8787
LIBVIRT_QEMU = "libvirt-qemu"
LIBVIRT_GROUP = "kvm"


def load() -> dict:
    data = {
        "uri": URI,
        "state_dir": str(STATE_DIR),
        "images_dir": str(IMAGES_DIR),
        "nvram_dir": str(NVRAM_DIR),
        "host_rdp_port": HOST_RDP_PORT,
        "guest_rdp_port": GUEST_RDP_PORT,
        "rdp_comment": RDP_COMMENT,
        "bind": BIND,
        "port": PORT,
        "ext_if": detect_ext_if(),
    }
    if CONFIG_PATH.is_file():
        try:
            data.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            pass
    data.setdefault("ext_if", detect_ext_if())
    return data


def state_dir() -> Path:
    p = Path(load()["state_dir"])
    p.mkdir(parents=True, exist_ok=True)
    return p


def detect_ext_if() -> str:
    try:
        out = subprocess.check_output(
            ["ip", "-4", "route", "show", "default"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        parts = out.split()
        if "dev" in parts:
            return parts[parts.index("dev") + 1]
    except (OSError, subprocess.CalledProcessError, IndexError):
        pass
    return "wlo1"


def host_ipv4(iface: str | None = None) -> str:
    iface = iface or load()["ext_if"]
    try:
        out = subprocess.check_output(
            ["ip", "-4", "-o", "addr", "show", "dev", iface],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        for tok in out.split():
            if "/" in tok and not tok.startswith("inet"):
                return tok.split("/")[0]
            if tok.count(".") == 3 and "/" in tok:
                return tok.split("/")[0]
    except (OSError, subprocess.CalledProcessError):
        pass
    return ""
