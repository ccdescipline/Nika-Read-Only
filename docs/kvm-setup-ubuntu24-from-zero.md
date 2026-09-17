# Ubuntu 24 从零搭建 KVM 反检测虚拟机 + GTX 1070 Mobile 直通（实战踩坑版）

> 初稿：2026-07-13 ~ 07-26 实际部署。刷新：2026-08-25（对照历史会话 + 当前实机）。
> 再刷新：2026-09-11（脚本改名 `qemupatch.sh` / `ovmfpatch.sh`；当日 incr / `--new-ids` / AHCI XML 见旁文档）。
> 再刷新：2026-09-14（`net-rotate` 网关 DNS 名；seekos 现网 `192.168.243.0/24` / `miwifi.com`）。
> 再刷新：2026-09-17（日常 RDP 改走 `vmctl` 切宿主机 `:3389`；`:3390` 已拆。见 [`vmctl.md`](vmctl.md)。总索引 [`README.md`](README.md)）。
> 目标：Nika Read Only（Ape-xCV）反检测栈，跑 Windows 10 22H2 + 单卡 GPU 直通。
> 宿主机：ASUS ROG 笔记本（i7-8750H / GTX 1070 Mobile / 32G / **无 iGPU** / 仅 WiFi `wlo1`）。
> 这份文档是仓库里**从零搭建 + 显卡直通**总结，坑都是本机踩过的。
> XML vs 模拟器身份、增量重编：[`qemu-identity-and-rebuild.md`](qemu-identity-and-rebuild.md)。
> VM 列表 / 克隆 / 3389 切换：[`vmctl.md`](vmctl.md)。
>
> **标注约定**：
> - `[README]` = 官方 README 原有步骤
> - `[适配]` = README 是 Fedora，这是 Ubuntu 24 的替代做法
> - `[补充]` = README 没有、实战中自己加的
> - `[跳过]` = README 有、本机故意没做（原因写清楚，别事后补坑）
> - 每个 ⚠️ 都是实际踩过的坑，附带症状和修法

---

## 0. 整套架构（先建立心智模型）

```
 Windows 工作机                     宿主机 cclaptop (Ubuntu 24, 无桌面)
 +------------------+               +----------------------------------+
 | SSH 隧道 :5900   |--ssh:22------>| libvirt / 补丁 QEMU 11.0.2       |
 | RDP 客户端 :3389 |--DNAT-------->| virbr0  192.168.76.0/24          |
 | 浏览器 :9090     |--Cockpit----->| vfio-pci 绑死 GTX 1070 Mobile    |
 +------------------+               | 物理屏幕: 直通后基本没画面        |
                                    +----------------+-----------------+
                                                     | hostdev 01:00.0/.1
                                                     v
                                    Windows 10 22H2  win10-nika
                                    独显输出 + e1000e + 模拟 VGA(备用)
```

**访问分工（直通之后这条铁律）**：

| 目的 | 走哪条路 | 不要走哪条 |
|---|---|---|
| 管宿主机 | SSH `cc@192.168.4.158:22` 或 Cockpit `:9090` | 别指望笔记本屏幕（卡已经给 VM 了） |
| 看 OVMF / 安装 / 黑屏抢救 | **SSH 隧道转 VNC** `127.0.0.1:5900` | 不要把 VNC 改成 `0.0.0.0`（没密码） |
| 用 Windows 桌面 / 打游戏 | **RDP 3389**（`vmctl rdp <名字>`） | GPU 驱动装完后 VNC 经常只剩黑屏或卡 logo |
| 改 XML / 启停 VM | `virsh -c qemu:///system ...` 或 Cockpit | 裸 `virsh list` 是 session 连接，永远是空的 |

---

## 0.1 当前实机快照（2026-08-25 核对；网络/QEMU 于 2026-09-11 更新）

| 项 | 值 |
|---|---|
| 宿主机 | `cclaptop` / Ubuntu 24 / `6.19.14-tkg-eevdf` / LAN `192.168.4.158`（WiFi 会漂，曾经是 `.159`） |
| QEMU | `/usr/local/bin/qemu-system-x86_64` **11.0.2 (v11.0.2-dirty)**，进程用户 `libvirt-qemu` |
| OVMF | `/usr/share/edk2/ovmf/OVMF_CODE_4M.patched.qcow2` + `OVMF_VARS_4M.patched.qcow2` |
| libvirt | 10.0.0，URI 必须 `qemu:///system` |
| GPU | `01:00.0 10de:1be1` + `01:00.1 10de:10f0`，**真实 SubID `1043:17ee`**，驱动 `vfio-pci` |
| IOMMU group 1 | `00:01.0` PCIe x16 桥 + GPU + HDMI 音频（没开 ACS，直通照样成） |
| 伪装 | SMBIOS 写成 MSI GE63 Raider 8RF / MS-16P5（和 i7-8750H + 1070 自洽） |
| 域 | `win10-nika`，8 GiB / 4c8t / q35-11.0 / 盘 `/var/lib/libvirt/images/win10-disk.raw` |
| 网 | `default` = **`192.168.243.0/24`**（曾 `200` / `76`），桥 MAC **`64:cc:2e:83:c3:c1`**（小米 / `miwifi.com` / domain `lan`）。seekos NIC `rtl8125`，MAC 现 `3c:97:0e:b1:c7:93`。会随 `net-rotate` 变 |
| 脚本 | **`vmctl`**（列表/启停/克隆/3389）、`/usr/local/bin/vm-rotate`、`/usr/local/bin/net-rotate`。旧 `vm-fwd` / `seekos-fwd` 不要再当日常用 |
| Cockpit | `*:9090` active |
| 内核 cmdline | `mitigations=off vfio-pci.ids=10de:1be1,10de:10f0 intel_iommu=on iommu=pt` |
| kvm.conf | `nested=0`、`ignore_msrs=0`（当前 `N` / `N`） |

⚠️ **仓库根目录的 `win10-nika.xml` 是早期模板，不是正在跑的身份。** live 的 UUID / MAC / 磁盘序列 / SMBIOS 序列号都被 `vm-rotate` 改过。救域请 `virsh dumpxml win10-nika`，不要拿仓库 XML 直接 `define` 把现网身份覆盖掉。

