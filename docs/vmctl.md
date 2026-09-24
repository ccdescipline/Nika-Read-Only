# vmctl：虚拟机管理（列表 / 启停 / 克隆 / 3389 切换 / 客人自助随机化）

> 2026-09-17 初稿。对照仓库 `vmctl/` + 宿主机 `cclaptop`。
> 再刷新：2026-09-17 晚（内核试更回滚；当时仍 Jul 13 tkg。见 [`kvm-setup §5.1`](kvm-setup-ubuntu24-from-zero.md#51-2026-09-17-试更官方-intel619mypatch已回滚)）。
> 再刷新：2026-09-23（内核 `#3` / `6.19.14-3`，9/22 补丁 + bootmgfw 已修。见 [`kvm-setup §5.2`](kvm-setup-ubuntu24-from-zero.md#52-2026-09-23-上-922-补丁并修好-bootmgfw)）。
> 再刷新：2026-09-24（新增 **客人自助随机化** `/api/self/rotate`；补全 HTTP API 参考。见 [§7](#7-http-api) / [§8](#8-客人自助随机化)）。
> 总索引：[`README.md`](README.md)。从零搭建 / 直通仍看 [`kvm-setup-ubuntu24-from-zero.md`](kvm-setup-ubuntu24-from-zero.md)。身份分层看 [`qemu-identity-and-rebuild.md`](qemu-identity-and-rebuild.md)。
>
> 本文只覆盖 **vmctl** 这一层：不管 QEMU 重编、不管 GPU 直通。现网两台（加克隆）都是模拟 VGA + VNC，卡在宿主机 `nouveau` 上。

## 索引

1. [要解决什么](#1-要解决什么)
2. [现网快照（2026-09-24）](#2-现网快照2026-09-24)
3. [装在哪](#3-装在哪)
4. [3389 切换](#4-3389-切换)
5. [克隆 + rotate](#5-克隆--rotate)
6. [命令与 Web](#6-命令与-web)
7. [HTTP API](#7-http-api)
8. [客人自助随机化](#8-客人自助随机化)
9. [技术选型](#9-技术选型)
10. [和旧脚本的关系](#10-和旧脚本的关系)
11. [已知限制](#11-已知限制)
12. [故障](#12-故障)

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

## 2. 现网快照（2026-09-24）

| 项 | 值 |
|---|---|
| 宿主机 | `cclaptop` / `192.168.4.158` / `wlo1` |
| NAT | `192.168.243.0/24` virbr0 `192.168.243.1` |
| 3389 | `wlo1:3389` → 当前目标客人 `:3389`（comment `vmctl-rdp`） |
| 3390 | **已删除** |
| Web | http://192.168.4.158:8787/ |
| systemd | `vmctl.service` enabled + active |
| Git | origin `https://github.com/ccdescipline/Nika-Read-Only.git` |
| 内核 | `6.19.14-tkg-eevdf` **`#3` Sep 23 11:26 UTC**（包 `6.19.14-3`）。9/22 补丁 + bootmgfw 修正已上，`seekos-ltsc` 能进锁屏。见 [`kvm-setup §5.2`](kvm-setup-ubuntu24-from-zero.md#52-2026-09-23-上-922-补丁并修好-bootmgfw) |

核对当时 `vmctl list`（2026-09-24，`seekos-ltsc` 刚被客人自助随机化过一次，见 §8.3）：

| NAME | STATE | MEM | IP | MAC | NIC | RDP |
|---|---|---|---|---|---|---|
| seekos-ltsc | running | 4G | 192.168.243.245 | `00:e0:4c:cd:50:22` | rtl8125 | * |
| seekos-ltsc2 | shut off | 4G | — | `00:e0:4c:1d:9c:de` | rtl8125 | |

`win10-nika` 已不在 libvirt 里（9/17 的表里还有）。`seekos-ltsc2` 是用 vmctl 从 `seekos-ltsc` 克隆出来的。rtl8125 一律用 Realtek OUI `00:e0:4c`。每次 rotate / 克隆都会变，以 `vmctl list` 为准。

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

重装不会停正在跑的 VM。**`install.sh` 用的是 `enable --now`，服务已在跑时不会重启**，改了代码要再重启一次：

```bash
sudo bash /home/cc/code/Nika-Read-Only/vmctl/install.sh && sudo systemctl restart vmctl
```

2026-09-24 部署前的运行副本备份在 `/var/lib/vmctl/bak-20260924/`。hook 放进 `/etc/libvirt/hooks/qemu` 后立刻生效，不必重启 libvirtd。

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

Web 没有 overlay 选项。CLI 仍有 `--overlay`，不要用，除非源盘永远不开。

删除：`vmctl delete NAME -y --force`，或 Web「删除」（要输入名字确认）。只删这台自己的盘/NVRAM，不删别人当 backing 的源盘。

---

## 6. 命令与 Web

```bash
vmctl list
vmctl start NAME
vmctl stop NAME          # ACPI
vmctl destroy NAME       # 强制
vmctl rdp NAME [--start]
vmctl clone SRC DST [--start]
vmctl delete NAME [-y] [--force]
vmctl rotate NAME
vmctl serve              # systemd 已在跑，一般不用手开
```

Web：http://192.168.4.158:8787/ （绑 `0.0.0.0:8787`，无密码，只当 LAN 用）。接口见 [§7](#7-http-api)；客人里一键随机化见 [§8](#8-客人自助随机化)。

Cockpit 仍是 `https://192.168.4.158:9090`。VNC 仍走 SSH 隧道：

```bat
ssh -N -L 5900:127.0.0.1:5900 cc@192.168.4.158
```

克隆出来的域 VNC 是 autoport，以 `vmctl list` 的 VNC 列为准，不一定是 5900。

---

## 7. HTTP API

服务：`vmctl serve`（systemd），`0.0.0.0:8787`，标准库 `http.server`，**无认证**。代码 `vmctl/server.py`。

约定：

- POST body 是 JSON（`Content-Type: application/json`），空 body 当 `{}`
- 返回 JSON。已知错误（VM 不存在 / 在跑 / 名字不合法等）→ `400 {"error": "..."}`；其它异常 → `500 {"error": "..."}`；路径不对 → `404`
- 耗时操作（clone / net-rotate / self-rotate）走后台任务：立即回 `{"job": "<id>"}`，再轮询 `/api/jobs/<id>`
- 下表“状态” = `/api/status` 的返回。很多 POST 成功后直接回它，前端拿来刷新

### 7.1 GET

| 路径 | 返回 |
|---|---|
| `/` | Web UI（`ui.html`） |
| `/api/status` | `{"rdp": {...}, "vms": [...], "jobs": [最近 8 个]}` |
| `/api/jobs/<id>` | `{"id","kind","status","log":[...],"error","result","started","finished"}`；`status` = `running` / `ok` / `error`；没有 → 404 |
| `/api/self` | **按请求来源 IP** 反查 VM：`{"ip": "来源 IP", "name": "VM 名，认不出为空串"}` |

- `vms[]` 每项：`name state running memory vcpus ip mac nic disk vnc rdp`
- `rdp`：`name ip dnat_ip running host ext_if stale`（`stale=true` = DNAT 指的 IP 和 VM 现在的 IP 不一致）

### 7.2 POST

| 路径 | body | 行为 | 返回 |
|---|---|---|---|
| `/api/start` | `{"name"}` | 开机；若是 3389 目标顺手重绑 | 状态 |
| `/api/stop` | `{"name"}` | ACPI 关机 | 状态 |
| `/api/destroy` | `{"name"}` | 强制关机 | 状态 |
| `/api/rdp` | `{"name", "start"}` | 宿主机 `:3389` 指过去；`start=true` 先开机 | 状态 + `ok:{name,ip,host,ext_if,fwi}` |
| `/api/clone` | `{"src","dst","overlay","start"}` | 后台克隆（源必须关机） | `{"job"}` |
| `/api/rotate` | `{"name"}` | Web「随机化」：换 UUID / MAC / 盘序列 / SMBIOS，保留 NVRAM。**必须已关机**，同步执行 | `{"name","identity"}` |
| `/api/net-rotate` | `{"name","start"}`（`start` 默认 true） | 后台跑 `net-rotate`（换网段 / 网关 MAC+DNS 名 / VM MAC）。其它 VM 必须全关 | `{"job"}` |
| `/api/delete` | `{"name","keep_disk","force"}` | 删域 + 它自己的盘 / NVRAM | 状态 + `ok:{removed,skipped}` |
| `/api/self/rotate` | 忽略 | **客人自助**：来源 IP → VM，后台 强制关机 → rotate → 开机 → 3389 重绑。见 [§8](#8-客人自助随机化) | `{"job","name","ip"}`；认不出 → 404 |

`identity` 字段：`uuid mac disk_sn sys_sn board_sn chassis_sn mem_sn`。

例：

```bash
curl -s http://192.168.4.158:8787/api/status | python3 -m json.tool
curl -s -X POST -H 'Content-Type: application/json' -d '{"name":"seekos-ltsc","start":true}' http://192.168.4.158:8787/api/rdp
curl -s http://192.168.4.158:8787/api/jobs/<id>
```

---

## 8. 客人自助随机化

需求：客人（Windows）里发一个请求，宿主机自己判断是哪台 VM，执行 Web 上同一个「随机化」，强制关机再开机。

### 8.1 流程

```
客人  POST http://<网关 或 192.168.4.158>:8787/api/self/rotate
  │   来源 IP 就是客人真实 IP（virbr0 进宿主机不经 NAT）
  ▼
vmctl  virt.name_by_ip(ip)   遍历运行中的域，用 DHCP 租约 / MAC 查 IP 比对；认不出 → 404
  │    jobs.submit("self-rotate", clone.rotate_restart) → 立即回 {"job","name","ip"}
  ▼
后台  sleep 1s（让响应先回到客人）
      → virt.destroy        强制关机
      → clone.rotate        = /api/rotate：UUID / MAC / 盘序列 / SMBIOS，保留 NVRAM
      → virt.start
      → 若是 3389 目标：等新 IP（≤120s）→ rdp.apply
```

- 同一台还在随机化时再请求 → 新任务 `error: 已在随机化中`，不会叠加
- MAC 变 → DHCP 给新 IP；3389 目标自动跟过去（libvirt hook 也会再试一次）
- 3389 重绑失败只记日志，不算任务失败
- 任务存在内存：vmctl 服务重启后查不到旧 job
- 客人连宿主机哪个地址都行（网关 `192.168.X.1` 或 LAN `192.168.4.158`），来源 IP 都是客人自己的

代码：`server.py`（路由）、`virt.name_by_ip`、`clone.rotate_restart`。

### 8.2 客人侧脚本

| 文件 | 用途 |
|---|---|
| `vmctl/contrib/guest-rotate.ps1` | 一行式，直接触发 |
| `vmctl/contrib/guest-rotate-test.ps1` | 测试：先 `GET /api/self` 确认身份；加 `-Rotate` 且输入 `YES` 才真触发；job URL 存到 `%PUBLIC%\vmctl-last-job.txt` |

两份都只用 ASCII（PowerShell 5.1 读无 BOM 的 UTF-8 会乱码）。取网关用 .NET `NetworkInterface`，不用 `Get-NetRoute`（精简版 LTSC 查不到）。取不到网关就回落 `192.168.4.158`。

```powershell
# 只检查
powershell -ExecutionPolicy Bypass -File .\guest-rotate-test.ps1
# 真随机化（会被强制关机）
powershell -ExecutionPolicy Bypass -File .\guest-rotate-test.ps1 -Rotate
# 开机后看结果
Invoke-RestMethod (Get-Content $env:PUBLIC\vmctl-last-job.txt) | ConvertTo-Json -Depth 6
```

一行式（手敲 / 放计划任务）：

```powershell
$gw = [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() | ? { $_.OperationalStatus -eq "Up" } |
    % { $_.GetIPProperties().GatewayAddresses } | ? { $_.Address.AddressFamily -eq "InterNetwork" -and "$($_.Address)" -ne "0.0.0.0" } |
    Select -First 1 -ExpandProperty Address
if (-not $gw) { $gw = "192.168.4.158" }
Invoke-RestMethod -Method Post -Uri "http://${gw}:8787/api/self/rotate" -ContentType application/json -Body '{}'
```

### 8.3 实测（2026-09-24，seekos-ltsc）

| 项 | 前 | 后 |
|---|---|---|
| IP | 192.168.243.105 | 192.168.243.245 |
| UUID | — | `6e189450-b10b-4800-8415-4572bc72a0b2` |
| MAC | — | `00:e0:4c:cd:50:22` |
| disk_sn | — | `4JH267OLYC8M` |
| sys / board / chassis / mem SN | — | `YUL29L50DYHC` / `MM2RURLW5NQI` / `R13KABW0ZYB4` / `0XUA85` |
| 3389 DNAT | → `.105:3389` | → `.245:3389`（自动） |

job log：`强制关机 → 随机化 → uuid/mac/disk_sn → 启动 → 3389 → 192.168.243.245`，`status: ok`。

客人里测试脚本显示的本机 IP / 网关为空（精简系统的网络 API 拿不到），回落到 `192.168.4.158` 后宿主机仍正确认出 `seekos-ltsc`，不影响功能。

---

## 9. 技术选型

| 选 | 原因 |
|---|---|
| Python 3.12 + `python3-libvirt` | 宿主机已有，不用再装语言 |
| 标准库 `http.server` + 单页 HTML | 无 pip / 无 FastAPI；Windows 浏览器点「切 3389」 |
| CLI 与 Web 同一套代码 | `python3 -m vmctl` |
| 不选 Proxmox / virt-clone / Cockpit 插件 | 补丁 QEMU、`qemu:commandline`、AHCI `controller=1`、rotate 它们扛不住 |
| 不选 GPU 锁 | 现网没有直通 |

---

## 10. 和旧脚本的关系

| 旧 | 现在 |
|---|---|
| `sudo vm-fwd` | `vmctl rdp win10-nika --start` |
| `sudo seekos-fwd`（3390） | `vmctl rdp seekos-ltsc`（走 3389） |
| `/usr/local/bin/vm-rotate` | `vmctl rotate NAME`（旧脚本还在） |
| `net-rotate` 末尾调 fwd | 改成 `vmctl rdp $VM_NAME` |

`/usr/local/bin/vm-fwd` 还在。它会清 **所有** 3389 DNAT 再按自己的规则加，和 vmctl 抢规则，**不要再跑**。`seekos-fwd.sh` 已改成直接 `exec vmctl rdp`。

---

## 11. 已知限制

- Web / API 无认证，只给 `192.168.4.0/24` 用
- **客人也能访问 8787 的全部接口**（宿主机 `INPUT` 默认 ACCEPT，virbr0 → `192.168.243.1:8787` 通）。`/api/self/rotate` 本来就需要客人能调；其它接口暂未按来源限制（9/24 决定先不做权限）
- 网关上开着 8787 本身是客人能扫到的特征，和 net-rotate 伪装路由器的目标冲突
- 后台任务只存在内存，`systemctl restart vmctl` 后丢
- 按来源 IP 认 VM：客人手动改静态 IP 冒充别的 VM 理论上可行（没校验 MAC / 没上 nwfilter）
- 客人没有 qemu-ga：主机名、SID、DUID、网络配置文件要进系统自己改
- overlay 克隆绑定源盘只读；源再开机写入会把克隆带崩
- QEMU/OVMF 全局一份，克隆只换 XML 层身份
- `LIBVIRT_FWI` 里可能还留着旧网段 `192.168.76.0/24` 的残骸，不影响现网 243
- WiFi IP 会漂（曾经 `.159`）。Web 用当时的 `wlo1` 地址打开

---

## 12. 故障

| 症状 | 处理 |
|---|---|
| `virsh list` 空、vmctl 有机器 | `export LIBVIRT_DEFAULT_URI=qemu:///system` |
| 切了 3389 连不上 | 目标是否 running；`vmctl list` 有没有 IP；Windows 网络是否公用 |
| `vmctl rdp` 报未运行 | 先 `vmctl start` 或加 `--start` |
| 克隆报源在跑 | 先 `vmctl stop` / `shutdown`，确认 shut off |
| 重启后 3389 丢 | `systemctl status vmctl`；hook 在不在；`vmctl rdp --status` 后重切 |
| Web 打不开 | `systemctl restart vmctl`；端口 8787 |
| 3390 又出现 | 不要跑旧 `seekos-fwd` 二进制；仓库脚本已改成 vmctl |
| 开机卡 ROG / `bootmgfw.efi` | 不是克隆坏了。现网应是 `#3`（§5.2）。若又卡：回滚 `kernel-bak-jul13-running`，不要重装客人 |
| 客人脚本报 `Get-NetRoute` 找不到 `0.0.0.0/0` | 精简版 LTSC 的 CIM 路由不可用。用仓库新版 `guest-rotate*.ps1`（.NET 取网关，回落 `192.168.4.158`） |
| `/api/self` 返回 `name: ""` / self-rotate 404 | 宿主机从租约查不到这个 IP：`virsh net-dhcp-leases default` 看有没有。客人要用 DHCP，静态 IP 认不出 |
| self-rotate 任务 `已在随机化中` | 上一次还没跑完，等它结束（看 `/api/status` 的 jobs） |
| 随机化后 RDP 连不上 | 新 MAC → Windows 可能判「公用」网络。VNC 进去 `Set-NetConnectionProfile ... -NetworkCategory Private`；再看 `vmctl rdp --status` |
