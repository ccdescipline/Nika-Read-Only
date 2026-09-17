#!/usr/bin/env bash
# net-rotate.sh
# 换 NAT 网段 192.168.X.0/24、virbr0 网关 MAC、网关 DNS 名（跟 OUI 厂商配对）、
# VM 网卡 MAC（Intel OUI 3c:97:0e）
# 不改 UUID / SMBIOS / NVRAM，不改宿主机 hostname（cclaptop）
# 用法:
#   sudo ./net-rotate.sh                 # 默认 seekos-ltsc，改完开机并 vmctl rdp
#   sudo ./net-rotate.sh win10-nika      # 改完开机并 vmctl rdp
#   sudo ./net-rotate.sh seekos-ltsc --no-start
# VM 若在跑会先 destroy

set -eu

if [[ "$(id -u)" -ne 0 ]]; then
    echo "ERROR: 需要 root: sudo $0 ${1:-}"
    exit 1
fi

export LIBVIRT_DEFAULT_URI="${LIBVIRT_DEFAULT_URI:-qemu:///system}"

START=1
VM_NAME="seekos-ltsc"
for arg in "$@"; do
    case "$arg" in
        --no-start) START=0 ;;
        --start) START=1 ;;
        -h|--help)
            echo "Usage: $0 [VM_NAME] [--no-start]"
            exit 0
            ;;
        *)
            VM_NAME="$arg"
            ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"
BAK_DIR="/home/cc/nika-rebuild"
mkdir -p "$BAK_DIR"

if ! virsh dominfo "$VM_NAME" >/dev/null 2>&1; then
    echo "ERROR: VM '$VM_NAME' 不存在"
    exit 1
fi

OTHER_RUNNING=""
while read -r name; do
    [[ -z "$name" || "$name" == "$VM_NAME" ]] && continue
    OTHER_RUNNING="$name"
done < <(virsh list --name)

if [[ -n "$OTHER_RUNNING" ]]; then
    echo "ERROR: 还有其它 VM 在跑: $OTHER_RUNNING"
    echo "      改 default 网段会踢掉所有用 virbr0 的机器，先关机。"
    exit 1
fi

STATE=$(virsh domstate "$VM_NAME" 2>/dev/null || echo "unknown")
if [[ "$STATE" == "running" ]]; then
    echo "destroy $VM_NAME ..."
    virsh destroy "$VM_NAME" >/dev/null
fi

pick_octet() {
    local n
    while true; do
        n=$((RANDOM % 240 + 10))
        case "$n" in
            4|76|122) continue ;;
        esac
        echo "$n"
        return
    done
}

# OUI|vendor-dns,short-name  — 短名给 PTR/NetBIOS，带点的给浏览器习惯域名
GW_PRESETS=(
    "04:d4:c4|router.asus.com,router"
    "2c:56:dc|router.asus.com,router"
    "38:d5:47|router.asus.com,router"
    "50:c7:bf|tplinkwifi.net,tplinkap.net,tplink"
    "e4:d3:32|tplinkwifi.net,tplinkap.net,tplink"
    "c0:06:c3|tplinkwifi.net,tplinkap.net,tplink"
    "a0:63:91|routerlogin.net,routerlogin.com,NETGEAR"
    "64:cc:2e|miwifi.com,miwifi"
)
GW_DOMAIN="lan"

pick_gw() {
    local preset="${GW_PRESETS[RANDOM % ${#GW_PRESETS[@]}]}"
    GW_OUI="${preset%%|*}"
    GW_HOSTNAMES="${preset#*|}"
    NEW_GW_MAC=$(printf '%s:%02x:%02x:%02x' "$GW_OUI" $((RANDOM % 256)) $((RANDOM % 256)) $((RANDOM % 256)))
}

pick_nic_mac() {
    printf '3c:97:0e:%02x:%02x:%02x' $((RANDOM % 256)) $((RANDOM % 256)) $((RANDOM % 256))
}

NET_XML=$(mktemp -t net-rotate.XXXXXX.xml)
VM_XML=$(mktemp -t vm-rotate.XXXXXX.xml)
trap 'rm -f "$NET_XML" "$VM_XML"' EXIT

virsh net-dumpxml default > "$NET_XML"
virsh dumpxml --migratable "$VM_NAME" > "$VM_XML"
cp "$NET_XML" "$BAK_DIR/default-net.xml.bak-mac-$STAMP"
cp "$VM_XML" "$BAK_DIR/${VM_NAME}.xml.bak-net-$STAMP"

OLD_NET_MAC=$(grep -oE "mac address='[^']+'" "$NET_XML" | head -1 | sed -E "s/mac address='//;s/'//")
OLD_NET_IP=$(grep -oE "ip address='[^']+'" "$NET_XML" | head -1 | sed -E "s/ip address='//;s/'//")
OLD_VM_MAC=$(grep -oE "<mac address='[^']+'" "$VM_XML" | head -1 | sed -E "s/<mac address='//;s/'//")
OLD_DOMAIN=$(grep -oE "<domain name='[^']+'" "$NET_XML" | head -1 | sed -E "s/<domain name='//;s/'//" || true)
OLD_GW_NAME=$(python3 - "$NET_XML" <<'PY' || true
import sys, xml.etree.ElementTree as ET
root = ET.parse(sys.argv[1]).getroot()
dns = root.find("dns")
if dns is None:
    sys.exit(0)
host = dns.find("host")
if host is None:
    sys.exit(0)
names = [h.text for h in host.findall("hostname") if h.text]
print(",".join(names))
PY
)

