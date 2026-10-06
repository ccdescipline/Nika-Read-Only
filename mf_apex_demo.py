#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mf_apex_demo.py -- Apex 主模块导出函数读取 demo
  遍历进程 -> r5apex_dx12.exe -> 主模块信息 -> PE导出表解析
  -> export1/export2 指向的VA + 所在段(预期.data) + 数据dump
运行: (root) /home/cc/mfenv/bin/python /home/cc/nika-rebuild/mf_apex_demo.py
"""
import sys, time
from ctypes import Structure, c_uint16, c_uint32, c_ubyte

sys.path.insert(0, "/home/cc/nika-rebuild")
from mf_api import VmApi

PROC_NAME = "r5apex_dx12.exe"
TARGET_EXPORTS = ("export1", "export2")
T0 = time.time()
def t(): return "t+%.1fs" % (time.time() - T0)

class SEC(Structure):
    _fields_ = [("Name", c_ubyte * 8), ("VirtualSize", c_uint32), ("VirtualAddress", c_uint32),
                ("SizeOfRawData", c_uint32), ("PointerToRawData", c_uint32),
                ("_r1", c_uint32), ("_r2", c_uint32), ("_r3", c_uint16 * 2),
                ("Characteristics", c_uint32)]

class EXPDIR(Structure):
    _fields_ = [("Characteristics", c_uint32), ("TimeDateStamp", c_uint32),
                ("MajorVersion", c_uint16), ("MinorVersion", c_uint16),
                ("NameRva", c_uint32), ("Base", c_uint32),
                ("NumberOfFunctions", c_uint32), ("NumberOfNames", c_uint32),
                ("AddressOfFunctions", c_uint32), ("AddressOfNames", c_uint32),
                ("AddressOfNameOrdinals", c_uint32)]

def secname(s): return bytes(s.Name).decode("ascii", "replace").strip("\x00").strip()

print("[%s] booting VmApi (qemu+win32)..." % t())
vm = VmApi()
print("[%s] connected" % t())

print("\n=== [1] process scan ===")
procs = vm.processes()
print("total %d processes" % len(procs))
hits = [(pid, n) for pid, n in procs if "apex" in n.lower() or "r5" in n.lower()]
print("r5/apex matches:", hits if hits else "none")
names = [n.lower() for _, n in procs]
if PROC_NAME.lower() not in names:
    print("\n!! %s NOT running. Start the game then re-run." % PROC_NAME)
    sys.exit(2)

p = vm.process(PROC_NAME)
info = p.info()
print("\n=== [2] target process ===")
print("pid=%d name=%s" % (info.pid, info.name))
print("dtb1=%#x dtb2=%#x" % (info.dtb1, info.dtb2))
if info.command_line: print("cmdline: %s" % info.command_line[:160])
if info.path: print("path: %s" % info.path)

print("\n=== [3] main module ===")
mods = vm.modules(p)
main = None
for m in mods:
    if m[0].lower() == PROC_NAME.lower():
        main = m; break
if main is None:
    main = mods[0]
name, base, size = main
print("module : %s" % name)
print("base   : %#x" % base)
print("size   : %#x (%.1f MiB)" % (size, size / 1048576.0))
assert vm.read(p, base, 2) == b"MZ", "not MZ"

lfanew = vm.read_u32(p, base + 0x3c)
nsec = p.read(base + lfanew + 6, c_uint16)
sizeopt = p.read(base + lfanew + 20, c_uint16)
secs = p.read(base + lfanew + 24 + sizeopt, SEC * nsec)
print("\nsections (%d):" % nsec)
for s in secs:
    flag = "".join(c for c, b in (("R", 0x40000000), ("W", 0x80000000), ("X", 0x20000000)) if s.Characteristics & b)
    print("  %-8s va=%#-10x vsize=%#-10x %s" % (secname(s), s.VirtualAddress, s.VirtualSize, flag))

print("\n=== [4] export directory ===")
ed_rva = vm.read_u32(p, base + lfanew + 24 + 112)
ed_size = vm.read_u32(p, base + lfanew + 24 + 116)
print("export dir rva=%#x size=%#x" % (ed_rva, ed_size))
if not ed_rva:
    print("no exports"); sys.exit(0)
def read_u32_at(addr):
    return int.from_bytes(vm.read(p, addr, 4), "little")

# raw-bytes parse + zero-page retry (demand-zero pages can read back all-zero on first touch)
for attempt in range(5):
    raw = vm.read(p, base + ed_rva, 40)
    nn = int.from_bytes(raw[24:28], "little")
    nf = int.from_bytes(raw[20:24], "little")
    if nn or nf:
        break
    print("  (export page read back zeros, retry %d/5 after 1s...)" % (attempt + 1))
    time.sleep(1)
u32 = lambda off: int.from_bytes(raw[off:off + 4], "little")
u16 = lambda off: int.from_bytes(raw[off:off + 2], "little")
NameRva, OrdBase = u32(12), u32(16)
NFunc, NNames = u32(20), u32(24)
FuncsRva, NamesRva, OrdRva = u32(28), u32(32), u32(36)
dllname = vm.read_cstr(p, base + NameRva, 64)
print("dll name=%r  functions=%d names=%d base=%d" % (dllname, NFunc, NNames, OrdBase))
print("funcsRva=%#x namesRva=%#x ordRva=%#x" % (FuncsRva, NamesRva, OrdRva))

names_raw = vm.read(p, base + NamesRva, NNames * 4)
exports = {}
allnames = []
for i in range(NNames):
    nrva = int.from_bytes(names_raw[i * 4:i * 4 + 4], "little")
    nm = vm.read_cstr(p, base + nrva, 64)
    allnames.append(nm)
    if nm.lower() in TARGET_EXPORTS:
        exports[nm.lower()] = i
print("export names (%d): %s%s" % (len(allnames), ", ".join(allnames[:40]), " ..." if len(allnames) > 40 else ""))

print("\n=== [5] target exports -> VA / section / data ===")
found_any = False
va_of = {}
for want in TARGET_EXPORTS:
    if want not in exports:
        print("%-8s : NOT FOUND in export table" % want); continue
    found_any = True
    i = exports[want]
    ordn = int.from_bytes(vm.read(p, base + OrdRva + i * 2, 2), "little")
    frva = read_u32_at(base + FuncsRva + ordn * 4)
    va = base + frva
    va_of[want] = va
    hit = None
    for s in secs:
        if s.VirtualAddress <= frva < s.VirtualAddress + max(s.VirtualSize, s.SizeOfRawData):
            hit = s; break
    loc = ("%s+%#x" % (secname(hit), frva - hit.VirtualAddress)) if hit else "outside sections?!"
    data = vm.read(p, va, 32)
    print("%-8s : ordinal=%d rva=%#x va=%#x  -> section %s" % (want, ordn + OrdBase, frva, va, loc))
    print("           data[0:32] = %s" % data.hex())


print()
print("=== [6] binary @export1, size @export2 ===")
import base64
if "export1" in va_of and "export2" in va_of:
    for attempt in range(5):
        sz_raw = vm.read(p, va_of["export2"], 8)
        size = int.from_bytes(sz_raw, "little")
        if size:
            break
        print("  (size@export2 still zero, retry %d/5 after 1s...)" % (attempt + 1))
        time.sleep(1)
    print("size (u64 @export2 va=%#x) = %d (0x%x)" % (va_of["export2"], size, size))
    if not (0 < size <= 0x1000000):
        print("  size out of sane range, abort blob read")
    else:
        blob = vm.read(p, va_of["export1"], size)
        print("blob @export1 va=%#x len=%d" % (va_of["export1"], len(blob)))
        print("hex : %s" % blob.hex())
        print("b64 : %s" % base64.b64encode(blob).decode("ascii"))
else:
    print("export1/export2 not both resolved, skip")
print("\n[%s] done (%s found)" % (t(), "targets" if found_any else "NO target exports"))
