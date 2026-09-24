#!/usr/bin/env bash
# 在终端里不回显地把一个密钥写进 ~/.secrets/<名字>.txt（不进历史、不打印）：
#   ssh -t kiora bash ~/simulatee/deploy/set-secret.sh fnos-smb-rw  Retro2   # NAS 可写账号：user=/pass=
#   ssh -t kiora bash ~/simulatee/deploy/set-secret.sh psp-rar-password       # 单个口令：pass=
# 之后的脚本（挂载、解压）只引用这些文件；Windows 侧的会话从不看到内容。
set -euo pipefail
name="${1:?用法: set-secret.sh <名字> [用户名]}"
user="${2:-}"
F="$HOME/.secrets/$name.txt"
mkdir -p "$HOME/.secrets"; chmod 700 "$HOME/.secrets"
[ -r /dev/tty ] || { echo "需要一个终端（用 ssh -t 运行）" >&2; exit 2; }
if [ -s "$F" ]; then
  cp -a "$F" "$F.bak-$(date +%Y%m%d-%H%M%S)"; chmod 600 "$F".bak-*
  echo "已有旧文件，已备份。"
fi
[ -n "$user" ] && printf 'user: %s\n' "$user"
read -r -s -p 'secret (typing is hidden): ' pass < /dev/tty; echo
read -r -s -p 'type it again: ' pass2 < /dev/tty; echo
[ "$pass" = "$pass2" ] || { echo "两次不一致，没有写入。"; exit 1; }
[ -n "$pass" ] || { echo "为空，没有写入。"; exit 1; }
if [ -n "$user" ]; then printf 'user=%s\npass=%s\n' "$user" "$pass" > "$F"; else printf 'pass=%s\n' "$pass" > "$F"; fi
chmod 600 "$F"; unset pass pass2
echo "ok: $F ($(stat -c %s "$F") bytes)"