OCTET=$(pick_octet)
NEW_GW="192.168.${OCTET}.1"
NEW_DHCP_S="192.168.${OCTET}.2"
NEW_DHCP_E="192.168.${OCTET}.254"
pick_gw
NEW_VM_MAC=$(pick_nic_mac)
NEW_GW_PRIMARY="${GW_HOSTNAMES%%,*}"

echo "=== 旧 ==="
echo "  网关 IP/MAC = $OLD_NET_IP  $OLD_NET_MAC"
echo "  网关 DNS    = ${OLD_GW_NAME:-<无>}  domain=${OLD_DOMAIN:-<无>}"
echo "  VM NIC MAC  = $OLD_VM_MAC"
echo "备份: $BAK_DIR/*$STAMP"
echo ""
echo "=== 新 ==="
echo "  网段        = 192.168.${OCTET}.0/24"
echo "  网关        = $NEW_GW  $NEW_GW_MAC"
echo "  网关 DNS    = $GW_HOSTNAMES  domain=$GW_DOMAIN"
echo "  VM NIC MAC  = $NEW_VM_MAC"
echo ""

python3 - "$NET_XML" "$NEW_GW_MAC" "$NEW_GW" "$NEW_DHCP_S" "$NEW_DHCP_E" "$GW_DOMAIN" "$GW_HOSTNAMES" <<'PY'
import sys
import xml.etree.ElementTree as ET

path, new_mac, new_gw, dhcp_s, dhcp_e, domain, hostnames_csv = sys.argv[1:]
hostnames = [h for h in hostnames_csv.split(",") if h]
if not hostnames:
    raise SystemExit("empty gateway hostnames")

tree = ET.parse(path)
root = tree.getroot()
root.attrib.pop("connections", None)

mac_el = root.find("mac")
if mac_el is None:
    raise SystemExit("no <mac> in network xml")
mac_el.set("address", new_mac)

ip_el = root.find("ip")
if ip_el is None:
    raise SystemExit("no <ip> in network xml")
ip_el.set("address", new_gw)
dhcp = ip_el.find("dhcp")
rng = None if dhcp is None else dhcp.find("range")
if rng is None:
    raise SystemExit("no dhcp range")
rng.set("start", dhcp_s)
rng.set("end", dhcp_e)

ip_idx = list(root).index(ip_el)

dom = root.find("domain")
if dom is None:
    dom = ET.Element("domain")
    root.insert(ip_idx, dom)
    ip_idx += 1
dom.set("name", domain)
dom.set("localOnly", "yes")

dns = root.find("dns")
if dns is None:
    dns = ET.Element("dns")
    root.insert(ip_idx, dns)
for child in list(dns):
    if child.tag == "host":
        dns.remove(child)
host = ET.SubElement(dns, "host")
host.set("ip", new_gw)
for name in hostnames:
    hn = ET.SubElement(host, "hostname")
    hn.text = name

ET.indent(tree, space="  ")
tree.write(path, encoding="utf-8", xml_declaration=False)
with open(path, "a", encoding="utf-8") as f:
    f.write("\n")
PY

python3 - "$VM_XML" "$OLD_VM_MAC" "$NEW_VM_MAC" <<'PY'
import sys
path, old_mac, new_mac = sys.argv[1:]
t = open(path, encoding="utf-8").read()
t = t.replace(f"<mac address='{old_mac}'", f"<mac address='{new_mac}'", 1)
open(path, "w", encoding="utf-8").write(t)
PY

echo "重定义 libvirt 网络 default ..."
virsh net-destroy default >/dev/null
virsh net-undefine default >/dev/null
virsh net-define "$NET_XML" >/dev/null
virsh net-autostart default >/dev/null
virsh net-start default >/dev/null

echo "重定义 VM $VM_NAME（保留 NVRAM）..."
virsh undefine --keep-nvram "$VM_NAME" >/dev/null
virsh define "$VM_XML" >/dev/null

echo ""
echo "核对:"
ip -br link show virbr0 || true
virsh net-dumpxml default | grep -E "mac address|ip address|range start|domain name|<hostname>"

if [[ "$START" != 1 ]]; then
    echo ""
    echo "未开机。启动: virsh start $VM_NAME"
    echo "然后: vmctl rdp $VM_NAME"
    exit 0
fi

echo "启动 $VM_NAME ..."
virsh start "$VM_NAME" >/dev/null

if command -v vmctl >/dev/null 2>&1; then
    echo "3389: vmctl rdp $VM_NAME"
    vmctl rdp "$VM_NAME"
else
    echo "没有 vmctl，请手动: vmctl rdp $VM_NAME"
fi

echo ""
echo "客人里检查:"
echo "  arp -a"
echo "  nslookup $NEW_GW"
echo "  ping -a $NEW_GW"
echo "  ipconfig /all"
echo "网关应是 $NEW_GW_MAC，DNS 名 $NEW_GW_PRIMARY / $GW_DOMAIN（不是 cclaptop）"
echo "MAC 变了以后 Windows 可能把网络打成公用。VNC 进去执行:"
echo "  Set-NetConnectionProfile -InterfaceAlias (Get-NetConnectionProfile).InterfaceAlias -NetworkCategory Private"