本次核对到的 live 身份（仅供对照，下次 rotate 就作废）：

- UUID `9bce2312-f516-4e91-92fb-7ea64bbf800e`
- MAC `3c:97:0e:c5:b7:42`
- VM IP `192.168.76.207`
- VNC 实际监听 `127.0.0.1:5900`（XML 里写的是 `port='-1' autoport`）

`seekos-ltsc` 9/14 快照见 [`qemu-identity-and-rebuild.md`](qemu-identity-and-rebuild.md) §9。**2026-09-17 起** RDP 只走宿主机 `:3389`（`vmctl` 切换，3390 已拆），现网以 [`vmctl.md`](vmctl.md) §2 为准。

---

## 0.2 README 做了 / 没做 / 跳过了什么

按 README 编号对齐，避免以后「看着官方文档又走一遍」把现网改崩：

| README | 本机 | 说明 |
|---|---|---|
| 1a 双 GPU | `[跳过]` | 这台 BIOS 里 iGPU 被 MUX 关掉，`lspci` 只有 NVIDIA |
| 1b Fedora MATE + dummy X + x11vnc | `[跳过]` | 宿主机是 Ubuntu 24 **无桌面**，管机走 SSH/Cockpit，没装 `dummy.conf` / `headless.sh` |
| 1.1 libvirt + 关 AppArmor | `[适配]` 做了 | 包名换成 apt；网络子网改成 `192.168.76.0/24` |
| 2 virt-manager 点点点建域 | `[适配]` | 无 GUI，XML 直 define。成品就是仓库 `win10-nika.xml` 那一套 |
| 3 / 3.1 / 3.2 VFIO 直通 | `[适配]` **大改** | Ubuntu initramfs 不吃 modprobe.d；softdep 拦不住 nouveau；还要骗 SubID |
| 4 evdev 键鼠直通 | `[跳过]` | 笔记本 + 远程用，桌面走 RDP。XML 里没有 `input-linux` / spice |
| 7 / 7.1 / 7.3 补丁 QEMU / OVMF / tkg | `[README]` 做了 | 芯片组 ID 改成 Cannon Lake-H |
| Looking Glass / Sunshine / EDID / memflow | `[跳过]` | `vm-fwd` 里 Sunshine 端口整段注释，以后要再开 |
| `qemu.conf` `user = "1000"` | `[跳过]` | 当前 QEMU 跑在 `libvirt-qemu`，音频用的 `audiodev none` |

---

## 0.3 全局注意事项（先读这个再动手）

1. **SSH 粘贴会断行**：本指南所有命令都是单行，直接整行粘贴。不要自己加 `\` 换行。
2. **Windows 与 Linux 互传文件后必须去 CRLF**：`sudo sed -i 's/\r$//' 文件名`，否则 bash 报 `/usr/bin/env: 'bash\r': No such file or directory`。
3. **长文件（XML 等）不要粘贴，用 scp 传**：在 Windows 侧写好，`scp 文件 cc@宿主机:/tmp/`。粘贴长行会被 SSH 客户端注入空白（实战中 `slot_length` 被注入成 `slot_leng   th`，QEMU 直接拒启动）。
4. 全程物理可达：改内核/直通有把宿主机搞重启的风险，搞砸了能到现场用 grub 菜单救。

---

## 1. BIOS 与硬件确认 `[README 1b]`

BIOS 里开 VT-x / VT-d / IOMMU。README 还写了关掉 Above 4G Decoding。验证：

```bash
LC_ALL=C lscpu | grep -E "Virtualization|Vendor ID"
grep -E "vmx|svm" /proc/cpuinfo | head -1
lspci -nn -s 01:00
```

- ⚠️ **笔记本看不到 Intel 核显是正常的**：MUX 独显直出机型 BIOS 里 iGPU 被关掉，`lspci | grep -i vga` 只有 NVIDIA。不用折腾，走 **单 GPU 方案**：宿主机 SSH/Cockpit 管理，dGPU 直通给 Windows。
- ⚠️ **Pascal 笔记本卡只有 2 个 PCI 功能**：本机 `01:00.0` VGA + `01:00.1` Audio。README 例子是 RTX 2070 的 4 个功能（再加 USB / UCSI），这边**不要去找 01:00.2 / 01:00.3**，没有。
- 记下来后面处处用：GPU `10de:1be1`、音频 `10de:10f0`、ASUS 子系统 **`1043:17ee`**（十进制 `4163:6126`，直通进 VM 要靠它骗 NVIDIA 安装器）。
- PCH 也记一下（补丁 QEMU 要改）：Cannon Lake-H `lpc=a30d / smbus=a323 / hdaudio=a348`。

## 2. 宿主机基础环境 `[README 1.1 + 适配]`

```bash
sudo apt update && sudo apt install -y qemu-kvm libvirt-daemon-system libvirt-clients bridge-utils virtinst ovmf cockpit cockpit-machines
sudo usermod -aG libvirt,kvm $USER
sudo systemctl stop apparmor && sudo systemctl disable apparmor
sudo systemctl enable --now cockpit.socket
```

新开一个 SSH 会话（usermod 对当前 shell 不生效），然后：

```bash
groups
export LIBVIRT_DEFAULT_URI=qemu:///system
virsh list --all
```

- ⚠️ AppArmor 会拦 QEMU 访问 `/usr/local/bin` 下的自制二进制和 ROM 文件，直接关掉最省事 `[适配]`。
- ⚠️ **裸 `virsh list` 是空的不一定是 VM 没了**：默认连的是 `qemu:///session`。本机域跑在 system 里。写成 `virsh -c qemu:///system list --all`，或 `export LIBVIRT_DEFAULT_URI=qemu:///system`。Cockpit 和 `sudo virsh` 都走 system。`[补充 2026-08-24]`
- ⚠️ 这台机 **没有桌面**，`virt-manager` 会报 `cannot open display`。装了也别开，用 Cockpit `:9090` 或 XML。`[适配]`
- README 的 Fedora dummy X + x11vnc 是给「宿主机还要有个图形会话」用的。这里宿主机本身就 SSH 管，**没装 `dummy.conf` / `headless.sh`** `[跳过]`。

