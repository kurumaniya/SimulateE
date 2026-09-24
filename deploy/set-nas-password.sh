#!/usr/bin/env bash
# 把飞牛 NAS 只读用户的密码写进 ~/.secrets/fnos-smb.txt（不回显、不进历史、不打印）：
#   ssh -t kiora bash ~/simulatee/deploy/set-nas-password.sh [用户名]
# 之后 deploy/nas-mount-setup.sh 只引用这个文件。
set -euo pipefail
F="$HOME/.secrets/fnos-smb.txt"
user="${1:-Retro}"
mkdir -p "$HOME/.secrets"; chmod 700 "$HOME/.secrets"
if [ ! -r /dev/tty ]; then
  echo "需要一个终端（用 ssh -t 运行）" >&2; exit 2
fi
if [ -s "$F" ]; then
  cp -a "$F" "$F.bak-$(date +%Y%m%d-%H%M%S)"; chmod 600 "$F".bak-*
  echo "已有旧文件，已备份。"
fi
printf 'NAS user: %s\n' "$user"
read -r -s -p 'NAS password (typing is hidden): ' pass < /dev/tty; echo
read -r -s -p 'Type it again: ' pass2 < /dev/tty; echo
[ "$pass" = "$pass2" ] || { echo "两次不一致，没有写入。"; exit 1; }
[ -n "$pass" ] || { echo "密码为空，没有写入。"; exit 1; }
printf 'user=%s\npass=%s\n' "$user" "$pass" > "$F"; chmod 600 "$F"
unset pass pass2
echo "ok: $F ($(stat -c %s "$F") bytes)"
