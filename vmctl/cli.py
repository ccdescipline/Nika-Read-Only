from __future__ import annotations

import argparse
import json
import sys

from . import clone, config, rdp, virt
from . import __version__


def _die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def cmd_list(_args) -> int:
    st = rdp.status()
    rows = virt.list_vms(st.get("name") or "")
    if not rows:
        print("(no vms)")
        return 0
    print(f"{'NAME':<20} {'STATE':<10} {'MEM':<5} {'CPU':<4} {'IP':<16} {'MAC':<18} {'NIC':<8} RDP")
    for v in rows:
        mark = "*" if v["rdp"] else ""
        print(
            f"{v['name']:<20} {v['state']:<10} {v['memory']:<5} {v['vcpus']:<4} "
            f"{(v['ip'] or '-'):<16} {(v['mac'] or '-'):<18} {(v['nic'] or '-'):<8} {mark}"
        )
    host = st.get("host") or ""
    tgt = st.get("name") or "(none)"
    extra = ""
    if st.get("stale"):
        extra = f"  [iptables 仍指向 {st.get('dnat_ip')}]"
    print()
    print(f"3389 → {tgt}  {host}{extra}")
    return 0


def cmd_start(args) -> int:
    virt.start(args.name)
    print(f"started {args.name}")
    if rdp.saved_target() == args.name:
        info = rdp.apply(args.name)
        print(f"3389 → {info['name']} {info['ip']}  ({info['host']})")
    return 0


def cmd_stop(args) -> int:
    virt.shutdown(args.name)
    print(f"shutdown {args.name}")
    return 0


def cmd_destroy(args) -> int:
    virt.destroy(args.name)
    print(f"destroyed {args.name}")
    return 0


def cmd_rdp(args) -> int:
    if args.hook:
        info = rdp.hook(args.hook)
        if info:
            print(f"rebind {info['name']} {info['ip']}")
        return 0
    if args.status or not args.name:
        st = rdp.status()
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return 0
    info = rdp.switch(args.name, start_if_down=args.start)
    print(f"3389 → {info['name']} {info['ip']}")
    print(f"LAN: {info['host']}")
    if not info.get("fwi"):
        print("WARN: 没有 LIBVIRT_FWI，default 网可能没起来")
    return 0


def cmd_clone(args) -> int:
    def progress(msg: str) -> None:
        print(msg, flush=True)

    result = clone.clone(
        args.src,
        args.dst,
        overlay=args.overlay,
        start=args.start,
        progress=progress,
    )
    print(json.dumps(result["identity"], ensure_ascii=False, indent=2))
    return 0


def cmd_rotate(args) -> int:
    result = clone.rotate(args.name)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_serve(args) -> int:
    from .server import serve

    cfg = config.load()
    bind = args.bind or cfg["bind"]
    port = args.port or int(cfg["port"])
    try:
        rdp.rebind_saved()
    except Exception as e:
        print(f"WARN: 启动时重绑 3389 失败: {e}", file=sys.stderr)
    serve(bind, port)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vmctl", description="libvirt VM 管理：列表 / 启停 / 3389 切换 / 克隆")
    p.add_argument("--version", action="version", version=f"vmctl {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="列出虚拟机和当前 3389 目标").set_defaults(func=cmd_list)

    s = sub.add_parser("start", help="启动")
    s.add_argument("name")
    s.set_defaults(func=cmd_start)

    s = sub.add_parser("stop", help="ACPI 关机")
    s.add_argument("name")
    s.set_defaults(func=cmd_stop)

    s = sub.add_parser("destroy", help="强制关机")
    s.add_argument("name")
    s.set_defaults(func=cmd_destroy)

    s = sub.add_parser("rdp", help="把宿主机 :3389 指到某台 VM")
    s.add_argument("name", nargs="?")
    s.add_argument("--start", action="store_true", help="没开就先开")
    s.add_argument("--status", action="store_true")
    s.add_argument("--hook", metavar="NAME", help=argparse.SUPPRESS)
    s.set_defaults(func=cmd_rdp)

    s = sub.add_parser("clone", help="关机克隆并 rotate 身份")
    s.add_argument("src")
    s.add_argument("dst")
    s.add_argument("--overlay", action="store_true", help="qcow2 backing，源盘必须保持只读")
    s.add_argument("--start", action="store_true")
    s.set_defaults(func=cmd_clone)

    s = sub.add_parser("rotate", help="只随机化身份（关机）")
    s.add_argument("name")
    s.set_defaults(func=cmd_rotate)

    s = sub.add_parser("serve", help="开 Web UI")
    s.add_argument("--bind", default=None)
    s.add_argument("--port", type=int, default=None)
    s.set_defaults(func=cmd_serve)
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (virt.VirtError, rdp.RdpError, clone.CloneError) as e:
        _die(str(e))
        return 1
    except KeyboardInterrupt:
        return 130
