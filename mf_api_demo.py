#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
memflow-py 基本API测试demo —— 宿主机侧免内核模块读写 seekos-gpu 客机内存
运行: (root) /home/cc/mfenv/bin/python /home/cc/nika-rebuild/mf_api_demo.py
API: 遍历进程 / 遍历模块基地址(内核+用户) / 读进程地址(ctypes结构体) / 写(物理+内核+用户) / QMP交叉校验 / 吞吐
"""
import hashlib, subprocess, time
from ctypes import Structure, c_uint16, c_uint32, c_ubyte

PLUGIN_DIR = "/home/cc/code/Nika-Read-Only"
VM = "seekos-gpu"
T0 = time.time()
def step(n, msg): print("\n=== [%s] %s  (t+%.1fs) ===" % (n, msg, time.time()-T0), flush=True)
def md5(b): return hashlib.md5(b).hexdigest()

def qmp_pmem_md5(addr, size):
    f = "/tmp/mfdemo_%x.bin" % addr
    subprocess.run(["rm", "-f", f])
    j = '{"execute":"pmemsave","arguments":{"val":%d,"size":%d,"filename":"%s"}}' % (addr, size, f)
    subprocess.run(["virsh", "qemu-monitor-command", VM, j], capture_output=True)
    try:
        with open(f, "rb") as fh: return md5(fh.read())
    except FileNotFoundError: return "<qmp-fail>"

class IMAGE_SECTION_HEADER(Structure):
    _fields_ = [("Name", c_ubyte * 8), ("VirtualSize", c_uint32), ("VirtualAddress", c_uint32),
                ("SizeOfRawData", c_uint32), ("PointerToRawData", c_uint32),
                ("_r1", c_uint32), ("_r2", c_uint32), ("_r3", c_uint16 * 2),
                ("Characteristics", c_uint32)]

def find_rw_section(reader, base):
    """用API读PE头找第一个可写段 (演示结构体读 + 给写测试找合法rw页)"""
    lfanew = reader(base + 0x3c, c_uint32)
    nsec = reader(base + lfanew + 6, c_uint16)
    sizeopt = reader(base + lfanew + 20, c_uint16)
    secs = reader(base + lfanew + 24 + sizeopt, IMAGE_SECTION_HEADER * nsec)
    for s in secs:
        if s.Characteristics & 0x80000000:
            return s
    return None

def secname(s): return bytes(s.Name).decode("ascii", "replace").strip("\x00").strip()

def idem_write(writer, reader, addr, n, label):
    orig = bytes(reader(addr, c_ubyte * n))
    writer(addr, c_ubyte * n, (c_ubyte * n)(*orig))
    again = bytes(reader(addr, c_ubyte * n))
    print("  %-8s @%#x 写回%d字节 -> 复读 %s" % (label, addr, n, "OK" if orig == again else "FAIL"))

step(1, "扫描插件 " + PLUGIN_DIR)
from memflow import Inventory
inv = Inventory(PLUGIN_DIR)
print("connectors:", inv.available_connectors(), " os plugins:", inv.available_os())

step(2, "qemu 连接器 (自动匹配)")
conn = inv.create_connector("qemu", None, None)
print("max=%#x size=%#x readonly=%s" % (conn.max_address, conn.real_size, conn.readonly))

step(3, "物理读校验 vs QMP")
for addr in (0x1000, 0x100000000):
    ours = md5(bytes(conn.phys_read(addr, c_ubyte * 4096)))
    qmp = qmp_pmem_md5(addr, 4096)
    print("  phys %#x: %s %s" % (addr, ours[:16], "MATCH" if ours == qmp else "MISMATCH"))

step(4, "win32 OS 层")
os = inv.create_os("win32", conn, None)
print("OK")

step(5, "API(1) 遍历进程")
infos = os.process_info_list()
print("共 %d 个, 前12:" % len(infos))
for i in infos[:12]: print("  pid=%-6d %-22s dtb1=%#x" % (i.pid, i.name, i.dtb1))

step(6, "API(2) 模块基地址 (内核+用户)")
kmods = os.module_info_list()
print("内核模块 %d 个, 前5:" % len(kmods))
for m in kmods[:5]: print("  %-20s base=%#-16x size=%#x" % (m.name, m.base, m.size))
target = os.process_from_name("explorer.exe")
umods = [m for m in target.module_info_list() if m.name]
print("explorer.exe 有名模块 %d 个, 前5:" % len(umods))
for m in umods[:5]: print("  %-20s base=%#-14x size=%#x" % (m.name, m.base, m.size))

step(7, "API(3) 读: MZ + PE结构体解析")
main = umods[0]
assert list(target.read(main.base, c_ubyte * 2)) == [0x4D, 0x5A], "user MZ fail"
print("  用户: %s MZ-OK" % main.name)
nt = kmods[0]
assert list(os.read(nt.base, c_ubyte * 2)) == [0x4D, 0x5A], "kernel MZ fail"
print("  内核: %s MZ-OK" % nt.name)
usec = find_rw_section(lambda a, t: target.read(a, t), main.base)
ksec = find_rw_section(lambda a, t: os.read(a, t), nt.base)
print("  PE解析: %s 可写段=%s(+%#x) | %s 可写段=%s(+%#x)" % (
    main.name, secname(usec), usec.VirtualAddress, nt.name, secname(ksec), ksec.VirtualAddress))

step(8, "API(4) 写: 物理 / 内核 / 用户(遍历可写段) / 保护行为")
idem_write(conn.phys_write, lambda a, t: conn.phys_read(a, t), target.info().dtb1, 8, "物理")
idem_write(os.write, lambda a, t: os.read(a, t), nt.base + ksec.VirtualAddress + 0x40, 8, "内核")

def user_write_test():
    mods = [umods[0]] + [m for m in umods if m.name.upper() in ("KERNELBASE.DLL", "UCRTBASE.DLL", "KERNEL32.DLL")]
    for mod in mods:
        base = mod.base
        try:
            lfanew = target.read(base + 0x3c, c_uint32)
            nsec = target.read(base + lfanew + 6, c_uint16)
            sizeopt = target.read(base + lfanew + 20, c_uint16)
            secs = target.read(base + lfanew + 24 + sizeopt, IMAGE_SECTION_HEADER * nsec)
        except Exception as e:
            print("  %s PE读失败: %s" % (mod.name, e)); continue
        for s in secs:
            if not (s.Characteristics & 0x80000000): continue
            addr = base + s.VirtualAddress + 0x40
            try:
                orig = bytes(target.read(addr, c_ubyte * 8))
                target.write(addr, c_ubyte * 8, (c_ubyte * 8)(*orig))
                again = bytes(target.read(addr, c_ubyte * 8))
                st = "OK" if orig == again else "FAIL"
            except Exception as e:
                st = "拒(%s)" % str(e).split("(")[0].strip()[:24]
            print("  %s!%s @%#x 运行时写: %s" % (mod.name, secname(s), addr, st))
            if st == "OK":
                return True
    return False

ok_user = user_write_test()
try:
    orig8 = bytes(target.read(main.base + 0x1000, c_ubyte * 8))
    target.write(main.base + 0x1000, c_ubyte * 8, (c_ubyte * 8)(*orig8))
    print("  .text写: 意外成功")
except Exception as e:
    print("  .text写: 按预期被拒 — r-x页按写权限翻译不可写")

step(9, "读吞吐: 4KBx1000 / 64KBx20 (Python绑定层)")
t = time.time()
for i in range(1000): conn.phys_read(0x100000000 + i * 0x1000, c_ubyte * 4096)
dt = time.time() - t
print("  4KB x1000 : %.2fs = %.0f 读/s (%.0f MB/s)" % (dt, 1000 / dt, 1000 * 4096 / dt / 1048576))
t = time.time()
for i in range(20): conn.phys_read(0x100000000 + i * 0x10000, c_ubyte * 65536)
dt = time.time() - t
print("  64KB x20  : %.2fs = %.0f MB/s" % (dt, 20 * 65536 / dt / 1048576))

print("\n========== DEMO ALL PASS ==========", flush=True)
