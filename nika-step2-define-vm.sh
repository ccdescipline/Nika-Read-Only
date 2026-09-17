#!/usr/bin/env bash
# step2: 50G 新盘 + 无直通 XML + rotate + 启动安装
set -euo pipefail
if [[ "$(id -u)" -ne 0 ]]; then
  echo "run as root"
  exit 1
fi
export LIBVIRT_DEFAULT_URI=qemu:///system

ISO=/var/lib/libvirt/images/win10-22h2.iso
DISK=/var/lib/libvirt/images/win10-disk.raw
XML=/home/cc/nika-rebuild/win10-nika-nogpu.xml
ROTATE=/home/cc/nika-rebuild/vm-rotate-identity.v2.sh

[[ -f "$ISO" ]] || { echo "missing ISO $ISO"; exit 1; }
[[ -f "$XML" ]] || { echo "missing XML $XML"; exit 1; }

if virsh dominfo win10-nika >/dev/null 2>&1; then
  echo "ERROR: win10-nika still exists. finish step1 first."
  virsh list --all
  exit 1
fi

if [[ -e "$DISK" ]]; then
  echo "ERROR: $DISK exists. refusing to clobber."
  ls -lh "$DISK"
  exit 1
fi

echo "create 50G raw disk"
qemu-img create -f raw "$DISK" 50G
chown libvirt-qemu:kvm "$DISK"
chmod 640 "$DISK"
ls -lh "$DISK"

install -m 0755 "$ROTATE" /usr/local/bin/vm-rotate
# keep vm-fwd as-is if present

echo "define domain"
virsh define "$XML"

echo "rotate identity"
/usr/local/bin/vm-rotate win10-nika

echo "start"
virsh start win10-nika
sleep 2
virsh list --all
virsh dumpxml win10-nika | grep -E 'uuid|mac address|serial>|hostdev|win10-22h2|boot order'
virsh domdisplay win10-nika
echo "STEP2 done. VNC: ssh -N -L 5900:127.0.0.1:5900 cc@宿主机  then connect 127.0.0.1:5900"
