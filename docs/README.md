# 文档索引

仓库：https://github.com/ccdescipline/Nika-Read-Only  
上游：https://github.com/Ape-xCV/Nika-Read-Only（`git remote` 名 `upstream`）  
宿主机副本：`cclaptop:/home/cc/code/Nika-Read-Only/docs/`

| 文档 | 看什么 |
|---|---|
| [kvm-setup-ubuntu24-from-zero.md](kvm-setup-ubuntu24-from-zero.md) | Ubuntu 24 从零搭 KVM、VFIO、RDP/VNC、踩坑表 |
| [qemu-identity-and-rebuild.md](qemu-identity-and-rebuild.md) | XML 身份 vs QEMU 重编、incr / `--new-ids`、net-rotate |
| [vmctl.md](vmctl.md) | **vmctl**：列表 / 启停 / 克隆+rotate / 宿主机 `:3389` 切换 |
| [nested-virtualization-status.md](nested-virtualization-status.md) | **2026-10-05 收尾**：seekos-ltsc 的 nested VMX/EPT、Hyper-V 参数、回滚包和 Windows LTSC 功能限制 |
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
| 2026-10-07 | **宿主机免内核模块读写客机内存（memflow-py）**：pip wheel + 仓库 `.so` 插件即得 Python API（进程/模块/读写/物理层，QMP 交叉校验）；`mf_api.py` / `mf_api_demo.py` / `mf_apex_demo.py` 三件套；Apex `export1`/`export2`（`.data` 二进制+长度）实测 | [kvm-setup §10.3](kvm-setup-ubuntu24-from-zero.md#103-2026-10-07-宿主机免内核模块读写客机内存memflow-py-python-api实战记录) |
| 2026-10-06 | **`seekos-gpu`（SeekOS 26.8）新 VM + 1070 直通二次部署**：VBIOS 预防性 dump（debugfs shadow 法，sysfs 法失效）；回滚脚本 `return-gpu-seekos-gpu.sh`；删 9/11 备份盘 | [kvm-setup §10.2](kvm-setup-ubuntu24-from-zero.md#102-2026-10-06-第二次直通seekos-gpuseekos-268-实战记录) |
| 2026-09-24 | vmctl 新增客人自助随机化 API `/api/self`、`/api/self/rotate`；客人脚本 `guest-rotate*.ps1`；补全 HTTP API 文档；seekos-ltsc 实测通过 | [vmctl §7](vmctl.md#7-http-api) / [§8](vmctl.md#8-客人自助随机化) |
| 2026-10-05 | seekos-ltsc 完成可回滚的 nested VMX/EPT 实验配置；Windows LTSC 缺少 Hyper-V/VirtualMachinePlatform 功能包 | [nested-virtualization-status.md](nested-virtualization-status.md) |
| 2026-09-23 | 内核 `#3` / `6.19.14-3`：9/22 补丁 + bootmgfw 三处修正 | [kvm-setup §5.2](kvm-setup-ubuntu24-from-zero.md#52-2026-09-23-上-922-补丁并修好-bootmgfw) |
| 2026-09-17 | vmctl 上线（3389 切换 / 克隆 / rotate），`:3390` 拆除；官方 intel619 试更回滚 | [vmctl.md](vmctl.md) / [kvm-setup §5.1](kvm-setup-ubuntu24-from-zero.md#51-2026-09-17-试更官方-intel619mypatch已回滚) |
