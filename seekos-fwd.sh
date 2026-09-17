#!/usr/bin/env bash
# 3390 已废弃，宿主机只保留 :3389，由 vmctl 切换目标。
# 用法: sudo seekos-fwd [VM_NAME]   →  vmctl rdp [VM_NAME]
set -eu
VM_NAME="${1:-seekos-ltsc}"
echo "3390 已移除，改走: vmctl rdp $VM_NAME"
exec vmctl rdp "$VM_NAME"
