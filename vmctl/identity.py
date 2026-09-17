from __future__ import annotations

import random
import re
import uuid as uuidlib

OUI = {
    "rtl8125": "00:e0:4c",
    "rtl8139": "00:e0:4c",
    "e1000e": "3c:97:0e",
    "e1000": "3c:97:0e",
    "virtio": "3c:97:0e",
}
DEFAULT_OUI = "3c:97:0e"
NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


def valid_name(name: str) -> bool:
    return bool(NAME_RE.match(name))


def gen_uuid() -> str:
    return str(uuidlib.uuid4())


def gen_alnum(n: int) -> str:
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return "".join(chars[random.randrange(36)] for _ in range(n))


def nic_model(xml: str) -> str:
    m = re.search(r"<model type=['\"]([^'\"]+)['\"]", xml)
    return m.group(1) if m else ""


def gen_mac(model: str = "") -> str:
    oui = OUI.get(model.lower(), DEFAULT_OUI)
    return "%s:%02x:%02x:%02x" % (
        oui,
        random.randrange(256),
        random.randrange(256),
        random.randrange(256),
    )


def new_identity(xml: str) -> dict:
    return {
        "uuid": gen_uuid(),
        "mac": gen_mac(nic_model(xml)),
        "disk_sn": gen_alnum(12),
        "sys_sn": gen_alnum(12),
        "board_sn": gen_alnum(12),
        "chassis_sn": gen_alnum(12),
        "mem_sn": gen_alnum(6),
    }


def rewrite_domain(
    xml: str,
    *,
    name: str,
    disk_path: str,
    nvram_path: str,
    disk_format: str = "raw",
    ident: dict | None = None,
) -> str:
    ident = ident or new_identity(xml)
    xml = re.sub(r"<name>[^<]*</name>", f"<name>{name}</name>", xml, count=1)
    xml = re.sub(r"<uuid>[^<]*</uuid>", f"<uuid>{ident['uuid']}</uuid>", xml, count=1)
    xml = re.sub(
        r"(<nvram\b[^>]*>)[^<]*(</nvram>)",
        rf"\g<1>{nvram_path}\g<2>",
        xml,
        count=1,
    )
    xml = re.sub(
        r"(<disk type=['\"]file['\"] device=['\"]disk['\"]>.*?<source file=['\"])[^'\"]*",
        rf"\g<1>{disk_path}",
        xml,
        count=1,
        flags=re.S,
    )
    xml = re.sub(
        r"(<disk type=['\"]file['\"] device=['\"]disk['\"]>.*?<driver name=['\"]qemu['\"] type=['\"])[^'\"]*",
        rf"\g<1>{disk_format}",
        xml,
        count=1,
        flags=re.S,
    )
    xml = re.sub(
        r"(<disk type=['\"]file['\"] device=['\"]disk['\"]>.*?<serial>)[^<]*",
        rf"\g<1>{ident['disk_sn']}",
        xml,
        count=1,
        flags=re.S,
    )
    xml = re.sub(
        r"<mac address=['\"][^'\"]*['\"]",
        f"<mac address='{ident['mac']}'",
        xml,
        count=1,
    )
    xml = re.sub(
        r"(type=1,[^'\"]*serial=)[A-Z0-9]+",
        rf"\g<1>{ident['sys_sn']}",
        xml,
    )
    xml = re.sub(
        r"(type=1,[^'\"]*uuid=)[0-9a-fA-F-]+",
        rf"\g<1>{ident['uuid']}",
        xml,
    )
    xml = re.sub(
        r"(type=2,[^'\"]*serial=)[A-Z0-9]+",
        rf"\g<1>{ident['board_sn']}",
        xml,
    )
    xml = re.sub(
        r"(type=3,[^'\"]*serial=)[A-Z0-9]+",
        rf"\g<1>{ident['chassis_sn']}",
        xml,
    )
    xml = re.sub(
        r"(type=17,[^'\"]*serial=)[A-Z0-9]+",
        rf"\g<1>{ident['mem_sn']}",
        xml,
    )
    xml = re.sub(
        r"(<disk type=['\"]file['\"] device=['\"]disk['\"]>.*?<boot order=['\"])\d+",
        r"\g<1>1",
        xml,
        count=1,
        flags=re.S,
    )
    xml = re.sub(
        r"(<disk type=['\"]file['\"] device=['\"]cdrom['\"]>.*?<boot order=['\"])\d+",
        r"\g<1>2",
        xml,
        count=1,
        flags=re.S,
    )
    xml = re.sub(r"\n\s*<backingStore/>", "", xml)
    xml = re.sub(r"\n\s*<resource>\s*<partition>[^<]*</partition>\s*</resource>", "", xml)
    xml = re.sub(r"\n\s*<seclabel\b[^>]*>.*?</seclabel>", "", xml, flags=re.S)
    xml = re.sub(r"\n\s*<hostdev\b.*?</hostdev>", "", xml, flags=re.S)
    xml = re.sub(r"\n\s*<qemu:override>.*?</qemu:override>", "", xml, flags=re.S)
    xml = re.sub(
        r"<graphics type=['\"]vnc['\"][^>]*>",
        "<graphics type='vnc' port='-1' autoport='yes' listen='127.0.0.1'>",
        xml,
        count=1,
    )
    return xml
