from __future__ import annotations

import grp
import os
import pwd
import re
import subprocess
from pathlib import Path

from . import config, identity, virt


class CloneError(RuntimeError):
    pass


def _images() -> Path:
    return Path(config.load()["images_dir"])


def _nvram_dir() -> Path:
    return Path(config.load()["nvram_dir"])


def _chown_libvirt(path: Path) -> None:
    uid = pwd.getpwnam(config.LIBVIRT_QEMU).pw_uid
    gid = grp.getgrnam(config.LIBVIRT_GROUP).gr_gid
    os.chown(path, uid, gid)
    os.chmod(path, 0o640)


def _disk_info(xml: str) -> tuple[str, str]:
    m = re.search(
        r"<disk type=['\"]file['\"] device=['\"]disk['\"]>.*?<source file=['\"]([^'\"]+)",
        xml,
        re.S,
    )
    if not m:
        raise CloneError("源 XML 里没有磁盘文件")
    path = m.group(1)
    fmt_m = re.search(
        r"<disk type=['\"]file['\"] device=['\"]disk['\"]>.*?<driver name=['\"]qemu['\"] type=['\"]([^'\"]+)",
        xml,
        re.S,
    )
    return path, (fmt_m.group(1) if fmt_m else "raw")


def _qemu_img(args: list[str], progress=None) -> None:
    cmd = ["qemu-img"] + args
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    buf = ""
    while True:
        ch = proc.stdout.read(1)
        if not ch:
            break
        if ch in "\r\n":
            line = buf.strip()
            buf = ""
            if line and progress:
                progress(line)
        else:
            buf += ch
    if buf.strip() and progress:
        progress(buf.strip())
    rc = proc.wait()
    if rc != 0:
        raise CloneError(f"qemu-img 失败 ({rc})")


def clone(
    src: str,
    dst: str,
    *,
    overlay: bool = False,
    start: bool = False,
    progress=None,
) -> dict:
    def log(msg: str) -> None:
        if progress:
            progress(msg)

    if not identity.valid_name(dst):
        raise CloneError("新名字必须字母开头，只含字母数字_-，最长 64")
    if src == dst:
        raise CloneError("源和目标不能同名")
    if not virt.exists(src):
        raise CloneError(f"源 VM '{src}' 不存在")
    if virt.exists(dst):
        raise CloneError(f"目标 VM '{dst}' 已存在")
    if virt.is_running(src):
        raise CloneError(f"源 VM '{src}' 在跑，先关机再克隆")

    xml = virt.domain_xml(src, migratable=True)
    src_disk, src_fmt = _disk_info(xml)
    src_path = Path(src_disk)
    if not src_path.is_file():
        raise CloneError(f"源磁盘不存在: {src_path}")

    images = _images()
    images.mkdir(parents=True, exist_ok=True)
    if overlay:
        dst_path = images / f"{dst}.qcow2"
        dst_fmt = "qcow2"
    else:
        dst_path = images / f"{dst}.{src_fmt}"
        dst_fmt = src_fmt
    if dst_path.exists():
        raise CloneError(f"目标磁盘已存在: {dst_path}")

    nvram_path = _nvram_dir() / f"{dst}_VARS.qcow2"
    if nvram_path.exists():
        log(f"删除旧 NVRAM {nvram_path}")
        nvram_path.unlink()

    ident = identity.new_identity(xml)
    new_xml = identity.rewrite_domain(
        xml,
        name=dst,
        disk_path=str(dst_path),
        nvram_path=str(nvram_path),
        disk_format=dst_fmt,
        ident=ident,
    )

    bak = config.state_dir() / "xml"
    bak.mkdir(parents=True, exist_ok=True)
    (bak / f"{dst}.xml").write_text(new_xml, encoding="utf-8")

    try:
        if overlay:
            log(f"qcow2 overlay ← {src_path}")
            _qemu_img(
                ["create", "-f", "qcow2", "-b", str(src_path), "-F", src_fmt, str(dst_path)],
                progress=progress,
            )
        else:
            log(f"拷贝磁盘 {src_path} → {dst_path} ({src_fmt}, 稀疏)")
            _qemu_img(
                ["convert", "-p", "-f", src_fmt, "-O", dst_fmt, "-S", "4k", str(src_path), str(dst_path)],
                progress=progress,
            )
        _chown_libvirt(dst_path)
        log("define 新域")
        virt.define_xml(new_xml)
    except Exception:
        if dst_path.exists():
            dst_path.unlink()
        raise

    if start:
        log(f"启动 {dst}")
        virt.start(dst)

    result = {
        "src": src,
        "dst": dst,
        "disk": str(dst_path),
        "format": dst_fmt,
        "overlay": overlay,
        "nvram": str(nvram_path),
        "identity": ident,
        "started": start,
    }
    log(
        f"完成 {dst}  uuid={ident['uuid']} mac={ident['mac']} disk_sn={ident['disk_sn']}"
    )
    log("MAC 变了以后 Windows 可能把网络打成公用，RDP 会被挡。VNC 进去执行:")
    log("  Set-NetConnectionProfile -InterfaceAlias (Get-NetConnectionProfile).InterfaceAlias -NetworkCategory Private")
    return result


def rotate(name: str) -> dict:
    if virt.is_running(name):
        raise CloneError(f"VM '{name}' 在跑，先关机再 rotate")
    xml = virt.domain_xml(name, migratable=True)
    ident = identity.new_identity(xml)
    disk, fmt = _disk_info(xml)
    nvram_m = re.search(r"<nvram\b[^>]*>([^<]+)</nvram>", xml)
    nvram = nvram_m.group(1) if nvram_m else str(_nvram_dir() / f"{name}_VARS.qcow2")
    new_xml = identity.rewrite_domain(
        xml,
        name=name,
        disk_path=disk,
        nvram_path=nvram,
        disk_format=fmt,
        ident=ident,
    )
    import libvirt
    with virt.connection() as conn:
        dom = conn.lookupByName(name)
        flags = 0
        if hasattr(libvirt, "VIR_DOMAIN_UNDEFINE_KEEP_NVRAM"):
            flags = libvirt.VIR_DOMAIN_UNDEFINE_KEEP_NVRAM
        dom.undefineFlags(flags)
    virt.define_xml(new_xml)
    return {"name": name, "identity": ident}
