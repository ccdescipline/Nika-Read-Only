# QEMU 身份分层：XML 能随机什么、模拟器要重编什么

> 2026-09-11 对照仓库最新脚本 + 宿主机 `cclaptop:/home/cc/code/Nika-Read-Only`。
> 当日实战：`qemupatch-incr.sh`、`--new-ids`、配套 `ovmfpatch.sh`、seekos-ltsc AHCI XML。
> 再刷新：2026-09-14（`net-rotate` 加网关 DNS 名；DUID 说明；§9 现网快照）。
> 再刷新：2026-09-17（日常 RDP 只走宿主机 `:3389`，`vmctl` 切换；`:3390` 已拆。见 [`vmctl.md`](vmctl.md)。总索引 [`README.md`](README.md)）。
> 从零搭建、直通仍看 [`kvm-setup-ubuntu24-from-zero.md`](kvm-setup-ubuntu24-from-zero.md)。克隆 / 3389：[`vmctl.md`](vmctl.md)。
> 本文只回答：改 XML 和改 QEMU 不是一回事，以及怎样少花一个小时重编。

---

## 1. 两层身份

| 层 | 改哪里 | 何时生效 | 每台 VM 能否不同 |
|---|---|---|---|
| 域身份 | libvirt XML / `vm-rotate` | 关机改 XML，开机即变 | 能 |
| 模拟器本体 | `qemupatch.sh` 编进 `/usr/local/bin/qemu-system-x86_64` | 必须重编（或增量编） | 不能。所有用这份 QEMU 的 VM 共享 |

XML **覆盖不了** QEMU 源码里写死的字符串和 PCI ID。客人读设备名 / ACPI OEM / fw_cfg HID 时，看到的是二进制里的值。

---

## 2. XML 层（不用重编）

仓库 `vm-rotate-identity.v2.sh`（宿主机上常装成 `/usr/local/bin/vm-rotate`）：

```bash
sudo virsh shutdown win10-nika
sudo ./vm-rotate-identity.v2.sh win10-nika
sudo virsh start win10-nika
vmctl rdp win10-nika --start
```

只改：UUID、NIC MAC、磁盘 `<serial>`、SMBIOS type 1/2/3/17 序列号。

不改：产品名、CPU 型号、NVRAM、模拟器里的 QEMU 指纹。

⚠️ live 身份以 `virsh dumpxml win10-nika` 为准。仓库 `win10-nika.xml` 是模板，`define` 会覆盖现网身份。

---

## 3. 模拟器层（要动 QEMU）

`qemupatch.sh` 做的事：clone QEMU `stable-11.0` → `sed` 改源码 → `configure` + `make` → 装到 `/usr/local/bin/`。

写进二进制、XML 改不掉的典型项：

- `"QEMU HARDDISK"` / `"QEMU DVD-ROM"` / `"QEMU Microsoft Mouse"` 等设备名
- ACPI OEM `"QEMU"`、`"QEMUQEQEMUQEMU"`
- fw_cfg HID `"QEMU0002"`
- 模拟设备 PCI：RedHat `0x1af4`、QEMU `0x1234`
- ICH9 LPC / SMBus / xHCI / HDA 的 device id
- EDID `"QEMU Monitor"`、厂商 `RHT`

脚本开头的 `lpc_8086` / `smbus_8086` / `hdaudio_8086` 等 **不要随机**，必须对宿主机 `lspci -nn`。本机 Cannon Lake-H：`lpc=a30d` / `smbus=a323` / `hdaudio=a348`。

### 3.1 `vars.sh` 和「每次随机」

| 值 | 何时变 |
|---|---|
| 磁盘名、键鼠名、ACPI OEM、EDID、电池 | **每次跑** `qemupatch.sh` / `qemupatch-incr.sh` 都重新随机 |
| `vars.sh` 里的 `device` / `vendor` / `xhci` / `cpu` / `virtio` | 第一次生成后一直用，好跟 OVMF 对齐 |
| 芯片组 ID（`lpc_8086` 等） | 对齐宿主机，不随机 |

换 `vars.sh` 那套 PCI 相关 ID：

```bash
cd /home/cc/code/Nika-Read-Only
rm -f vars.sh
sudo -E ./qemupatch.sh          # 全量，约 1 小时；有 build 后用 incr
sudo -E ./ovmfpatch.sh          # 必须接着编，PCI ID 才能和 QEMU 对齐
```