**关嵌套虚拟化、禁止忽略未知 MSR** `[README 3]`：

```bash
echo 'options kvm_intel nested=0' | sudo tee /etc/modprobe.d/kvm.conf && echo 'options kvm ignore_msrs=0' | sudo tee -a /etc/modprobe.d/kvm.conf
```

重启后应看到：

```bash
cat /sys/module/kvm_intel/parameters/nested
cat /sys/module/kvm/parameters/ignore_msrs
```

两个都是 `N`。

**libvirt 默认网络换随机子网**（避开烂大街的 192.168.122.x，反检测细节）`[补充]`：

```bash
sudo virsh net-destroy default
sudo virsh net-edit default
```

把 `<ip address='192.168.122.1' ...>` 段改成自定义段（本指南用 `192.168.76.1/24`，DHCP `192.168.76.2-254`），然后：

```bash
sudo virsh net-start default && sudo virsh net-autostart default
```

- ⚠️ 直接 `net-edit` 保存报 `network 'default' already exists with uuid ...` → 必须先 `net-destroy` 再改。
- ⚠️ SSH 里拼随机 MAC 的多行命令会断行（本机当时 `27: command not found`）。命令必须单行，或用仓库脚本生成。见第 0.3 节。

## 3. 编译补丁 QEMU（L1 反检测）`[README 7]`

改 `qemupatch.sh` 里的芯片组 ID 为你机器的 PCH（本机 Cannon Lake-H：`lpc=a30d / smbus=a323 / hdaudio=a348`，可用 `lspci -nn` 查 ISA bridge / SMBus / Audio 的 8086 设备号）。旧文件名是 `qemupatch11.sh`，2026-09 仓库已换成 `qemupatch.sh`。

```bash
sed -i -e 's/^lpc_8086="[^"]*"/lpc_8086="a30d"/' -e 's/^smbus_8086="[^"]*"/smbus_8086="a323"/' qemupatch.sh
sudo -E ./qemupatch.sh
```

- 第一次全量大约 1 小时。之后用 `qemupatch-incr.sh`（不要改 `qemupatch.sh`）。换 PCI ID：`sudo -E ./qemupatch-incr.sh --new-ids -y`，然后必须 `ovmfpatch.sh`。见 [`qemu-identity-and-rebuild.md`](qemu-identity-and-rebuild.md) 第 7 节。
- ⚠️ 新 `qemupatch.sh` 会关掉 q35 自带 SATA。XML 要显式加 `sata` `index='1'`，盘的 drive address 绑 `controller='1'`，否则 `Bus 'ide.0' not found`。
- ⚠️ 只换 QEMU 不换 OVMF：VNC 黑屏 `Guest has not initialized the display`，CPU 打满。系统自带 OVMF 也不行（认不出 `8086:$device` 显卡）。

- ⚠️ 报 `/usr/bin/env: 'bash\r'` → 文件是 Windows 换行符：`sed -i 's/\r$//' *.sh *.mypatch *.patch *.conf *.ini *.dsl`。
- 验证：`/usr/local/bin/qemu-system-x86_64 --version` 应显示 `11.0.2 (v11.0.2-dirty)`；`ssdt1.aml / ssdt2.aml` 应在 `/usr/local/bin/`。

## 4. 编译补丁 OVMF（L2 反检测）`[README 7.1]`

```bash
sudo -E ./ovmfpatch.sh
```

旧文件名是 `edk2patch.sh`（远端还留着当备份）。`ovmfpatch.sh` 依赖 `qemupatch.sh` 生成的 `vars.sh`，两套 PCI ID 必须一起编。

产物：`/usr/share/edk2/ovmf/OVMF_CODE_4M.patched.qcow2` 和 `OVMF_VARS_4M.patched.qcow2`（带安全启动 + American Megatrends 字符串伪装）。

- ⚠️ **libvirt 10.0 认不出魔改 OVMF 的 var store**，启动报 `unable to find any master var store`。修法和 README 不同 `[适配]`：在域 XML 里**显式写 nvram template**（见第 7 节）。`/etc/libvirt/qemu.conf` 里的 `nvram = [...]` 数组在这个版本上**无效**，别浪费时间。

## 5. 编译定制内核（L3：KVM 层反检测）`[README 7.3]`

```bash
sudo -E ./kernelpatch619.sh
```

交互选项选 `0) Debian`（Ubuntu 按 DEB 系处理）。产物 `.deb` 在 `linux-tkg/DEBS/` 子目录（⚠️ 不在 tkg 根目录）：

```bash
sudo dpkg -i linux-tkg/DEBS/linux-image-6.19.14-tkg-eevdf_6.19.14-1_amd64.deb linux-tkg/DEBS/linux-headers-6.19.14-tkg-eevdf_6.19.14-1_amd64.deb
```

改 grub 内核参数（注意：整条用 `sudo sed -i`，不要用重定向，重定向的 sudo 只管左边）：

```bash
sudo sed -i 's/^GRUB_CMDLINE_LINUX_DEFAULT="\(.*\)"/GRUB_CMDLINE_LINUX_DEFAULT="\1 mitigations=off intel_iommu=on iommu=pt vfio-pci.ids=10de:1be1,10de:10f0"/' /etc/default/grub && sudo update-grub
```

