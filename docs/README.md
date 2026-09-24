# 文档索引

仓库：https://github.com/ccdescipline/Nika-Read-Only  
上游：https://github.com/Ape-xCV/Nika-Read-Only（`git remote` 名 `upstream`）  
宿主机副本：`cclaptop:/home/cc/code/Nika-Read-Only/docs/`

| 文档 | 看什么 |
|---|---|
| [kvm-setup-ubuntu24-from-zero.md](kvm-setup-ubuntu24-from-zero.md) | Ubuntu 24 从零搭 KVM、VFIO、RDP/VNC、踩坑表 |
| [qemu-identity-and-rebuild.md](qemu-identity-and-rebuild.md) | XML 身份 vs QEMU 重编、incr / `--new-ids`、net-rotate |
| [vmctl.md](vmctl.md) | **vmctl**：列表 / 启停 / 克隆+rotate / 宿主机 `:3389` 切换 |
| [vmctl §7 HTTP API](vmctl.md#7-http-api) | 8787 全部接口：GET / POST、body、返回、后台任务 |
| [vmctl §8 客人自助随机化](vmctl.md#8-客人自助随机化) | **9/24 新增**：客人 `POST /api/self/rotate` → 按来源 IP 认 VM → 强制关机 → 随机化 → 开机；客人脚本、实测记录 |
| [kvm-setup §5](kvm-setup-ubuntu24-from-zero.md#5-编译定制内核l3kvm-层反检测readme-73) | 内核全量 / 增量 incr |
| [kvm-setup §5.1](kvm-setup-ubuntu24-from-zero.md#51-2026-09-17-试更官方-intel619mypatch已回滚) | 9/17 intel619 试更失败（卡 `bootmgfw.efi`，不要重装客人） |
| [kvm-setup §5.2](kvm-setup-ubuntu24-from-zero.md#52-2026-09-23-上-922-补丁并修好-bootmgfw) | **9/23 现网 `#3` / `6.19.14-3`**：9/22 补丁 + bootmgfw 三处修正 |
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
# 内核：现网 Sep 23 #3 / 6.19.14-3。bootmgfw 已修，不要重装 Windows
#   docs/kvm-setup-ubuntu24-from-zero.md §5.2
# 客人里一键随机化本机（Windows PowerShell）
#   vmctl/contrib/guest-rotate-test.ps1 [-Rotate]   见 docs/vmctl.md §8
```

## 更新记录

| 日期 | 改了什么 | 看哪 |
|---|---|---|
| 2026-09-24 | vmctl 新增客人自助随机化 API `/api/self`、`/api/self/rotate`；客人脚本 `guest-rotate*.ps1`；补全 HTTP API 文档；seekos-ltsc 实测通过 | [vmctl §7](vmctl.md#7-http-api) / [§8](vmctl.md#8-客人自助随机化) |
| 2026-09-23 | 内核 `#3` / `6.19.14-3`：9/22 补丁 + bootmgfw 三处修正 | [kvm-setup §5.2](kvm-setup-ubuntu24-from-zero.md#52-2026-09-23-上-922-补丁并修好-bootmgfw) |
| 2026-09-17 | vmctl 上线（3389 切换 / 克隆 / rotate），`:3390` 拆除；官方 intel619 试更回滚 | [vmctl.md](vmctl.md) / [kvm-setup §5.1](kvm-setup-ubuntu24-from-zero.md#51-2026-09-17-试更官方-intel619mypatch已回滚) |
