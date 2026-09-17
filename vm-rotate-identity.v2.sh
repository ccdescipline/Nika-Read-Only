#!/usr/bin/env bash
# vm-rotate-identity.sh
# 随机化 VM 硬件身份：UUID / NIC MAC / 磁盘序列号 / SMBIOS type 1/2/3/17 序列号
# 不改产品名、CPU 型号、不重置 NVRAM
# 用法: sudo vm-rotate [VM_NAME]
# 默认 VM_NAME = win10-nika
# VM 必须已关机

set -eu

VM_NAME="${1:-win10-nika}"
XML_FILE=$(mktemp -t vm-rotate.XXXXXX.xml)
BACKUP_FILE="/var/lib/libvirt/${VM_NAME}.xml.$(date +%Y%m%d-%H%M%S).bak"
trap 'rm -f "$XML_FILE"' EXIT

export LIBVIRT_DEFAULT_URI="${LIBVIRT_DEFAULT_URI:-qemu:///system}"

_gen_alnum() {
    local len="$1"
    local chars='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
    local out=''
    local i
    for ((i=0; i<len; i++)); do
        out+="${chars:$((RANDOM % 36)):1}"
    done
    printf '%s' "$out"
}
gen_serial12() { _gen_alnum 12; }
gen_serial6()  { _gen_alnum 6; }
gen_mac()      { printf '3c:97:0e:%02x:%02x:%02x' $((RANDOM%256)) $((RANDOM%256)) $((RANDOM%256)); }
gen_uuid()     { cat /proc/sys/kernel/random/uuid; }

if ! virsh dominfo "$VM_NAME" >/dev/null 2>&1; then
    echo "ERROR: VM '$VM_NAME' not found."
    exit 1
fi

STATE=$(virsh domstate "$VM_NAME" 2>/dev/null || echo "unknown")
if [[ "$STATE" == "running" ]]; then
    echo "ERROR: VM '$VM_NAME' is running. Shut it down first:"
    echo "  virsh shutdown $VM_NAME"
    exit 1
fi

echo "VM '$VM_NAME' state: $STATE"
echo ""

NEW_UUID=$(gen_uuid)
NEW_MAC=$(gen_mac)
NEW_DISK_SN=$(gen_serial12)
NEW_SYS_SN=$(gen_serial12)
NEW_BOARD_SN=$(gen_serial12)
NEW_CHASSIS_SN=$(gen_serial12)
NEW_MEM_SN=$(gen_serial6)

virsh dumpxml "$VM_NAME" > "$XML_FILE"
mkdir -p /var/lib/libvirt
cp "$XML_FILE" "$BACKUP_FILE"

echo "=== 旧身份 ==="
printf "  UUID          = %s\n" "$(grep -oE '<uuid>[^<]+' "$XML_FILE" | head -1 | sed 's/<uuid>//')"
printf "  NIC MAC       = %s\n" "$(grep -oE 'mac address=.[[:xdigit:]:]+' "$XML_FILE" | head -1 | sed -E 's/mac address=.//;s/["'\'']//')"
printf "  Disk Serial   = %s\n" "$(grep -oE '<serial>[^<]+' "$XML_FILE" | head -1 | sed 's/<serial>//')"
echo "备份原 XML: $BACKUP_FILE"
echo ""

echo "=== 新身份 ==="
printf "  UUID          = %s\n" "$NEW_UUID"
printf "  NIC MAC       = %s\n" "$NEW_MAC"
printf "  Disk Serial   = %s\n" "$NEW_DISK_SN"
printf "  System Serial = %s\n" "$NEW_SYS_SN"
printf "  Board Serial  = %s\n" "$NEW_BOARD_SN"
printf "  Chassis SN    = %s\n" "$NEW_CHASSIS_SN"
printf "  Memory Serial = %s\n" "$NEW_MEM_SN"
echo ""

sed -i -E "s|<uuid>[^<]*</uuid>|<uuid>$NEW_UUID</uuid>|" "$XML_FILE"
sed -i -E "s|<mac address=['\"][^'\"]*['\"]|<mac address='$NEW_MAC'|" "$XML_FILE"
sed -i -E "s|<serial>[^<]*</serial>|<serial>$NEW_DISK_SN</serial>|" "$XML_FILE"
sed -i -E "s|(type=1,[^'\"]*serial=)[A-Z0-9]+|\1$NEW_SYS_SN|" "$XML_FILE"
sed -i -E "s|(type=2,[^'\"]*serial=)[A-Z0-9]+|\1$NEW_BOARD_SN|" "$XML_FILE"
sed -i -E "s|(type=3,[^'\"]*serial=)[A-Z0-9]+|\1$NEW_CHASSIS_SN|" "$XML_FILE"
sed -i -E "s|(type=17,[^'\"]*serial=)[A-Z0-9]+|\1$NEW_MEM_SN|" "$XML_FILE"
sed -i -E "s|(type=1,[^'\"]*uuid=)[0-9a-fA-F-]+|\1$NEW_UUID|" "$XML_FILE"

echo "=== 验证已应用 ==="
echo -n "  UUID:       " ; grep -oE '<uuid>[^<]+' "$XML_FILE" | head -1 | sed 's/<uuid>//'
echo -n "  MAC:        " ; grep -oE 'mac address=.[[:xdigit:]:]+' "$XML_FILE" | head -1 | sed -E 's/mac address=.//;s/["'\'']//'
echo -n "  Disk SN:    " ; grep -oE '<serial>[^<]+' "$XML_FILE" | head -1 | sed 's/<serial>//'
echo -n "  Type 1 SN:  " ; grep -oE 'type=1,[^"'\'']*serial=[A-Z0-9]+' "$XML_FILE" | sed 's/.*serial=//' | head -1
echo -n "  Type 1 UUID:" ; grep -oE 'type=1,[^"'\'']*uuid=[0-9a-fA-F-]+' "$XML_FILE" | sed 's/.*uuid=//' | head -1
echo -n "  Type 2 SN:  " ; grep -oE 'type=2,[^"'\'']*serial=[A-Z0-9]+' "$XML_FILE" | sed 's/.*serial=//' | head -1
echo -n "  Type 3 SN:  " ; grep -oE 'type=3,[^"'\'']*serial=[A-Z0-9]+' "$XML_FILE" | sed 's/.*serial=//' | head -1
echo -n "  Type 17 SN: " ; grep -oE 'type=17,[^"'\'']*serial=[A-Z0-9]+' "$XML_FILE" | sed 's/.*serial=//' | head -1
echo ""

echo "重定义 VM（保留 NVRAM）..."
virsh undefine --keep-nvram "$VM_NAME" >/dev/null
virsh define "$XML_FILE" >/dev/null

echo ""
echo "=== 完成 ==="
echo "启动: virsh start $VM_NAME"
echo "RDP 转发: sudo vm-fwd"
echo ""
echo "提醒: MAC 变了以后 Windows 可能把网络位置打成公用，RDP 会被挡。"
echo "      VNC 隧道进系统后执行:"
echo "      Set-NetConnectionProfile -InterfaceAlias (Get-NetConnectionProfile).InterfaceAlias -NetworkCategory Private"
