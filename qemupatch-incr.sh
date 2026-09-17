#!/usr/bin/env bash
# Incremental QEMU rebuild. Does not modify qemupatch.sh.
# Restores only files that qemupatch.sh patches, keeps qemu/build, skips configure.
#
# Usage:
#   sudo -E ./qemupatch-incr.sh
#   sudo -E ./qemupatch-incr.sh -y
#   sudo -E ./qemupatch-incr.sh --new-ids -y
#
# Need an existing qemu/build (run qemupatch.sh once) and qemubackup or qemu11backup.

set -euo pipefail

if [ "$EUID" != 0 ]; then
    faillock --reset
    sudo -E "$0" "$@"
    exit $?
fi

YES=0
NEW_IDS=0
for arg in "$@"; do
  case "$arg" in
    -y|--yes) YES=1 ;;
    --new-ids) NEW_IDS=1 ;;
    -h|--help)
      echo "Usage: $0 [-y] [--new-ids]"
      exit 0
      ;;
    *)
      echo "Unknown arg: $arg"
      exit 1
      ;;
  esac
done

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -f qemupatch.sh ]]; then
  echo "qemupatch.sh not found in $ROOT"
  exit 1
fi
if [[ ! -d qemu/build ]]; then
  echo "qemu/build not found. Run ./qemupatch.sh once for the full build."
  exit 1
fi
if [[ ! -f qemu/build/build.ninja && ! -f qemu/build/Makefile ]]; then
  echo "qemu/build has no build.ninja/Makefile. Run ./qemupatch.sh once."
  exit 1
fi
if [[ ! -d qemubackup && ! -d qemu11backup ]]; then
  echo "Need qemubackup or qemu11backup (clean QEMU sources)."
  exit 1
fi

if [[ "$NEW_IDS" == 1 ]]; then
  if [[ -f vars.sh ]]; then
    cp -a vars.sh "vars.sh.bak-$(date +%Y%m%d-%H%M%S)"
    rm -f vars.sh
    echo "Removed vars.sh (backup kept). Run ovmfpatch.sh after this build."
  fi
fi

TMP="$(mktemp -t qemupatch-incr.XXXXXX.sh)"
trap 'rm -f "$TMP"' EXIT

python3 - "$ROOT/qemupatch.sh" "$TMP" "$YES" <<'PY'
import re
import sys

src_path, dst_path, yes = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
text = open(src_path, "r", encoding="utf-8", newline="").read().replace("\r\n", "\n")

restore_fn = r'''
qemupatch_incr_restore() {
  local backup=""
  if [[ -d qemubackup ]]; then
    backup=qemubackup
  elif [[ -d qemu11backup ]]; then
    backup=qemu11backup
  else
    echo "qemupatch-incr: no qemubackup or qemu11backup"
    exit 1
  fi
  local qemu_root="$(pwd)/qemu"
  local bak_root="$(pwd)/$backup"
  echo "qemupatch-incr: restore patched sources from $backup (keep qemu/build)"
  local var dest rel src n=0
  for var in $(compgen -v); do
    [[ "$var" =~ ^(file_|header_) ]] || continue
    dest="${!var}"
    [[ "$dest" == "$qemu_root"/* ]] || continue
    rel="${dest#"$qemu_root"/}"
    src="$bak_root/$rel"
    if [[ -f "$src" ]]; then
      mkdir -p "$(dirname "$dest")"
      cp -f "$src" "$dest"
      n=$((n + 1))
    fi
  done
  echo "qemupatch-incr: restored $n files"
}
'''

sudo_end = '''if [ "$EUID" != 0 ]; then
    faillock --reset
    sudo -E "$0" "$@"
    exit $?
fi
'''
if sudo_end not in text:
    print("qemupatch-incr: sudo block not found in qemupatch.sh", file=sys.stderr)
    sys.exit(1)
text = text.replace(sudo_end, sudo_end + restore_fn, 1)

clone = '''if [[ ! -d qemubackup ]]; then
  echo -e "$(pwd)/\\e[1mqemubackup\\e[0m does not exist, cloning..."
  git clone --single-branch --branch stable-11.0 https://github.com/qemu/qemu.git qemubackup
else
  echo -e "$(pwd)/\\e[1mqemubackup\\e[0m found."
fi
'''
clone_new = '''if [[ ! -d qemubackup && ! -d qemu11backup ]]; then
  echo "qemupatch-incr: need qemubackup or qemu11backup"
  exit 1
fi
if [[ -d qemubackup ]]; then
  echo -e "$(pwd)/\\e[1mqemubackup\\e[0m found (incremental, no clone)."
else
  echo -e "$(pwd)/\\e[1mqemu11backup\\e[0m found (incremental, no clone)."
fi
'''
if clone not in text:
    print("qemupatch-incr: clone block not found in qemupatch.sh", file=sys.stderr)
    sys.exit(1)
text = text.replace(clone, clone_new, 1)

if "cp -fr qemubackup/. qemu" not in text:
    print("qemupatch-incr: cp backup line not found", file=sys.stderr)
    sys.exit(1)
text = text.replace("cp -fr qemubackup/. qemu", "qemupatch_incr_restore", 1)

configure = '''cd qemu
./configure --target-list=x86_64-softmmu
cd build
make -j
'''
configure_new = '''cd qemu
if [[ -f build/build.ninja || -f build/Makefile ]]; then
  echo "qemupatch-incr: skip configure, reuse $(pwd)/build"
else
  echo "qemupatch-incr: no existing build, running configure"
  ./configure --target-list=x86_64-softmmu
fi
cd build
make -j$(nproc)
'''
if configure not in text:
    print("qemupatch-incr: configure/make block not found", file=sys.stderr)
    sys.exit(1)
text = text.replace(configure, configure_new, 1)

if yes:
    read_line = "read -p $'Continue? [y/\\e[1mN\\e[0m]> ' -n 1 -r"
    if read_line not in text:
        print("qemupatch-incr: continue prompt not found", file=sys.stderr)
        sys.exit(1)
    text = text.replace(read_line, "REPLY=y", 1)

if "git clone" in text:
    print("qemupatch-incr: git clone still present after transform", file=sys.stderr)
    sys.exit(1)
if "qemupatch_incr_restore" not in text:
    print("qemupatch-incr: restore function not injected", file=sys.stderr)
    sys.exit(1)

open(dst_path, "w", encoding="utf-8", newline="\n").write(text)
print("qemupatch-incr: wrote transformed script")
PY

chmod +x "$TMP"
echo "qemupatch-incr: running patched copy of qemupatch.sh"
bash "$TMP"
echo "qemupatch-incr: done"
if [[ "$NEW_IDS" == 1 ]]; then
  echo "PCI IDs changed. Run: sudo -E ./ovmfpatch.sh"
fi