`ovmfpatch.sh` 依赖已有 `vars.sh`，只编 QEMU 不编 OVMF 会对不上。

OVMF 是开机固件（蓝底启动菜单）。`ovmfpatch.sh` 编 `OVMF_CODE_4M.patched.qcow2`，让固件认 QEMU 里伪装过的 PCI ID（显卡是 `8086:$device`）。它只读 `vars.sh`，不生成 ID。

| | `qemupatch-incr.sh` | `ovmfpatch.sh` |
|---|---|---|
| 改谁 | QEMU 二进制 | UEFI 固件 |
| 产物 | `/usr/local/bin/qemu-system-x86_64` | `/usr/share/edk2/ovmf/OVMF_*.patched.qcow2` |
| 耗时（本机已有 build） | 约 5–20 分钟 | 约 10–20 分钟；第一次 clone EDK2 再加 10–20 分钟 |

没有「像改 XML 那样开机随机模拟器」的开关。那些值编进二进制了。要每 VM / 每开机不同，只能改 QEMU 让启动时读配置，而不是 `sed` 写死。

⚠️ 7 月留下的 `vars.sh` **没有 `cpu=`**。新 `qemupatch.sh` 会把空 `cpu` 写进 `ICH9_CPU_HOTPLUG_IO_BASE`。incr / `--new-ids` 前先保证 `vars.sh` 有合法 `cpu`（例如 `16896`），或接受 `--new-ids` 重新生成一整份。

---

## 4. 全量 vs 增量编译

`qemupatch.sh` 每次 `cp -fr qemubackup/. qemu`（没有 `-p`），源文件时间戳全新，Ninja 当全部变了，再跑一遍 `./configure`。所以即使用过的 `qemu/build` 也接近整编，大约 **1 小时**。