- ⚠️ README 写的是改 `GRUB_CMDLINE_LINUX` + `grub-mkconfig`。Ubuntu 24 用 `GRUB_CMDLINE_LINUX_DEFAULT` + `update-grub` 即可。本机最终 grub 行就是上面这条。
- ⚠️ `sudo dpkg -i \` 换行粘贴会把路径截断，deb 路径写成**一行**。

重启后验证：

```bash
uname -r
cat /proc/cmdline
ls /sys/kernel/iommu_groups/
```

- ⚠️ **tkg 6.19 默认不开 IOMMU**：不加 `intel_iommu=on iommu=pt` 的话 `/sys/kernel/iommu_groups/` 根本不存在，`virsh nodedev-detach` 报 `VFIO device assignment is currently not supported`。
- ⚠️ **拉源码镜像选择**（CN 网络实测）`[补充]`：
  - 首选 NJU：`https://mirror.nju.edu.cn/git/linux-stable.git`（5.5 MB/s 不排队）
  - 清华 tuna 会排队（Position: 345）；USTC 路径结构不同会 404
  - **移动宽带 IPv6 到清华只有 1 KB/s**，强制 IPv4：`/etc/hosts` 加 `101.6.15.130 mirrors.tuna.tsinghua.edu.cn`
  - tkg 首次 `git ls-remote` 10 秒超时可能抖一下，重跑即可

## 6. VFIO GPU 直通准备（宿主机把卡从 nouveau 抢走）`[README 3.1 + 适配]`

这是整套直通的 **A 段：宿主机侧绑定**。B 段（塞进 VM + 装驱动）在第 10 节。顺序不能反：先让 `lspci -k` 看到 `vfio-pci`，再改域 XML。

本机实战时间线（2026-07-14）：先装好 Windows + RDP，再动手直通。单卡机一旦绑定成功，**笔记本面板会黑**，只剩 SSH。所以直通前确认：

1. 已经能 SSH 进宿主机
2. Windows 已经装完、设了密码、开了 RDP（第 8、9 节）
3. 人身在机器旁边（grub 救场）

### 6.1 只靠 cmdline 不够

第 5 节已经把 `vfio-pci.ids=10de:1be1,10de:10f0 intel_iommu=on iommu=pt` 写进 grub。Ubuntu 24 + tkg 上这还不够，当时的现场是：

```
lspci -k -s 01:00
  01:00.0 ... Kernel driver in use: nouveau      ← 失败
  01:00.1 ... Kernel driver in use: snd_hda_intel
cat /proc/cmdline | grep vfio
  vfio-pci.ids=10de:1be1,10de:10f0               ← cmdline 明明写了
lsmod | grep vfio                                ← 空的
```

- ⚠️ **initramfs-tools 不吃 `/etc/modprobe.d/*.conf` 里的 options**：早启动阶段 vfio-pci 加载了但没收到 ids。修法 `[适配]`：往 `/etc/initramfs-tools/modules` 写**行内参数**（该文件支持同行参数）。本机最终文件末尾是：

```
vfio
vfio_iommu_type1
vfio_pci ids=10de:1be1,10de:10f0
```

```bash
printf '%s\n' 'vfio' 'vfio_iommu_type1' 'vfio_pci ids=10de:1be1,10de:10f0' | sudo tee -a /etc/initramfs-tools/modules
```

- ⚠️ **`softdep nouveau pre: vfio-pci` 不可靠**（README 3 就是这么写的）：softdep 在 initramfs 里不一定执行，nouveau 会抢卡。修法：硬黑名单：

```bash
echo "blacklist nouveau" | sudo tee /etc/modprobe.d/blacklist-nouveau.conf && sudo update-initramfs -u -k $(uname -r)
```

- ⚠️ README 写 Debian 用 `update-initramfs -c`。`-c` 是**新建**一份 initramfs，容易跟现有镜像打架。已经在跑的内核用 **`-u -k $(uname -r)`**。

重启后验证（两个功能都必须是 `vfio-pci`，nouveau 不许在 lsmod 里）：

```bash
lspci -k -s 01:00
lsmod | grep -E 'vfio|nouveau|nvidia'
readlink /sys/bus/pci/devices/0000:01:00.0/iommu_group
ls /sys/bus/pci/devices/0000:01:00.0/iommu_group/devices/
```

本机健康输出：

```
01:00.0 ... [10de:1be1]  Kernel driver in use: vfio-pci
01:00.1 ... [10de:10f0]  Kernel driver in use: vfio-pci
vfio_pci / vfio_pci_core / vfio_iommu_type1 / vfio / iommufd
iommu group 1:  0000:00:01.0  0000:01:00.0  0000:01:00.1
```

### 6.2 绑定阶段踩过的坑

- ⚠️ **tkg 6.19 默认不开 IOMMU**（第 5 节已经写）：`/sys/kernel/iommu_groups/` 不存在时，`virsh nodedev-detach` 报 `VFIO device assignment is currently not supported on this system`。先查 cmdline 有没有 `intel_iommu=on iommu=pt`，没有就不要在 sysfs 上硬 bind。
- ⚠️ 手动 `echo vfio-pci > driver_override` + `echo 0000:01:00.0 > drivers_probe` 本机报 **`Invalid argument (-22)`**，`lspci` 甚至变成「Kernel modules: nouveau」连 in-use 都没了。**不要死磕 sysfs**。IOMMU 起来之后 `sudo virsh nodedev-detach pci_0000_01_00_0` 反而能成。XML 里 `managed="yes"` 时 libvirt 启动 VM 会自己 detach。
- ⚠️ GPU 和 PCIe 桥在同一 IOMMU group **不影响直通**（本机 group 1 = `00:01.0` 桥 + GPU + 音频）。tkg 编译时 `_acs_override="false"`，别急着重编内核。真要 ACS 是 group 里混进了不能直通的 SATA/USB。
- ⚠️ 绑成功 = 宿主机失去这张卡。SSH 断了就只能现场 grub。单卡机不要在「还没确认 SSH 自动重连」时 reboot 碰运气。

## 7. 创建 Windows 虚拟机 `[README 2 + 补充]`

准备 ISO 和磁盘：

```bash
sudo mv ~/zh-cn_windows_10_business_editions_version_22h2_xxx.iso /var/lib/libvirt/images/win10-22h2.iso && sudo chown libvirt-qemu:kvm /var/lib/libvirt/images/win10-22h2.iso
sudo qemu-img create -f raw /var/lib/libvirt/images/win10-disk.raw 240G
```

