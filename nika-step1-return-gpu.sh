#!/usr/bin/env bash
# step1: 删除 win10-nika，解开 vfio 锁，重启把显卡还给 nouveau / 笔记本屏幕
set -euo pipefail
if [[ "$(id -u)" -ne 0 ]]; then
  echo "run as root"
  exit 1
fi
export LIBVIRT_DEFAULT_URI=qemu:///system

mkdir -p /home/cc/nika-rebuild
if virsh dominfo win10-nika >/dev/null 2>&1; then
  virsh dumpxml win10-nika > /home/cc/nika-rebuild/win10-nika-live-before-delete.xml || true
  STATE=$(virsh domstate win10-nika || true)
  echo "VM state=$STATE"
  if [[ "$STATE" == "running" || "$STATE" == "paused" ]]; then
    echo "destroying running VM..."
    virsh destroy win10-nika || true
    sleep 2
  fi
  echo "undefine --nvram"
  virsh undefine win10-nika --nvram || virsh undefine win10-nika --keep-nvram || true
else
  echo "win10-nika already gone"
fi

echo "list:"
virsh list --all || true

if [[ -e /var/lib/libvirt/images/win10-disk.raw ]]; then
  echo "removing 240G disk..."
  rm -f /var/lib/libvirt/images/win10-disk.raw
  echo "disk removed"
else
  echo "disk already absent"
fi
ls -lh /var/lib/libvirt/images/win10-22h2.iso

echo "reattach GPU to host (best effort before reboot)"
virsh nodedev-reattach pci_0000_01_00_0 2>/dev/null || true
virsh nodedev-reattach pci_0000_01_00_1 2>/dev/null || true

echo "strip vfio-pci.ids from grub"
sed -i 's/ *vfio-pci.ids=10de:1be1,10de:10f0//g' /etc/default/grub
grep GRUB_CMDLINE /etc/default/grub

echo "remove nouveau blacklist"
rm -f /etc/modprobe.d/blacklist-nouveau.conf

echo "strip vfio from initramfs modules"
sed -i '/^vfio$/d;/^vfio_iommu_type1$/d;/^vfio_pci/d' /etc/initramfs-tools/modules
echo "----- modules after -----"
cat /etc/initramfs-tools/modules

KVER=$(uname -r)
echo "update-initramfs -u -k $KVER"
update-initramfs -u -k "$KVER"
update-grub

echo "GPU now:"
lspci -k -s 01:00 || true
sync
echo "STEP1 done. rebooting in 3s so nouveau can own the panel."
sleep 3
reboot