内核补丁增量（`intel619.mypatch`）不是这个脚本，见 [`kernelpatch-incr.sh`](../kernelpatch-incr.sh) / [`kvm-setup §5`](kvm-setup-ubuntu24-from-zero.md#5-编译定制内核l3kvm-层反检测readme-73)。

不要改 `qemupatch.sh`。QEMU 增量用仓库 `qemupatch-incr.sh`：

- 只从 `qemubackup` 或 `qemu11backup` 还原**即将被 sed 的文件**
- 保留 `qemu/build`，跳过 clone / 整树拷贝 / `configure`
- 再 `make -j$(nproc)`（改过的 `.o` + 链接，大约几分钟）

前提：已经用 `qemupatch.sh` 全量编过一次，目录里有 `qemu/build` 和干净源码树。

```bash
cd /home/cc/code/Nika-Read-Only
sudo -E ./qemupatch-incr.sh -y              # 重随机设备名等，PCI ID 沿用 vars.sh
sudo -E ./qemupatch-incr.sh --new-ids -y    # 删 vars.sh 换 PCI ID；之后必须 ovmfpatch.sh
```

本机 2026-09-11：`qemu/build` 在，incr 走 `qemu11backup`（没有 `qemubackup`）。`ccache` 空的，incr 不依赖它。

实测：只改字符串时 Ninja 约 682 步；补丁碰到被大量 include 的头文件时会到 ~3127 步，仍比全量 `configure` 短。长编译丢 tmux，别走 MCP：

```bash
tmux new -s qemuincr
sudo -E ./qemupatch-incr.sh -y
# 断线后: tmux attach -t qemuincr
```

---

## 5. 仓库脚本改名（2026-09 拉最新之后）

| 旧（7 月远端） | 新 |
|---|---|
| `qemupatch11.sh` | `qemupatch.sh`（另有 `qemupatch_homo.sh`） |
| `edk2patch.sh` | `ovmfpatch.sh`（另有 `fedk2patch.sh`） |

远端旧文件留着当备份，没删。新增量脚本：`qemupatch-incr.sh`。

---

## 6. 远端仓库同步备忘（cclaptop）

路径：`/home/cc/code/Nika-Read-Only`

2026-09-11 从 Windows 仓库上传过一轮。覆盖前备份：

`/home/cc/code/Nika-Read-Only.bak-20260911`

**不要传 / 不要覆盖：**

- `vars.sh`（和已编的 QEMU/OVMF 绑定）
- `qemu/`、`edk2/`、`linux-tkg/`（编译产物）
- 家目录已有的 SeekOS ISO
- `nika.i64` / `*.sys.i64`（IDA 库）

从 Windows 传 `.sh` 会带 CRLF，Linux 上是 `/usr/bin/env: 'bash\r'`。上传后：

```bash
sed -i 's/\r$//' *.sh *.mypatch *.patch *.conf *.ini *.dsl
```

`qemupatch-incr.sh` 已在远端 chmod +x，并且当时做过 LF 转换。

---

## 7. 2026-09-11 实战坑（incr + OVMF + seekos-ltsc）

### 7.1 新 `qemupatch.sh` 关掉了机器自带 SATA

源码里 `pcms->sata_enabled = false`。旧 `qemupatch11.sh` 没有这行。

libvirt 的 `<controller type='sata' index='0'>` 只是在描述 q35 **自带** ICH9 AHCI，**不会**发 `-device ahci`。新 QEMU 起 VM 报：

`Bus 'ide.0' not found`

XML 要再加一块真的 AHCI，盘绑到 `controller='1'`（`model='ahci'` 在 libvirt 10 上不认，不要写）：

```xml
<controller type="sata" index="0">
  <address type="pci" domain="0x0000" bus="0x00" slot="0x1f" function="0x2"/>
</controller>
<controller type="sata" index="1">
  <address type="pci" domain="0x0000" bus="0x03" slot="0x00" function="0x0"/>
</controller>
```

盘 / 光驱：

```xml
<address type="drive" controller="1" bus="0" target="0" unit="0"/>
```

native 应出现 `-device ahci,id=sata1` 和 `bus=sata1.0`。`seekos-ltsc` 现网已这样改。仓库模板 `seekos-ltsc.xml` 已同步。备份：`/home/cc/nika-rebuild/seekos-ltsc.xml.bak-ahci-20260911`。

### 7.2 只换 QEMU、不换 OVMF = 黑屏

VNC：`Guest has not initialized the display (yet).`  
QEMU CPU ~800%，截图约 1569 字节（空帧），VGA BAR `not mapped`。

原因：补丁 OVMF 按 `vars.sh` 的 `8086:$device` 认显卡；incr 还会改 ACPI/fw_cfg。7 月 OVMF 对不上今天的 QEMU。

系统自带 `/usr/share/OVMF/OVMF_CODE_4M.fd` **也不能救急**：它不认 `8086:2091` 这种伪装 VGA，同样黑屏。

正确顺序：`qemupatch-incr.sh`（或 `--new-ids`）→ `ovmfpatch.sh` → 拷 QEMU 到 `/usr/local/bin` → **删域 NVRAM** 再开机（旧 vars 是旧固件的）。

编 OVMF 时 VM 不要占着 CODE 文件，否则：

`qemu-img: Failed to get "write" lock`

Ubuntu 上 `ovmfpatch.sh` 末尾拷 `?0-edk2-ovmf-4m-qcow2-x64-sb-enrolled.json` 可能失败，固件本身仍能装上，可忽略。

### 7.3 `--new-ids` 实测（13:31–13:35）

增量 QEMU + 重编 OVMF，没有整编 QEMU。seekos 用新二进制起来，锁屏截图约 400KB，VGA `8086:2099` BAR 已映射。

| | 换 ID 前 | `--new-ids` 后 |
|---|---|---|
| device（显卡） | 2091 | 2099 |
| vendor | 2846 | 2775 |
| xhci | 46320 | 46711 |
| cpu | 16896 | 24528 |
| virtio | 51243 | 51251 |
| edk2bridge_* | 1633 / 1901 | 不变（来自脚本开头的芯片组桥） |

回滚：`/usr/local/bin/qemu-system-x86_64.bak-before-newids`，`/usr/share/edk2/ovmf/*.bak-before-newids`，以及 `vars.sh.bak-before-newids-*`。

### 7.4 启动菜单里的光驱名

OVMF 蓝底第一项是伪装光驱（如 `UEFI Lite-On iHAS324-17`），不是「没进 ISO」。选中后有时还要再按一次任意键。那是每次 incr 随机的设备名。

### 7.5 NAT 网关 MAC / 网段 / 主机名

客人 `arp -a` 只能看到 virbr0（NAT），看不到宿主机 WiFi。

9/11 先把网关从 `02:a8:0d:cb:8b:00` 改成 `04:d4:c4:8e:2b:17`，随后 `net-rotate` 换过网段和 MAC。9/12 网卡改成 `rtl8125`。**现网以 §9 为准**（§8 是 9/11 收工快照）。

```bash
sudo net-rotate seekos-ltsc
```

脚本改：网段、virbr0 网关 MAC、网关 DNS 名（跟 OUI 厂商配对）、VM 网卡 MAC。不改 UUID / SMBIOS / NVRAM，**不改宿主机 hostname `cclaptop`**。

| OUI | 厂商 | 客人看到的网关名 |
|---|---|---|
| `04:d4:c4` `2c:56:dc` `38:d5:47` | ASUS | `router.asus.com` / `router` |
| `50:c7:bf` `e4:d3:32` `c0:06:c3` | TP-Link | `tplinkwifi.net` / `tplink` |
| `a0:63:91` | Netgear | `routerlogin.net` / `NETGEAR` |
| `64:cc:2e` | 小米 | `miwifi.com` / `miwifi` |

DHCP domain 固定 `lan`（libvirt `<domain name='lan' localOnly='yes'/>` + `<dns><host>`）。不要用 `02:` / `52:54:00`。避开宿主机 LAN `192.168.4.x` 和 libvirt 默认 `122`。备份 `/home/cc/nika-rebuild/`。

客人核对（把网关 IP 换成当次的 `.1`）：

```cmd
ipconfig /all
arp -a
nslookup 192.168.X.1
ping -a 192.168.X.1
```

对上：DNS Suffix `lan`，`nslookup`/`ping -a` 是厂商名（不是 `cclaptop`），ARP 里网关 MAC 与 virbr0 一致。

#### 7.5.1 两层 MAC，XML 改不了 DUID

| | 改哪里 | `net-rotate` |
|---|---|---|
| 网关 MAC | libvirt `default` 网络 XML 的 virbr0 | 会换 |
| VM NIC MAC | **域 XML** `<mac address='...'>` | 会换 |
| DUID | 客人注册表，不是 XML | **不换** |

DUID 是 Windows 的 DHCPv6 客户端身份证（DUID-LLT）。`ipconfig /all` 里「DHCPv6 客户端 DUID」末 6 字节是**第一次生成时**那张网卡的 MAC，换 XML MAC / 换卡都不变。现网 virbr0 关了 IPv6，DHCPv6 实际用不上，但 Windows 仍会打出来。

本机 9/11 装机留下的：`00-01-00-01-32-35-5F-02-3C-97-0E-EC-5D-B6`（当时 e1000e `3c:97:0e:ec:5d:b6`）。要清只能进客人删 `HKLM\SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters\Dhcpv6DUID`，或关 IPv6。

#### 7.5.2 脚本还没跟上的

- VM NIC 现网是 `rtl8125`，脚本仍用 Intel OUI `3c:97:0e` 生成 MAC。Realtek 卡配 Intel MAC，客人 `ipconfig` 一眼能看出来。
- 客人主机名仍是装机日 `WXSG-20260911BA`。
- `dnsmasq-2.90` 的 CHAOS `version.bind` 还能查到，没藏。

---

## 8. 2026-09-11 收工快照（seekos-ltsc）

incr / `--new-ids` / AHCI / 黑屏原因见第 7 节，这里只留**现网值**和备份，方便下次对照。

### 8.1 现网

| 项 | 值 |
|---|---|
| QEMU | `/usr/local/bin/qemu-system-x86_64` 11.0.2-dirty，mtime **13:37**（与 `qemu/build` md5 一致） |
| OVMF | `OVMF_CODE_4M.patched.qcow2` mtime **13:35** |
| `vars.sh` | device=**2099** vendor=**2775** xhci=**46711** cpu=**24528** virtio=**51251** |
| 客人 VGA | 在用 `PCI\VEN_8086&DEV_2099`；`DEV_2091` 是幽灵设备（`Present=False`） |
| 客人磁盘 | `EMTCE X150 240GB` serial `10QQNE9R9H8O` |
| NAT | `192.168.200.0/24` 网关 `192.168.200.1` MAC **`38:d5:47:41:65:69`** |
| VM NIC | `3c:97:0e:ec:5d:b6` e1000e，DHCP **192.168.200.74** |
| RDP | 当时 `:3390` → 客人 3389（**9/17 起已拆，改 vmctl 切 `:3389`**） |
| VNC | SSH 隧道 `127.0.0.1:5900` |
| 主机名 | 宿主机仍是 `cclaptop`（LLMNR/NetBIOS 可能漏，ARP 里没有） |

客人核对：

```cmd
arp -a
ipconfig /all
Get-WmiObject Win32_VideoController | Select Name, PNPDeviceID
```

### 8.2 备份

| 路径 | 内容 |
|---|---|
| `/usr/local/bin/qemu-system-x86_64.bak-incr-20260911` | 7 月 QEMU |
| `/usr/local/bin/qemu-system-x86_64.bak-before-newids` | `--new-ids` 前 QEMU |
| `/usr/share/edk2/ovmf/*.bak-20260911` | 7 月 OVMF |
| `/usr/share/edk2/ovmf/*.bak-before-newids` | `--new-ids` 前 OVMF |
| `vars.sh.bak-before-newids-*` | 换 ID 前 vars |
| `/home/cc/nika-rebuild/seekos-ltsc.xml.bak-ahci-20260911` | 加 AHCI 前 XML |
| `/home/cc/nika-rebuild/default-net.xml.bak-mac-*` | 改 virbr0 / `net-rotate` 前网络 |
| `/home/cc/nika-rebuild/seekos-ltsc.xml.bak-net-*` | `net-rotate` 前域 XML |
| `/var/lib/libvirt/images/seekos-ltsc.raw.bak-20260911` | 重建空盘前的旧盘 |

`win10-nika` 当日没开机。下次启动会用**同一份**新 QEMU/OVMF（模拟器全局一份）。

---

## 9. 2026-09-14 收工快照（seekos-ltsc）

`net-rotate` 补了网关 DNS 名并实跑一次。QEMU/OVMF/`vars.sh` 没动，仍是 §8 那份。

### 9.1 现网

| 项 | 值 |
|---|---|
| 内存 | 4G / 8 vCPU（9/12 从 8G 改回） |
| 网卡 | `rtl8125` `10ec:8125`，Windows：Realtek PCIe 2.5GbE |
| VM NIC MAC | `3c:97:0e:b1:c7:93`（脚本仍写 Intel OUI，见 §7.5.2） |
| NAT | `192.168.243.0/24` 网关 `192.168.243.1` MAC **`64:cc:2e:83:c3:c1`**（小米） |
| 网关 DNS | `miwifi.com` / `miwifi`，domain `lan` |
| DHCP | **192.168.243.74** |
| RDP | 9/14 曾是 `:3390` → `.74:3389`。**2026-09-17 起 3390 已拆**，改 `vmctl rdp` 切宿主机 `:3389` |
| VNC | SSH 隧道 `127.0.0.1:5900` |
| 宿主机名 | 仍是 `cclaptop`（NAT 下客人 DNS 已是 `miwifi.com`，不是它） |
| 客人主机名 | `WXSG-20260911BA`（装机日，没转） |
| DUID | `00-01-00-01-32-35-5F-02-3C-97-0E-EC-5D-B6`（9/11 e1000e MAC，XML 改不了） |

9/14 客人实测：`ipconfig` DNS Suffix `lan`；`nslookup` / `ping -a 192.168.243.1` → `miwifi.com`；ARP 网关 `64-cc-2e-83-c3-c1`。没有 `cclaptop`。

### 9.2 备份

| 路径 | 内容 |
|---|---|
| `/home/cc/nika-rebuild/default-net.xml.bak-mac-20260914-083223` | 转网前 virbr0（当时 `192.168.200.0/24` / `38:d5:47:41:65:69`） |
| `/home/cc/nika-rebuild/seekos-ltsc.xml.bak-net-20260914-083223` | 转网前域 XML（当时 NIC MAC `00:e0:4c:96:ec:21`） |

下次换网：`sudo net-rotate seekos-ltsc`。下次换 PCI ID：`qemupatch-incr.sh --new-ids -y` → `ovmfpatch.sh` → 拷二进制 → 删 NVRAM。
