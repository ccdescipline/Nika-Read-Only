#!/usr/bin/env bash
# vm-fwd.sh — 一键设置 VM 端口转发(RDP + Sunshine)
# 用法: sudo vm-fwd [VM_NAME]
# 默认 VM_NAME = win10-nika
# 会自动:
#   1. 查询 VM 当前 IP
#   2. 清掉所有旧的 3389/Sunshine 转发规则
#   3. 加新规则指向当前 IP

set -eu

VM_NAME="${1:-win10-nika}"
EXT_IF="wlo1"

# 想转发的端口列表
declare -A TCP_PORTS=(
    ["3389"]="RDP"
    # 后面用 Sunshine 时取消注释:
    # ["47984"]="Sunshine-HTTPS"
    # ["47989"]="Sunshine-HTTP"
    # ["47990"]="Sunshine-Web"
    # ["48010"]="Sunshine-RTSP"
)
declare -A UDP_PORTS=(
    # ["47998"]="Sunshine-Video"
    # ["47999"]="Sunshine-Control"
    # ["48000"]="Sunshine-Audio"
    # ["48002"]="Sunshine-Mic"
    # ["48010"]="Sunshine-RTSP-UDP"
)

# ============================================================
# 检查 VM 是否运行
# ============================================================
STATE=$(virsh domstate "$VM_NAME" 2>/dev/null || echo "unknown")
if [[ "$STATE" != "running" ]]; then
    echo "ERROR: VM '$VM_NAME' 未运行 (state: $STATE),先启动:"
    echo "  sudo virsh start $VM_NAME"
    exit 1
fi

# ============================================================
# 拿当前 IP(等最多 30 秒等 DHCP)
# ============================================================
echo "查询 VM IP..."
VM_IP=""
for i in {1..30}; do
    VM_IP=$(virsh domifaddr "$VM_NAME" 2>/dev/null | awk '/ipv4/ {print $4}' | cut -d/ -f1 | head -1)
    [[ -n "$VM_IP" ]] && break
    sleep 1
done

if [[ -z "$VM_IP" ]]; then
    echo "ERROR: 30 秒内没拿到 VM IP。VM 里网络是否 up?"
    echo "  sudo virsh domif-setlink $VM_NAME 3c:97:0e:XX:XX:XX up"
    exit 1
fi

echo "VM IP: $VM_IP"
echo ""

# ============================================================
# 清掉所有涉及以下端口的旧规则
# ============================================================
ALL_PORTS=("${!TCP_PORTS[@]}" "${!UDP_PORTS[@]}")

for port in "${ALL_PORTS[@]}"; do
    # 清 NAT PREROUTING
    while true; do
        LINE=$(iptables -t nat -L PREROUTING --line-numbers -n 2>/dev/null | awk -v p="dpt:$port" '$0 ~ p {print $1; exit}')
        [[ -z "$LINE" ]] && break
        iptables -t nat -D PREROUTING "$LINE"
    done
    # 清 LIBVIRT_FWI
    while true; do
        LINE=$(iptables -L LIBVIRT_FWI --line-numbers -n 2>/dev/null | awk -v p="dpt:$port" '$0 ~ p {print $1; exit}')
        [[ -z "$LINE" ]] && break
        iptables -D LIBVIRT_FWI "$LINE"
    done
done

echo "已清理旧规则"

# ============================================================
# 加新规则
# ============================================================
for port in "${!TCP_PORTS[@]}"; do
    iptables -t nat -A PREROUTING -i "$EXT_IF" -p tcp --dport "$port" -j DNAT --to-destination "$VM_IP:$port"
    iptables -I LIBVIRT_FWI 1 -d "$VM_IP/32" -p tcp --dport "$port" -j ACCEPT
    echo "  TCP $port  (${TCP_PORTS[$port]}) → $VM_IP:$port"
done

for port in "${!UDP_PORTS[@]}"; do
    iptables -t nat -A PREROUTING -i "$EXT_IF" -p udp --dport "$port" -j DNAT --to-destination "$VM_IP:$port"
    iptables -I LIBVIRT_FWI 1 -d "$VM_IP/32" -p udp --dport "$port" -j ACCEPT
    echo "  UDP $port  (${UDP_PORTS[$port]}) → $VM_IP:$port"
done

echo ""
echo "=== ✓ 转发已设置 ==="
echo "从 LAN 访问: <宿主机IP>:3389"
