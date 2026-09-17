# vmctl：虚拟机管理（列表 / 启停 / 克隆 / 3389 切换）

> 2026-09-17 初稿。对照仓库 `vmctl/` + 宿主机 `cclaptop`。
> 总索引：[`README.md`](README.md)。从零搭建 / 直通仍看 [`kvm-setup-ubuntu24-from-zero.md`](kvm-setup-ubuntu24-from-zero.md)。身份分层看 [`qemu-identity-and-rebuild.md`](qemu-identity-and-rebuild.md)。
>
> 本文只覆盖 **vmctl** 这一层：不管 QEMU 重编、不管 GPU 直通。现网两台（加克隆）都是模拟 VGA + VNC，卡在宿主机 `nouveau` 上。

## 索引

1. [要解决什么](#1-要解决什么)
2. [现网快照（2026-09-17）](#2-现网快照2026-09-17)
3. [装在哪](#3-装在哪)
4. [3389 切换](#4-3389-切换)
5. [克隆 + rotate](#5-克隆--rotate)
6. [命令与 Web](#6-命令与-web)
7. [技术选型](#7-技术选型)
8. [和旧脚本的关系](#8-和旧脚本的关系)
9. [已知限制](#9-已知限制)
10. [故障](#10-故障)

---

## 1. 要解决什么

以前：`vm-fwd` 把宿主机 `:3389` 钉死给 `win10-nika`，`seekos-fwd` 另开 `:3390` 给 seekos。换哪台就记端口，规则还容易变死（指向已经不存在的 IP）。

现在：

- RDP 客户端永远连 **`192.168.4.158:3389`**
- `vmctl rdp <名字>`（或 Web 上「切 3389」）把 DNAT 指到那一台的客人 `:3389`
- 克隆：稀疏拷盘 + 新 NVRAM + 换 UUID/MAC/盘序列/SMBIOS，不共用身份
- **不做 GPU 直通、不加 GPU 互斥**。现网 XML 没有 `hostdev` / `vfio`

`:3390` 已拆除。`seekos-fwd` 变成 `vmctl rdp` 的兼容入口，不会再写 3390。

---

## 2. 现网快照（2026-09-17）

| 项 | 值 |
|---|---|
| 宿主机 | `cclaptop` / `192.168.4.158` / `wlo1` |
| NAT | `192.168.243.0/24` virbr0 `192.168.243.1` |
| 3389 | `wlo1:3389` → 当前目标客人 `:3389`（comment `vmctl-rdp`） |
| 3390 | **已删除** |
| Web | http://192.168.4.158:8787/ |
| systemd | `vmctl.service` enabled + active |
| Git | origin `https://github.com/ccdescipline/Nika-Read-Only.git` |

核对当时 `vmctl list`：

| NAME | STATE | MEM | IP | MAC | NIC | RDP |
|---|---|---|---|---|---|---|
| seekos-ltsc2 | running | 4G | 192.168.243.147 | `00:e0:4c:53:23:49` | rtl8125 | * |
| seekos-ltsc | shut off | 4G | — | `3c:97:0e:b1:c7:93` | rtl8125 | |
| win10-nika | shut off | 8G | — | `3c:97:0e:a4:84:88` | e1000e | |

`seekos-ltsc2` 是用 vmctl 从 `seekos-ltsc` 克隆出来的（Realtek OUI `00:e0:4c`，不再给 rtl8125 贴 Intel `3c:97:0e`）。下次 rotate / 克隆会变，以 `vmctl list` 为准。

两台源域都没有 GPU 直通。显示 = 模拟 VGA + VNC（`127.0.0.1`，走 SSH 隧道）。

---

## 3. 装在哪

| 角色 | 路径 |
|---|---|
| 仓库源码 | `/home/cc/code/Nika-Read-Only/vmctl/`（Windows 仓库同路径） |
| 运行副本 | `/usr/local/lib/vmctl/` |
| CLI | `/usr/local/bin/vmctl` |
| systemd | `/etc/systemd/system/vmctl.service` |
| libvirt hook | `/etc/libvirt/hooks/qemu`（目标 VM 开机自动重绑 3389） |
| 状态 | `/var/lib/vmctl/rdp-target`、`/var/lib/vmctl/xml/` |
| 安装 | `sudo bash /home/cc/code/Nika-Read-Only/vmctl/install.sh` |

依赖：系统自带 Python 3.12 + `python3-libvirt`。宿主机没有 pip / FastAPI，Web 用标准库 `http.server`。

重装不会停正在跑的 VM。hook 放进 `/etc/libvirt/hooks/qemu` 后立刻生效，不必重启 libvirtd。

---

## 4. 3389 切换

```
Windows RDP 客户端
    →  192.168.4.158:3389
    →  iptables DNAT (只留一条，comment=vmctl-rdp)
    →  当前选中 VM 的 :3389
```

规则：

- 只动 **宿主机端口 3389** 的 NAT PREROUTING，绑 `-i wlo1`
- `LIBVIRT_FWI` 插一条到该 VM IP 的 `:3389` ACCEPT（插在 REJECT 前面）
- 不碰别的端口
- 目标没开机：CLI 报错；Web「切 3389」会带 `start: true` 先开再切
- 保存目标名到 `/var/lib/vmctl/rdp-target`；`netfilter-persistent save`
- libvirt `qemu` hook：若开机的域就是当前目标，等 DHCP 后重绑（IP 变了也能跟上）
- `vmctl serve` 启动时也会尝试重绑已保存目标

```bash
vmctl rdp seekos-ltsc2          # 切过去（必须已运行）
vmctl rdp win10-nika --start    # 没开就先开
vmctl rdp --status
```

核对：

```bash
iptables-save -t nat | grep 3389
# 应只有：-A PREROUTING -i wlo1 -p tcp --dport 3389 -m comment --comment vmctl-rdp -j DNAT --to-destination <IP>:3389
```

⚠️ 本机不要连 `127.0.0.1:3389`（规则绑在 `wlo1` 入向）。从 LAN 连 `192.168.4.158:3389`。

⚠️ 切 MAC / 克隆之后 Windows 可能把网络打成「公用」，防火墙挡 RDP。VNC 隧道进去：

```powershell
Set-NetConnectionProfile -InterfaceAlias (Get-NetConnectionProfile).InterfaceAlias -NetworkCategory Private
```

---

## 5. 克隆 + rotate

源必须 **关机**。流程：

1. `virsh dumpxml --migratable`
2. 盘：默认 `qemu-img convert -S 4k` 稀疏整拷到 `/var/lib/libvirt/images/<新名字>.raw`；`--overlay` 则 qcow2 backing（源盘之后不要开机写入）
3. 新 NVRAM 路径，不拷旧 vars（让 libvirt 从 template 生成）
4. 改名 / UUID / 盘路径 / MAC / 盘序列 / SMBIOS type 1/2/3/17 序列
5. 磁盘 boot order=1，光驱=2；VNC autoport；剥掉 `hostdev` / `qemu:override`（现网没有，防以后误带）
6. `virsh define`

MAC OUI 按网卡型号：

| model | OUI |
|---|---|
| rtl8125 / rtl8139 | `00:e0:4c` Realtek |
| e1000e / e1000 / virtio | `3c:97:0e` Intel |

```bash
# 源关机
virsh shutdown seekos-ltsc
vmctl clone seekos-ltsc seekos-ltsc2
vmctl start seekos-ltsc2
vmctl rdp seekos-ltsc2
```

只换身份、不拷盘：`vmctl rotate NAME`（也要关机）。

克隆不改 QEMU 二进制。模拟器层指纹所有 VM 仍共享，见身份文档。

---

## 6. 命令与 Web

```bash
vmctl list
vmctl start NAME
vmctl stop NAME          # ACPI
vmctl destroy NAME       # 强制
vmctl rdp NAME [--start]
vmctl clone SRC DST [--overlay] [--start]
vmctl rotate NAME
vmctl serve              # systemd 已在跑，一般不用手开
```

Web：http://192.168.4.158:8787/ （绑 `0.0.0.0:8787`，无密码，只当 LAN 用）。

Cockpit 仍是 `https://192.168.4.158:9090`。VNC 仍走 SSH 隧道：

```bat
ssh -N -L 5900:127.0.0.1:5900 cc@192.168.4.158
```

克隆出来的域 VNC 是 autoport，以 `vmctl list` 的 VNC 列为准，不一定是 5900。

---

## 7. 技术选型

| 选 | 原因 |
|---|---|
| Python 3.12 + `python3-libvirt` | 宿主机已有，不用再装语言 |
| 标准库 `http.server` + 单页 HTML | 无 pip / 无 FastAPI；Windows 浏览器点「切 3389」 |
| CLI 与 Web 同一套代码 | `python3 -m vmctl` |
| 不选 Proxmox / virt-clone / Cockpit 插件 | 补丁 QEMU、`qemu:commandline`、AHCI `controller=1`、rotate 它们扛不住 |
| 不选 GPU 锁 | 现网没有直通 |

---

## 8. 和旧脚本的关系

| 旧 | 现在 |
|---|---|
| `sudo vm-fwd` | `vmctl rdp win10-nika --start` |
| `sudo seekos-fwd`（3390） | `vmctl rdp seekos-ltsc`（走 3389） |
| `/usr/local/bin/vm-rotate` | `vmctl rotate NAME`（旧脚本还在） |
| `net-rotate` 末尾调 fwd | 改成 `vmctl rdp $VM_NAME` |

`/usr/local/bin/vm-fwd` 还在。它会清 **所有** 3389 DNAT 再按自己的规则加，和 vmctl 抢规则，**不要再跑**。`seekos-fwd.sh` 已改成直接 `exec vmctl rdp`。

---

## 9. 已知限制

- Web 无认证，只给 `192.168.4.0/24` 用
- 客人没有 qemu-ga：主机名、SID、DUID、网络配置文件要进系统自己改
- overlay 克隆绑定源盘只读；源再开机写入会把克隆带崩
- QEMU/OVMF 全局一份，克隆只换 XML 层身份
- `LIBVIRT_FWI` 里可能还留着旧网段 `192.168.76.0/24` 的残骸，不影响现网 243
- WiFi IP 会漂（曾经 `.159`）。Web 用当时的 `wlo1` 地址打开

---

## 10. 故障

| 症状 | 处理 |
|---|---|
| `virsh list` 空、vmctl 有机器 | `export LIBVIRT_DEFAULT_URI=qemu:///system` |
| 切了 3389 连不上 | 目标是否 running；`vmctl list` 有没有 IP；Windows 网络是否公用 |
| `vmctl rdp` 报未运行 | 先 `vmctl start` 或加 `--start` |
| 克隆报源在跑 | 先 `vmctl stop` / `shutdown`，确认 shut off |
| 重启后 3389 丢 | `systemctl status vmctl`；hook 在不在；`vmctl rdp --status` 后重切 |
| Web 打不开 | `systemctl restart vmctl`；端口 8787 |
| 3390 又出现 | 不要跑旧 `seekos-fwd` 二进制；仓库脚本已改成 vmctl |