**生成硬件身份** `[补充]`：UUID 随机、MAC 用 Intel OUI `3c:97:0e:xx:xx:xx`、序列号 12 位大写字母+数字（生成函数见仓库 `vm-rotate-identity.v2.sh`）。这是 XML 层；模拟器层见 [`qemu-identity-and-rebuild.md`](qemu-identity-and-rebuild.md)。

**域 XML** 从零搭时用仓库 `win10-nika.xml` 当模板（已含踩坑修正）。**现网救域不要用它覆盖 live 身份**，见第 0.1 节。关键点：

- `<nvram template="...OVMF_VARS_4M.patched.qcow2" templateFormat="qcow2" format="qcow2">...`（第 4 节的坑）
- 伪装成 MSI GE63 Raider 8RF（和 i7-8750H + GTX 1070 真实配置对得上，反检测要自洽）：SMBIOS type 1/2/3/4/9/17 + SSDT 表
- `<feature policy="disable" name="hypervisor"/>` + `<kvm><hidden state="on"/></kvm>` + 全部 hyperv 子项 `state="off"`
- 模拟 VGA 留着当备用（`video vga vram=16384`），直通后 VNC 还能看 BIOS
- ⚠️ **不要加 `<ps2 state="on"/>`**：libvirt 10.0 报 `unexpected feature 'ps2'`，删掉即可（PS/2 默认就是开）
- ⚠️ `<msrs unknown="fault"/>` 和 CPU `host-passthrough` + `vmx` require 是反检测关键，别删
- ⚠️ Intel 主机不要抄 README 例子里的 `svm` / `topoext`（那是 AMD）
- ⚠️ XML 必须 `xmlns:qemu="http://libvirt.org/schemas/domain/qemu/1.0"`，后面 override / smbios / acpitable 才认
- `[跳过]` 没加 evdev 键鼠、没加 Looking Glass、音频是 `<audio type="none"/>`

scp 传到宿主机后：

```bash
sudo virsh define /tmp/win10-nika.xml && sudo virsh start win10-nika
sudo virsh -c qemu:///system domdisplay win10-nika
```

VNC 连接安装：见第 10.1 节（SSH 隧道）。安装阶段还没直通独显，VNC 能看到完整安装界面。

## 8. 安装 Windows `[补充]`

1. **进安装引导后立刻断网**（防自动更新/强制联机账户）：

```bash
sudo virsh domif-setlink win10-nika 3c:97:0e:XX:XX:XX down
```

2. SATA 盘 + e1000e 网卡 Windows 自带驱动，**不需要 virtio ISO**（fedorapeople 在国内 1 KB/s，不装省事）。
3. 装完记得 `domif-setlink ... up` 恢复网络。
4. ⚠️ 宿主机共享目录（hostshare）Windows 默认看不到，别折腾 9p/virtio-fs，**传文件走 RDP 驱动器重定向或 scp**。
5. ⚠️ **空密码账户 RDP 会被拒**：设个密码，或组策略放开"限制空白密码账户只能控制台登录"。
6. Windows 里启用远程桌面。

## 9. 网络与 RDP 转发 `[补充]`

开转发并持久化：

```bash
sudo sysctl -w net.ipv4.ip_forward=1 && echo "net.ipv4.ip_forward=1" | sudo tee /etc/sysctl.d/99-forward.conf
```

从局域网访问 VM 的 RDP 需要**两条规则缺一不可**（IP 以实际为准）：

```bash
sudo iptables -t nat -A PREROUTING -i wlo1 -p tcp --dport 3389 -j DNAT --to-destination 192.168.76.207:3389
sudo iptables -I LIBVIRT_FWI 1 -d 192.168.76.207/32 -p tcp --dport 3389 -j ACCEPT
```

- ⚠️ **LIBVIRT_FWI 默认 REJECT 所有进入 virbr0 的新连接**：DNAT 成功了包也会被拒，必须 `-I 1` 插到 REJECT 前面。
- ⚠️ **DNAT 规则按顺序匹配，命中第一条就生效**：VM 换 IP 后必须先删旧规则再追加，否则包被指向旧 IP 的死规则劫走。症状：`iptables -t nat -L PREROUTING -n | grep 3389` 出现多条指向不同 IP。
- ⚠️ **libvirt 重启 default 网络会重建 LIBVIRT_FWI 链，自定义规则全丢**；宿主机重启也丢。所以有了 `/usr/local/bin/vm-fwd`（自动探测 VM IP → 清全部旧 3389 规则 → 加新规则）。**每次 VM 启动 / 网络重启 / vm-rotate 后跑一遍**：

```bash
sudo vm-fwd
```

## 10. GPU 直通进 VM + 装驱动 `[README 3.2 + 实战坑]`

这是直通 **B 段**。前提：第 6 节 `lspci -k -s 01:00` 已经是 `vfio-pci`。

建议顺序（本机就是这么走的，少踩一次「直通瞬间丢 RDP」）：

1. Windows 已装完、有密码、RDP 能从 LAN 进（第 8、9 节）
2. **关机** VM：`sudo virsh shutdown win10-nika`
3. 把两个 hostdev + `qemu:override` 写进 XML（仓库模板已含，live 用 `virsh edit`）
4. `virsh start`，立刻 `sudo vm-fwd`（宿主机万一重启，规则会丢）
5. RDP 进 Windows 装 **Notebooks** 驱动
6. 装完驱动后 VNC 基本废了，以后桌面只走 RDP

### 10.0 XML 里要有的三块

**1) 两个 hostdev**（只透 GPU + 音频，Pascal 没有 01:00.2/3）：

```xml
<hostdev mode="subsystem" type="pci" managed="yes">
  <driver name="vfio"/>
  <source>
    <address domain="0x0000" bus="0x01" slot="0x00" function="0x0"/>
  </source>
  <rom bar="on"/>
  <alias name="hostdev0"/>
</hostdev>
<hostdev mode="subsystem" type="pci" managed="yes">
  <driver name="vfio"/>
  <source>
    <address domain="0x0000" bus="0x01" slot="0x00" function="0x1"/>
  </source>
  <alias name="hostdev1"/>
</hostdev>
```

