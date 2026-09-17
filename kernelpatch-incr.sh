#!/usr/bin/env bash
# Incremental KVM userpatch rebuild. Does not modify kernelpatch619.sh.
# Reverse the currently applied intel/amd619.mypatch, apply the repo copy,
# then make -j bindeb-pkg on the existing linux-src-git (keeps .o).
#
# Usage:
#   sudo -E ./kernelpatch-incr.sh           # backup + rebuild, do not dpkg
#   sudo -E ./kernelpatch-incr.sh -y
#   sudo -E ./kernelpatch-incr.sh --force   # rebuild even if patch unchanged
#   sudo -E ./kernelpatch-incr.sh --backup-only
#   sudo -E ./kernelpatch-incr.sh --install # after a successful rebuild, dpkg
#
# Need: linux-tkg/linux-src-git from a finished kernelpatch619.sh, with .config.

set -euo pipefail

if [ "$EUID" != 0 ]; then
    faillock --reset
    sudo -E "$0" "$@"
    exit $?
fi

YES=0
FORCE=0
BACKUP_ONLY=0
INSTALL=0
for arg in "$@"; do
    case "$arg" in
        -y|--yes) YES=1 ;;
        --force) FORCE=1 ;;
        --backup-only) BACKUP_ONLY=1 ;;
        --install) INSTALL=1 ;;
        -h|--help)
            echo "Usage: $0 [-y] [--force] [--backup-only] [--install]"
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

TKG_DIR="$ROOT/linux-tkg"
SRC="$TKG_DIR/linux-src-git"
DEBS="$TKG_DIR/DEBS"
UP_DIR="$TKG_DIR/linux619-tkg-userpatches"
STAMP="$(date +%Y%m%d-%H%M%S)"
BAK_DIR="/home/cc/nika-rebuild/kernel-bak-$STAMP"
APPLIED="$UP_DIR/.applied.patch"
KREL="6.19.14-tkg-eevdf"
MAKE_FLAGS=(KCFLAGS="-Wno-error=discarded-qualifiers" HOSTCFLAGS="-Wno-error=discarded-qualifiers")

cpu_vendor="$(awk -F: '/vendor_id/{gsub(/^[ \t]+/, "", $2); print $2; exit}' /proc/cpuinfo)"
if [[ "$cpu_vendor" == "AuthenticAMD" ]]; then
    PATCH_SRC="$ROOT/amd619.mypatch"
    PATCH_NAME="amd619.mypatch"
else
    PATCH_SRC="$ROOT/intel619.mypatch"
    PATCH_NAME="intel619.mypatch"
fi
PATCH_DST="$UP_DIR/$PATCH_NAME"

if [[ ! -d "$SRC" || ! -f "$SRC/.config" ]]; then
    echo "ERROR: $SRC/.config missing. Run ./kernelpatch619.sh once (full build)."
    exit 1
fi
if [[ ! -f "$PATCH_SRC" ]]; then
    echo "ERROR: $PATCH_SRC not found"
    exit 1
fi
mkdir -p "$UP_DIR" "$DEBS" "$BAK_DIR"

backup_now() {
    echo "备份 → $BAK_DIR"
    mkdir -p "$BAK_DIR/boot" "$BAK_DIR/debs" "$BAK_DIR/patch"
    for f in /boot/vmlinuz-"$KREL" /boot/initrd.img-"$KREL" /boot/System.map-"$KREL" /boot/config-"$KREL"; do
        [[ -e "$f" ]] && cp -a "$f" "$BAK_DIR/boot/"
    done
    if [[ -d "$DEBS" ]]; then
        cp -a "$DEBS"/linux-image-"$KREL"_*.deb "$BAK_DIR/debs/" 2>/dev/null || true
        cp -a "$DEBS"/linux-headers-"$KREL"_*.deb "$BAK_DIR/debs/" 2>/dev/null || true
    fi
    [[ -f "$PATCH_DST" ]] && cp -a "$PATCH_DST" "$BAK_DIR/patch/"
    [[ -f "$APPLIED" ]] && cp -a "$APPLIED" "$BAK_DIR/patch/applied.patch"
    echo "  boot: $(ls "$BAK_DIR/boot" 2>/dev/null | tr '\n' ' ')"
    echo "  debs: $(ls "$BAK_DIR/debs" 2>/dev/null | tr '\n' ' ')"
}

same_patch() {
    [[ -f "$APPLIED" ]] && cmp -s "$PATCH_SRC" "$APPLIED"
}

