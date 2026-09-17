#!/usr/bin/env bash
set -euo pipefail
if [[ "$(id -u)" -ne 0 ]]; then
    echo "run as root: sudo $0"
    exit 1
fi

ROOT="$(cd "$(dirname "$0")" && pwd)"
DEST=/usr/local/lib/vmctl
BIN=/usr/local/bin/vmctl

find "$ROOT" -type f \( -name '*.py' -o -name '*.sh' -o -name 'qemu-hook' -o -name '*.html' -o -name '*.service' \) -exec sed -i 's/\r$//' {} +

rm -rf "$DEST"
install -d "$DEST" "$DEST/contrib" /var/lib/vmctl /etc/libvirt/hooks
install -m 0644 "$ROOT"/*.py "$DEST/"
install -m 0644 "$ROOT/ui.html" "$DEST/ui.html"
install -m 0644 "$ROOT/contrib/vmctl.service" /etc/systemd/system/vmctl.service
install -m 0755 "$ROOT/contrib/qemu-hook" /etc/libvirt/hooks/qemu

cat > "$BIN" <<'EOF'
#!/usr/bin/env python3
import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path("/usr/local/lib")))
runpy.run_module("vmctl", run_name="__main__")
EOF
chmod 0755 "$BIN"

python3 -c "import libvirt, vmctl" 2>/dev/null || PYTHONPATH=/usr/local/lib python3 -c "import vmctl, libvirt; print('ok', vmctl.__version__)"

systemctl daemon-reload
systemctl enable --now vmctl.service

echo
echo "installed. CLI: vmctl list"
echo "UI: http://$(ip -4 -o addr show scope global | awk '{print $4}' | head -1 | cut -d/ -f1):8787/"
echo "systemd: systemctl status vmctl"
