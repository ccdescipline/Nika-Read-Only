# 文档索引

仓库：https://github.com/ccdescipline/Nika-Read-Only  
上游：https://github.com/Ape-xCV/Nika-Read-Only（`git remote` 名 `upstream`）  
宿主机副本：`cclaptop:/home/cc/code/Nika-Read-Only/docs/`

| 文档 | 看什么 |
|---|---|
| [kvm-setup-ubuntu24-from-zero.md](kvm-setup-ubuntu24-from-zero.md) | Ubuntu 24 从零搭 KVM、VFIO、RDP/VNC、踩坑表 |
| [qemu-identity-and-rebuild.md](qemu-identity-and-rebuild.md) | XML 身份 vs QEMU 重编、incr / `--new-ids`、net-rotate |
| [vmctl.md](vmctl.md) | **vmctl**：列表 / 启停 / 克隆+rotate / 宿主机 `:3389` 切换 |
| [kvm-setup §5](kvm-setup-ubuntu24-from-zero.md#5-编译定制内核l3kvm-层反检测readme-73) | 内核全量 / 增量 incr |
| [kvm-setup §5.1](kvm-setup-ubuntu24-from-zero.md#51-2026-09-17-试更官方-intel619mypatch已回滚) | **9/17 intel619 试更失败已回滚**（卡 `bootmgfw.efi`，不要重装客人） |
| [backups/win10-nika-live-20260825.xml](backups/win10-nika-live-20260825.xml) | win10-nika 早期 live XML 备份（不是现网） |

日常入口：

```bash
# 管 VM / 切 RDP
vmctl list
# 浏览器
http://192.168.4.158:8787/
# 从零搭建、直通
#   docs/kvm-setup-ubuntu24-from-zero.md
# 换 QEMU 指纹、换网段
#   docs/qemu-identity-and-rebuild.md
# 内核：现网 Jul 13。官方 intel619 9/17 试更已回滚，不要重装 Windows
#   docs/kvm-setup-ubuntu24-from-zero.md §5.1
```
