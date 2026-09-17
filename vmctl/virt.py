from __future__ import annotations

import re
from contextlib import contextmanager

import libvirt

from . import config

STATES = {
    libvirt.VIR_DOMAIN_NOSTATE: "nostate",
    libvirt.VIR_DOMAIN_RUNNING: "running",
    libvirt.VIR_DOMAIN_BLOCKED: "blocked",
    libvirt.VIR_DOMAIN_PAUSED: "paused",
    libvirt.VIR_DOMAIN_SHUTDOWN: "shutdown",
    libvirt.VIR_DOMAIN_SHUTOFF: "shut off",
    libvirt.VIR_DOMAIN_CRASHED: "crashed",
    libvirt.VIR_DOMAIN_PMSUSPENDED: "pmsuspended",
}


class VirtError(RuntimeError):
    pass


@contextmanager
def connection():
    uri = config.load()["uri"]
    conn = libvirt.open(uri)
    if conn is None:
        raise VirtError(f"cannot open {uri}")
    try:
        yield conn
    finally:
        conn.close()


def _dom(conn, name: str):
    try:
        return conn.lookupByName(name)
    except libvirt.libvirtError as e:
        raise VirtError(f"VM '{name}' 不存在") from e


def domain_xml(name: str, migratable: bool = True) -> str:
    with connection() as conn:
        flags = libvirt.VIR_DOMAIN_XML_MIGRATABLE if migratable else 0
        return _dom(conn, name).XMLDesc(flags)


def domain_ip(name: str) -> str:
    with connection() as conn:
        return _ip(_dom(conn, name), conn)


def _ip(dom, conn) -> str:
    if not dom.isActive():
        return ""
    try:
        addrs = dom.interfaceAddresses(
            libvirt.VIR_DOMAIN_INTERFACE_ADDRESSES_SRC_LEASE, 0
        )
        for info in addrs.values():
            for a in info.get("addrs") or []:
                if a.get("type") == libvirt.VIR_IP_ADDR_TYPE_IPV4:
                    return a.get("addr") or ""
    except libvirt.libvirtError:
        pass
    mac = ""
    xml = dom.XMLDesc(0)
    m = re.search(r"<mac address=['\"]([^'\"]+)['\"]", xml)
    if m:
        mac = m.group(1).lower()
    try:
        net = conn.networkLookupByName("default")
        for lease in net.DHCPLeases() or []:
            if (lease.get("mac") or "").lower() == mac and lease.get("ipaddr"):
                return lease["ipaddr"]
    except libvirt.libvirtError:
        pass
    return ""


def _vnc_port(xml: str) -> str:
    m = re.search(r"<graphics type=['\"]vnc['\"][^>]*port=['\"](-?\d+)['\"]", xml)
    if not m:
        return ""
    p = m.group(1)
    return "" if p in ("-1", "0") else p


def _mem_gib(kib: int) -> str:
    return f"{kib / 1024 / 1024:.0f}G"


def list_vms(rdp_name: str = "") -> list[dict]:
    with connection() as conn:
        out = []
        for dom in conn.listAllDomains(0):
            info = dom.info()
            xml = dom.XMLDesc(0)
            name = dom.name()
            ip = _ip(dom, conn) if dom.isActive() else ""
            mac_m = re.search(r"<mac address=['\"]([^'\"]+)['\"]", xml)
            model_m = re.search(r"<model type=['\"]([^'\"]+)['\"]", xml)
            disk_m = re.search(
                r"<disk type=['\"]file['\"] device=['\"]disk['\"]>.*?<source file=['\"]([^'\"]+)",
                xml,
                re.S,
            )
            item = {
                "name": name,
                "state": STATES.get(info[0], str(info[0])),
                "running": bool(dom.isActive()),
                "memory": _mem_gib(info[1]),
                "vcpus": info[3],
                "ip": ip,
                "mac": mac_m.group(1) if mac_m else "",
                "nic": model_m.group(1) if model_m else "",
                "disk": disk_m.group(1) if disk_m else "",
                "vnc": _vnc_port(xml) if dom.isActive() else "",
                "rdp": name == rdp_name,
            }
            out.append(item)
        out.sort(key=lambda x: (not x["running"], x["name"]))
        return out


def start(name: str) -> None:
    with connection() as conn:
        dom = _dom(conn, name)
        if dom.isActive():
            return
        if dom.create() != 0:
            raise VirtError(f"启动 {name} 失败")


def shutdown(name: str) -> None:
    with connection() as conn:
        dom = _dom(conn, name)
        if not dom.isActive():
            return
        if dom.shutdown() != 0:
            raise VirtError(f"关机 {name} 失败")


def destroy(name: str) -> None:
    with connection() as conn:
        dom = _dom(conn, name)
        if not dom.isActive():
            return
        if dom.destroy() != 0:
            raise VirtError(f"强制关机 {name} 失败")


def define_xml(xml: str) -> None:
    with connection() as conn:
        dom = conn.defineXML(xml)
        if dom is None:
            raise VirtError("virsh define 失败")


def exists(name: str) -> bool:
    with connection() as conn:
        try:
            conn.lookupByName(name)
            return True
        except libvirt.libvirtError:
            return False


def is_running(name: str) -> bool:
    with connection() as conn:
        return bool(_dom(conn, name).isActive())


def undefine(name: str, remove_nvram: bool = True) -> None:
    with connection() as conn:
        dom = _dom(conn, name)
        if dom.isActive():
            raise VirtError(f"VM '{name}' 还在跑，先 stop/destroy")
        flags = 0
        if remove_nvram and hasattr(libvirt, "VIR_DOMAIN_UNDEFINE_NVRAM"):
            flags |= libvirt.VIR_DOMAIN_UNDEFINE_NVRAM
        elif hasattr(libvirt, "VIR_DOMAIN_UNDEFINE_KEEP_NVRAM"):
            flags |= libvirt.VIR_DOMAIN_UNDEFINE_KEEP_NVRAM
        try:
            if flags:
                dom.undefineFlags(flags)
            else:
                dom.undefine()
        except libvirt.libvirtError as e:
            raise VirtError(f"undefine {name} 失败: {e}") from e


def all_disk_paths(except_name: str = "") -> set[str]:
    out: set[str] = set()
    with connection() as conn:
        for dom in conn.listAllDomains(0):
            if except_name and dom.name() == except_name:
                continue
            xml = dom.XMLDesc(0)
            for m in re.finditer(r"<source file=['\"]([^'\"]+)", xml):
                out.add(m.group(1))
    return out