`managed="yes"` = 启动时 libvirt 自己 `nodedev-detach`，关机再还回去。本机 live 里 GPU 在 `pci.3`、音频在 `pci.4`，这是 libvirt 自动分配的，不必手写 address。

**2) `qemu:override` 把 SubID 写回去**（域根要有 qemu XMLNS）：

```xml
<qemu:override>
  <qemu:device alias="hostdev0">
    <qemu:frontend>
      <qemu:property name="x-pci-sub-vendor-id" type="unsigned" value="4163"/>
      <qemu:property name="x-pci-sub-device-id" type="unsigned" value="6126"/>
    </qemu:frontend>
  </qemu:device>
  <qemu:device alias="hostdev1">
    <qemu:frontend>
      <qemu:property name="x-pci-sub-vendor-id" type="unsigned" value="4163"/>
      <qemu:property name="x-pci-sub-device-id" type="unsigned" value="6126"/>
    </qemu:frontend>
  </qemu:device>
</qemu:override>
```

live QEMU 命令行能看到对应参数才算挂上：

```
-device ...,host=0000:01:00.0,id=hostdev0,...,x-pci-sub-vendor-id=4163,x-pci-sub-device-id=6126
-device ...,host=0000:01:00.1,id=hostdev1,...,x-pci-sub-vendor-id=4163,x-pci-sub-device-id=6126
```

**3) 模拟 VGA 留着**（VNC 看 BIOS / 抢救用）。不要在直通成功后删掉 `<graphics type="vnc" listen="127.0.0.1"/>`。

### 10.0.1 驱动与 Code 43

- ⚠️ **VFIO 直通会把子系统 ID 清零**：Windows 里看到 `SUBSYS_00000000`，NVIDIA 安装器直接拒装「找不到兼容的图形硬件」。这就是 override 存在的理由。属性必须用**十进制**（`0x1043→4163`，`0x17ee→6126`），两个 hostdev 都要有 **`alias name="hostdev0/1"`** 才能挂上。漏 alias = override 静默不生效。
- ⚠️ **GTX 1070 Mobile ≠ 桌面版**：设备 ID `1BE1`（移动）vs `1B81`（桌面）。驱动必须去 nvidia.cn 选 **"GeForce 10 Series (Notebooks)"**，桌面版驱动 SubID 对了也不认。
- ⚠️ 装完驱动后 `Get-PnpDevice -Class Display` 检查，可能有 `SUBSYS_00000000` 的 **ghost 设备**残留，清理：

```powershell
pnputil /remove-device "PCI\VEN_10DE&DEV_1BE1&SUBSYS_00000000&REV_A1\4&XXXXXXXX&0&0012"
```

- ⚠️ dmesg 里可能出现 `vfio-pci: Invalid PCI ROM header signature: expecting 0xaa55, got 0x365a`。本机 **没有因此 Code 43**（KVM hidden + SubID 伪装够用）。真触发了再 dump 真 VBIOS——必须在 **GPU 没进 VM、host 侧还能碰 ROM  sysfs** 时做：

```bash
sudo bash -c 'echo 1 > /sys/bus/pci/devices/0000:01:00.0/rom; cat /sys/bus/pci/devices/0000:01:00.0/rom > /usr/local/share/vbios-1070m.rom; echo 0 > /sys/bus/pci/devices/0000:01:00.0/rom'
```

然后 XML `<rom bar="on" file="/usr/local/share/vbios-1070m.rom"/>`。卡已经在 VM 里时去 dump 会失败或 dump 到垃圾。
- ⚠️ 直通那一次本机 **host 自己重启过**，RDP 转发全丢。起来先 `sudo vm-fwd`，再谈驱动。
- README 还写了 NVIDIA 控制面板把 shader cache 调到 10 GiB，属于优化不是直通门槛。
- `[跳过]` evdev：笔记本没有外接键鼠直通需求，输入走 RDP。

### 10.1 直通之后怎么连（VNC / RDP / Cockpit）`[补充 2026-08-24]`

核对现状（只读，不要改 XML）：

```bash
export LIBVIRT_DEFAULT_URI=qemu:///system
virsh list --all
virsh dumpxml win10-nika | grep -A2 graphics
ss -lntp | grep 5900
```

本机：

```
graphics type='vnc' port='5900' autoport='yes' listen='127.0.0.1'
LISTEN 127.0.0.1:5900
```

含义：显示号 `:0` → 端口 5900；**只绑回环，没密码**；局域网直接连 `192.168.4.158:5900` 会失败，这是故意的。

**本机 Windows 连 VNC（看 BIOS / 安装 / 抢救）**：开一个保持不关的 SSH 隧道。

```bat
ssh -N -L 5900:127.0.0.1:5900 cc@192.168.4.158
```

然后 VNC 客户端连 `127.0.0.1:5900`，密码空。本机 5900 占用就换：

```bat
ssh -N -L 15900:127.0.0.1:5900 cc@192.168.4.158
```

连 `127.0.0.1:15900`。客户端用 TigerVNC / RealVNC / TightVNC / virt-viewer 都行。

⚠️ **独显驱动装上之后，VNC 经常只能看到 OVMF、Windows logo 或者黑屏。** 模拟 VGA 不再是 Windows 主显示。日常桌面用 RDP：

```
LAN 上任意机器 → 宿主机:3389 → DNAT → 192.168.76.x:3389
sudo vm-fwd
```

Cockpit 管 libvirt：浏览器开 `https://192.168.4.158:9090`（证书自签）。

不要把 VNC 改成 `listen=0.0.0.0`。没密码，等于裸奔进局域网。

`virsh domdisplay` 可能打印 `vnc://127.0.0.1:0`（显示号），对应的 TCP 是 5900，不是 0。

## 11. 一键身份随机化 `[补充]`

`/usr/local/bin/vm-rotate`（源码见仓库 `vm-rotate-identity.v2.sh`）：随机化 UUID / NIC MAC / 磁盘序列 / SMBIOS type 1/2/3/17 序列号，保留 NVRAM。**必须 VM 关机后运行**。这只改 XML，不改 QEMU 二进制里的指纹；模拟器层见 [`qemu-identity-and-rebuild.md`](qemu-identity-and-rebuild.md)。

