#!/usr/bin/env bash
# 把飞牛 NAS 的 roms 共享（SMB，只读）挂到 .53 的 ~/mnt/fnos-roms，零 sudo：
#   bash ~/simulatee/deploy/nas-mount-setup.sh
# 前置：~/.secrets/fnos-smb.txt（user=…/pass=…，由主人自己写，见 SimulateEIOS docs/07）
#        ~/.local/bin/rclone（单文件二进制）
# 做的事：生成 rclone 远程配置（密码用 rclone obscure 写入 0600 的 rclone.conf）
#        → 安装/启动 systemd --user 服务 fnos-roms → 验证目录可读、统计 psp 文件数。
set -euo pipefail

SECRET="$HOME/.secrets/fnos-smb.txt"
NAS_HOST="${NAS_HOST:-192.168.1.169}"
MOUNT="$HOME/mnt/fnos-roms"
CONF_DIR="$HOME/.config/rclone"
export PATH="$HOME/.local/bin:$PATH"
export XDG_RUNTIME_DIR="/run/user/$(id -u)"

log() { printf '\n\033[36m==> %s\033[0m\n' "$*"; }

[ -s "$SECRET" ] || { echo "缺 $SECRET（user=…/pass=…）"; exit 1; }
command -v rclone >/dev/null || { echo "缺 ~/.local/bin/rclone"; exit 1; }
user=$(sed -n 's/^user=//p' "$SECRET"); pass=$(sed -n 's/^pass=//p' "$SECRET")
[ -n "$user" ] && [ -n "$pass" ] || { echo "$SECRET 里要有 user= 和 pass="; exit 1; }

log "rclone 远程 fnos → smb://$NAS_HOST（密码经 rclone obscure 写入 0600 的配置）"
mkdir -p "$CONF_DIR" "$MOUNT"; chmod 700 "$CONF_DIR"
obscured=$(printf '%s' "$pass" | rclone obscure -)
python3 - "$CONF_DIR/rclone.conf" "$NAS_HOST" "$user" "$obscured" <<'PY'
import configparser, pathlib, sys
path, host, user, obscured = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
cfg = configparser.ConfigParser()
if path.exists():
    cfg.read(path)
cfg["fnos"] = {"type": "smb", "host": host, "user": user, "pass": obscured}
with path.open("w") as f:
    cfg.write(f)
path.chmod(0o600)
PY
unset pass obscured

log "登录测试（列出共享根目录）"
rclone lsd fnos:roms --max-depth 1

log "安装并启动 fnos-roms.service"
mkdir -p "$HOME/.config/systemd/user"
cp "$(dirname "$0")/fnos-roms.service" "$HOME/.config/systemd/user/"
systemctl --user daemon-reload
systemctl --user enable fnos-roms >/dev/null
systemctl --user restart fnos-roms
for _ in $(seq 1 20); do sleep 1; mountpoint -q "$MOUNT" && break; done
mountpoint "$MOUNT"

log "验证"
echo "顶层目录: $(ls "$MOUNT" | tr '\n' ' ')"
if [ -d "$MOUNT/psp" ]; then
  echo "psp 文件数: $(find "$MOUNT/psp" -type f | wc -l)，总大小: $(du -sh "$MOUNT/psp" 2>/dev/null | cut -f1)"
  first=$(find "$MOUNT/psp" -type f \( -iname '*.iso' -o -iname '*.cso' -o -iname '*.pbp' \) | head -1)
  if [ -n "$first" ]; then
    echo "读取测试（前 64 MB）: $(dd if="$first" bs=1M count=64 2>&1 >/dev/null | tail -1)"
  fi
fi
echo "只读检查: $(touch "$MOUNT/.rw-test" 2>&1 >/dev/null | head -1 || true)"
systemctl --user is-active fnos-roms