if [[ "$BACKUP_ONLY" == 1 ]]; then
    backup_now
    echo "只备份，不编译。"
    echo "回滚: dpkg -i $BAK_DIR/debs/linux-image-*.deb $BAK_DIR/debs/linux-headers-*.deb && reboot"
    exit 0
fi

if [[ ! -f "$APPLIED" && -f "$PATCH_DST" ]]; then
    cp -f "$PATCH_DST" "$APPLIED"
    echo "记下当前 userpatches/$PATCH_NAME 为已应用（上次全量编）"
fi

backup_now

if same_patch && [[ "$FORCE" != 1 ]]; then
    echo "仓库 $PATCH_NAME 和当前已应用的补丁相同，跳过编译。"
    echo "要强制重编: $0 --force"
    if [[ "$INSTALL" == 1 ]]; then
        echo "dpkg -i 现有 DEBS ..."
        DEBIAN_FRONTEND=noninteractive dpkg -i "$DEBS"/linux-image-"$KREL"_*.deb "$DEBS"/linux-headers-"$KREL"_*.deb
        echo "已安装。uname 仍是旧内核，直到 reboot。"
        exit 0
    fi
    echo "要安装已有 DEBS: $0 --install"
    exit 0
fi

if [[ "$YES" != 1 ]]; then
    echo "将 reverse 旧 userpatch，打上 $PATCH_SRC，然后 make -j$(nproc) bindeb-pkg"
    echo "不会 dpkg / 不会 reboot。"
    read -r -p "Continue? [y/N] " ans
    [[ "$ans" =~ ^[Yy]$ ]] || exit 0
fi

mkdir -p "$UP_DIR"
if [[ -f "$APPLIED" ]]; then
    echo "reverse 已应用补丁..."
    if ! patch -d "$SRC" -Np1 -R --dry-run < "$APPLIED" >/tmp/kpatch-incr-rev.dry 2>&1; then
        echo "ERROR: reverse dry-run 失败，树和 .applied.patch 对不上。别硬打。"
        cat /tmp/kpatch-incr-rev.dry
        exit 1
    fi
    patch -d "$SRC" -Np1 -R < "$APPLIED"
fi

cp -f "$PATCH_SRC" "$PATCH_DST"
sed -i 's/\r$//' "$PATCH_DST"

echo "apply $PATCH_DST ..."
if ! patch -d "$SRC" -Np1 --dry-run < "$PATCH_DST" >/tmp/kpatch-incr-fwd.dry 2>&1; then
    echo "ERROR: 新补丁 dry-run 失败。正在尝试把旧补丁打回去..."
    if [[ -f "$APPLIED" ]]; then
        patch -d "$SRC" -Np1 < "$APPLIED" || true
    fi
    cat /tmp/kpatch-incr-fwd.dry
    exit 1
fi
patch -d "$SRC" -Np1 < "$PATCH_DST"
cp -f "$PATCH_DST" "$APPLIED"

echo "make -j$(nproc) bindeb-pkg LOCALVERSION=-tkg-eevdf"
cd "$SRC"
make "${MAKE_FLAGS[@]}" -j"$(nproc)" bindeb-pkg LOCALVERSION=-tkg-eevdf
cd "$ROOT"

echo "拷贝 deb → $DEBS"
mkdir -p "$DEBS"
shopt -s nullglob
for deb in "$TKG_DIR"/linux-image-"$KREL"_*.deb "$TKG_DIR"/linux-headers-"$KREL"_*.deb "$TKG_DIR"/linux-libc-dev_*.deb; do
    [[ -f "$deb" ]] || continue
    case "$deb" in *-dbg_*) continue ;; esac
    cp -a "$deb" "$DEBS/"
done
ls -lt --time-style=long-iso "$DEBS" | head

echo
echo "=== 编译完成，未安装 ==="
echo "备份: $BAK_DIR"
echo "安装: sudo dpkg -i $DEBS/linux-image-${KREL}_*.deb $DEBS/linux-headers-${KREL}_*.deb"
echo "或:   sudo -E $0 --install"
echo "回滚: sudo dpkg -i $BAK_DIR/debs/linux-image-*.deb $BAK_DIR/debs/linux-headers-*.deb && sudo reboot"
echo "生效必须 reboot。先关虚拟机。"

if [[ "$INSTALL" == 1 ]]; then
    echo "dpkg -i ..."
    DEBIAN_FRONTEND=noninteractive dpkg -i "$DEBS"/linux-image-"$KREL"_*.deb "$DEBS"/linux-headers-"$KREL"_*.deb
    echo "已安装。uname 仍是旧内核，直到 reboot。"
fi