rotate 后的善后清单（每次必做）：

1. `sudo virsh start win10-nika` → VM 会拿到**新 IP**
2. `sudo vm-fwd` 重建转发
3. ⚠️ **新 MAC = Windows 网络位置重置为"公用"→ 防火墙挡 RDP**。这时 RDP 已经废了，走第 10.1 节 SSH 隧道 VNC 进去执行：

（独显驱动把模拟 VGA 黑掉时，VNC 也可能没桌面，这是单卡直通 + 改 MAC 的组合死锁。能防的只有：rotate 前先在 Windows 里把网络配置文件策略钉死，或现场键盘。本机 7 月那次 VNC 还进得去。）

```powershell
Set-NetConnectionProfile -InterfaceAlias (Get-NetConnectionProfile).InterfaceAlias -NetworkCategory Private
```

4. Windows 可能提示重新激活（硬件大变）

- 注意：**GPU SubID 和 SMBIOS 产品名不轮换**——它们必须和伪装的真实硬件（MSI GE63）保持一致，换了反而露馅。
- ⚠️ 脚本坑：不能用 `tr < /dev/urandom | head -c N` 生成随机串，`pipefail` 下 tr 收 SIGPIPE 静默退出（exit 141 无报错）。用纯 bash 字符选取（仓库脚本已实现）。

## 12. MAC 地址管理：三层模型（2026-07-26 新坑）`[补充]`

改 MAC 前必须理解的三层：

| 层 | 位置 | 作用 |
|---|---|---|
| 1. XML 登记 | `virsh dumpxml` 的 `<mac address=` | 宿主机"户口本" |
| 2. QEMU 递送 | e1000e 硬件 MAC | 正常等于第 1 层 |
| 3. Windows 覆盖 | 注册表 `HKLM\SYSTEM\CurrentControlSet\Control\Class\{4D36E972-E325-11CE-BFC1-08002BE10318}\<编号>\NetworkAddress`（设备管理器→网卡→高级→"网络地址"也写这里） | **设了就盖过第 2 层**，Windows 实际用它发包 |

**错位症状**（本次实测）：`virsh domifaddr --source lease` 返回空（它按 XML MAC 查租约表，而租约登记的是 Windows 覆盖 MAC）→ `vm-fwd` 30 秒超时拿不到 IP → 转发建不起来 → RDP 连不上。**VM 本身上网是正常的**，坏的只是管理层。

**排查三件套**：

```bash
sudo virsh dumpxml win10-nika | grep "mac address"
sudo virsh domifaddr win10-nika --source lease
sudo cat /var/lib/libvirt/dnsmasq/virbr0.status
```

VM 内查覆盖（有输出就是被覆盖了）：

```powershell
Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Control\Class\{4D36E972-E325-11CE-BFC1-08002BE10318}\*" -Name NetworkAddress -ErrorAction SilentlyContinue | Select-Object PSChildName, NetworkAddress
```

**修复（免重启 VM：热拔插网卡）**：新网卡对 Windows 是全新设备实例，注册表覆盖绑旧实例不会带过去：

```bash
sudo virsh domiflist win10-nika
sudo virsh detach-interface win10-nika network --mac 上一步看到的MAC --live
sudo virsh attach-interface win10-nika network default --model e1000e --mac 目标MAC --live --config
```

等 20 秒 DHCP，然后 `vm-fwd` + VM 内设专用网络（第 11 节第 3 条）。`--config` 会同时写进持久 XML，三层一次对齐。

**铁律：MAC 只在一层改**。要么只用 `vm-rotate` 管 XML 层，要么只在 Windows 里改覆盖层，两边都动必然错位。

- ⚠️ Windows 手填 MAC 时**第一个字节必须是偶数**（奇数 = 多播地址，直接断网）；本地管理地址第二十六进制位 ∈ {2,6,A,E}。
- ⚠️ 热拔插/rotate 后旧网卡变 ghost 设备，VM 里出现"以太网 2"，不碍事，想清理用 `pnputil /remove-device`。
- ⚠️ 清理 dnsmasq 尸体租约（VM 关机时）：`sudo virsh net-destroy default && sudo rm -f /var/lib/libvirt/dnsmasq/virbr0.status && sudo virsh net-start default`。

## 13. 其他杂坑

- ⚠️ `virsh detach-disk` **不支持 cdrom**：报 `disk device type 'cdrom' cannot be detached`。用 `sudo virsh change-media win10-nika sdb --eject --config --live`（弹出留驱）或删 XML 整段 redefine。
- ⚠️ `virsh domifaddr --source arp` 报 `wrong nlmsg len` 是 libvirt 在新内核上的已知 bug，用 `--source lease` 即可。
- ⚠️ 宿主机只有 WiFi（wlo1），转发规则都绑 wlo1；换网口要改 `vm-fwd` 里的 `EXT_IF`。
- ⚠️ `ls /var/lib/libvirt/images/` 报 Permission denied 是正常的（目录 `drwx--x--x`），用 `sudo ls`。
- ⚠️ 空密码账户 RDP 会被拒（第 8 节）：设密码，或组策略放开「限制空白密码账户只能控制台登录」。
- ⚠️ 不要拿仓库 `win10-nika.xml` 对正在跑的域 `virsh undefine && define`。那是早期模板，会把 live UUID/MAC/序列号覆盖成旧快照。
- ⚠️ 非交互 SSH / MCP 里 `sudo virsh` 可能卡在要密码。用户已在 `libvirt` 组时改用 `virsh -c qemu:///system ...`。

## 14. 故障速查表

