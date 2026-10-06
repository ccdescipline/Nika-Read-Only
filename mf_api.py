#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
mf_api.py —— memflow-py 薄封装: 宿主机侧免内核模块读写客机(Windows)内存
依赖: /home/cc/mfenv (pip install memflow) + 仓库三件套 .so 插件
用法: (root) /home/cc/mfenv/bin/python
    from mf_api import VmApi
    vm = VmApi()
    vm.processes()                  # [(pid, name), ...]
    p = vm.process("explorer.exe")  # 按名或pid
    vm.modules(p)                   # [(name, base, size), ...]
    vm.read(p, addr, 16)            # bytes
    vm.write(p, addr, b"\x90"*4)   # 写可写页
    vm.phys_read(0x1000, 16)        # 物理层
"""
from ctypes import c_ubyte, c_uint32, c_uint64

PLUGIN_DIR = "/home/cc/code/Nika-Read-Only"

class VmApi:
    def __init__(self, plugin_dir=PLUGIN_DIR):
        from memflow import Inventory
        inv = Inventory(plugin_dir)
        self.conn = inv.create_connector("qemu", None, None)  # 单VM: 自动匹配qemu进程
        self.os = inv.create_os("win32", self.conn, None)

    # ---- 进程 ----
    def processes(self):
        return [(i.pid, i.name) for i in self.os.process_info_list()]

    def process(self, name_or_pid):
        if isinstance(name_or_pid, int):
            return self.os.process_from_pid(name_or_pid)
        return self.os.process_from_name(name_or_pid)

    # ---- 模块 ----
    @staticmethod
    def modules(proc):
        return [(m.name, m.base, m.size) for m in proc.module_info_list() if m.name]

    @staticmethod
    def pid(proc):
        return proc.info().pid

    @staticmethod
    def module(proc, name):
        return proc.module_by_name(name)

    # ---- 进程地址读写 ----
    @staticmethod
    def read(proc, addr, n):
        return bytes(proc.read(addr, c_ubyte * n))

    @staticmethod
    def read_u32(proc, addr):
        return proc.read(addr, c_uint32)

    @staticmethod
    def read_u64(proc, addr):
        return proc.read(addr, c_uint64)

    @staticmethod
    def read_cstr(proc, addr, max_bytes=260):
        return proc.read_char_string(addr, max_bytes)

    @staticmethod
    def write(proc, addr, data):
        proc.write(addr, c_ubyte * len(data), (c_ubyte * len(data))(*data))

    # ---- 物理地址读写 ----
    def phys_read(self, addr, n):
        return bytes(self.conn.phys_read(addr, c_ubyte * n))

    def phys_write(self, addr, data):
        self.conn.phys_write(addr, c_ubyte * len(data), (c_ubyte * len(data))(*data))

if __name__ == "__main__":
    vm = VmApi()
    procs = vm.processes()
    print("processes:", len(procs))
    p = vm.process("explorer.exe")
    print("explorer pid=%d" % p.info().pid)
    mods = vm.modules(p)
    print("modules:", len(mods), "first:", mods[0])
    base = mods[0][1]
    print("MZ:", vm.read(p, base, 2))
    print("phys 0x1000 head:", vm.phys_read(0x1000, 8).hex())
    print("SMOKE-PASS")
