#!/usr/bin/env bash
# 把飞牛 NAS 的 roms 共享（SMB，只读）挂到 .53 的 ~/mnt/fnos-roms，零 sudo：
#   bash ~/simulatee/deploy/nas-mount-setup.sh
# 前置：~/.secrets/fnos-smb.txt（user=…/pass=…，由主人自己用 deploy/set-nas-password.sh 写）
#        ~/.local/bin/rclone（单文件二进制）
# 做的事：生成 rclone 远程配置（密码用 rclone obscure 写入 0600 的 rclone.conf；共享名放在
#        别名远程 fnosroms 里，systemd 单元只写 fnosroms:）→ 安装/启动 systemd --user 服务
#        fnos-roms → 验证目录可读、统计 psp 文件数。
set -euo pipefail

SECRET="$HOME/.secrets/fnos-smb.txt"
NAS_HOST="${NAS_HOST:-192.168.1.169}"
# 飞牛把"团队文件"下的共享暴露为 团队文件-<名字>；挂的是它的根，psp 等系统目录在里面
NAS_SHARE="${NAS_SHARE:-团队文件-roms}"
MOUNT="$HOME/mnt/fnos-roms"
CONF_DIR="$HOME/.config/rclone"
export PATH="$HOME/.local/bin:$PATH"
export XDG_RUNTIME_DIR="/run/user/$(id -u)"

log() { printf '\n\033[36m==> %s\033[0m\n' "$*"; }

[ -s "$SECRET" ] || { echo "缺 $SECRET（user=…/pass=…）"; exit 1; }
command -v rclone >/dev/null || { echo "缺 ~/.local/bin/rclone"; exit 1; }
user=$(sed -n 's/^user=//p' "$SECRET"); pass=$(sed -n 's/^pass=//p' "$SECRET")
[ -n "$user" ] && [ -n "$pass" ] || { echo "$SECRET 里要有 user= 和 pass="; exit 1; }

log "rclone 远程 fnos → smb://$NAS_HOST，别名 fnosroms → fnos:$NAS_SHARE"
mkdir -p "$CONF_DIR" "$MOUNT"; chmod 700 "$CONF_DIR"
obscured=$(printf '%s' "$pass" | rclone obscure -)
CONF="$CONF_DIR/rclone.conf" HOST="$NAS_HOST" SMB_USER="$user" OBSCURED="$obscured" SHARE="$NAS_SHARE" python3 - <<'PY'
import configparser, os, pathlib
path = pathlib.Path(os.environ["CONF"])
cfg = configparser.ConfigParser()
if path.exists():
    cfg.read(path, encoding="utf-8")
cfg["fnos"] = {"type": "smb", "host": os.environ["HOST"], "user": os.environ["SMB_USER"], "pass": os.environ["OBSCURED"]}
cfg["fnosroms"] = {"type": "alias", "remote": "fnos:" + os.environ["SHARE"]}
with path.open("w", encoding="utf-8") as f:
    cfg.write(f)
path.chmod(0o600)
PY
unset pass obscured

log "登录测试（列出共享 $NAS_SHARE 的根目录）"
rclone lsd fnosroms: --max-depth 1

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
  echo "psp 扩展名分布: $(find "$MOUNT/psp" -type f | sed -n 's/.*\.\([A-Za-z0-9]*\)$/\1/p' | tr 'A-Z' 'a-z' | sort | uniq -c | sort -rn | head -5 | tr '\n' ' ')"
  first=$(find "$MOUNT/psp" -type f | head -1)
  if [ -n "$first" ]; then
    echo "读取测试（前 64 MB）: $(dd if="$first" bs=1M count=64 2>&1 >/dev/null | tail -1)"
  fi
fi
echo "只读检查: $( (touch "$MOUNT/.rw-test" 2>&1 || true) | head -1)"
systemctl --user is-active fnos-roms