| 症状 | 原因 | 修复 |
|---|---|---|
| `virsh list` 永远空，Cockpit 里却在跑 | 连的是 `qemu:///session` | `export LIBVIRT_DEFAULT_URI=qemu:///system` |
| 局域网连 `宿主机:5900` 失败 | VNC 只绑 `127.0.0.1` | 第 10.1 节 SSH 隧道 |
| VNC 只有黑屏 / 卡 logo | 独显已接走显示 | 正常，桌面走 RDP |
| `domdisplay` 显示 `:0` | 那是 VNC 显示号 | TCP 端口是 5900 |
| `domifaddr` 返回空但 VM 能上网 | XML MAC ≠ Windows 覆盖 MAC | 第 12 节热拔插对齐 |
| `vm-fwd` 30 秒超时 | 同上 | 同上 |
| 加了 DNAT 还是连不上 3389 | 旧 DNAT 规则在前面劫包 / LIBVIRT_FWI REJECT | `vm-fwd`（先清后加） |
| rotate/换卡后 RDP 突然断 | 网络位置变「公用」防火墙挡 | VM 内 `Set-NetConnectionProfile ... Private` |
| 宿主机重启后转发全丢 | iptables 不持久 + libvirt 重建链 | 重跑 `vm-fwd` |
| `unable to find any master var store` | libvirt 认不出魔改 OVMF | XML 显式 nvram template |
| `unexpected feature 'ps2'` | libvirt 10.0 不支持该元素 | XML 删掉该行 |
| NVIDIA 安装器「找不到兼容的图形硬件」 | SubID 被清零 | qemu:override 十进制 SubID，检查 alias |
| NVIDIA 驱动 SubID 对了仍不装 | 用了桌面版驱动 | 下 Notebooks 版 |
| `VFIO device assignment is currently not supported` | tkg 内核没开 IOMMU | cmdline 加 `intel_iommu=on iommu=pt` |
| GPU 仍被 nouveau 占用 | softdep 不可靠 / initramfs 没吃到 ids | blacklist + `/etc/initramfs-tools/modules` 行内 ids + `update-initramfs -u` |
| sysfs `driver_override` 报 `-22` | 没 IOMMU 或绑定路径不对 | 先开 IOMMU，再用 `nodedev-detach` / `managed=yes` |
| 笔记本面板直通后黑屏 | 单卡被 VM 抢走 | 正常，SSH / Cockpit 管宿主机 |
| 脚本静默退出无报错 | pipefail + tr/head SIGPIPE | 纯 bash 生成随机串 |
| QEMU 报 `Invalid parameter 'slot_leng   th'` | SSH 粘贴注入空白 | scp 传文件，别粘贴 |
| `'bash\r': No such file or directory` | Windows 换行符 | `sed -i 's/\r$//'` |
| git clone 卡在 Waiting in queue | tuna 镜像排队 | 换 NJU 镜像 |
| 镜像速度 1 KB/s | 移动 IPv6 劣化 | /etc/hosts 强制 IPv4 |
| virt-manager `cannot open display` | 宿主机无 GUI | 用 Cockpit 或 XML，别装桌面硬开 |

## 15. 日常命令速查

```bash
export LIBVIRT_DEFAULT_URI=qemu:///system              # 当前 shell 先写上
virsh list --all                                       # VM 状态（system）
virsh start win10-nika                                 # 启动（shutdown/reboot/domstate 同理）
virsh domifaddr win10-nika --source lease              # 查 VM IP/MAC
virsh domiflist win10-nika                             # 网卡 / 当前 MAC
virsh dumpxml win10-nika | grep -E 'mac address|uuid|hostdev|nvram'
virsh domdisplay win10-nika                            # VNC 地址（:0 = 5900）
vmctl list                                             # VM 列表 + 当前 3389 目标
vmctl rdp NAME                                         # 把宿主机 :3389 指到该 VM（替代 vm-fwd / seekos-fwd）
sudo vm-rotate                                         # 随机化身份（VM 必须关机；也可用 vmctl rotate）
sudo iptables -t nat -L PREROUTING -n --line-numbers   # 查 DNAT
sudo iptables -L LIBVIRT_FWI -n --line-numbers         # 查入向过滤
lspci -nnk -s 01:00                                    # GPU 是否绑在 vfio-pci
ls /sys/kernel/iommu_groups/                           # IOMMU 是否起来
```

Windows 侧隧道（VNC）：

```bat
ssh -N -L 5900:127.0.0.1:5900 cc@192.168.4.158
```

RDP：`vmctl rdp <名字>`，再连 `192.168.4.158:3389`（不要再记 3390）。Web：`http://192.168.4.158:8787/`。Cockpit：`https://192.168.4.158:9090`。详情 [`vmctl.md`](vmctl.md)。

## 16. 从零再搭一遍的顺序（对照用）

按这个走就不会把「先直通再装系统」搞成笔记本变砖：

1. BIOS：VT-x / VT-d / IOMMU；确认只有独显、记下 `10de:1be1,10de:10f0` / `1043:17ee` / PCH ID
2. Ubuntu 24：libvirt + Cockpit，关 AppArmor，加 `libvirt,kvm` 组，换新 SSH 会话
3. `kvm.conf`：`nested=0` + `ignore_msrs=0`
4. 改 default 网络到 `192.168.76.0/24`（先 destroy 再 edit）
5. CRLF 洗仓库脚本 → `qemupatch.sh`（改 PCH ID；已有 `qemu/build` 时用 `qemupatch-incr.sh`）→ `ovmfpatch.sh` → `kernelpatch619.sh` 选 Debian
6. grub：`mitigations=off intel_iommu=on iommu=pt vfio-pci.ids=...` + `update-grub`
7. **先不要绑卡**：先 define VM、VNC 隧道装 Windows、设密码、开 RDP、`vmctl rdp <名字>` 通
8. 再做第 6 节：initramfs 行内 ids + blacklist nouveau + `update-initramfs -u` + 重启
9. 确认 `lspci -k` 是 vfio-pci 之后，关机 VM，加 hostdev + qemu:override，开机，立刻 `vmctl rdp <名字>`
10. RDP 进 Windows 装 **Notebooks** 驱动，清 ghost 设备
11. 以后桌面只走 RDP；VNC 只救 BIOS；身份变化走 `vm-rotate` / `vmctl rotate`（关机）+ `vmctl rdp` + 网络配置文件改 Private
