#!/usr/bin/env bash
# 在 .53 上把 NAS 里的加密 RAR（扩展名 .7z）解成 ISO，写回 NAS 同目录。可反复运行（已解过的跳过）。
#   nohup bash ~/simulatee/deploy/extract-psp-archives.sh > ~/simulatee-extract.log 2>&1 &
# 前置：
#   ~/.secrets/fnos-smb-rw.txt      对共享有写权限的 NAS 账号（user=/pass=，deploy/set-secret.sh 写）
#   ~/.secrets/psp-rar-password.txt 压缩包口令（pass=）
#   ~/.local/bin/unrar              rarlab 的 unrar（支持 RAR5 + 口令）
# 读走只读挂载 ~/mnt/fnos-roms（服务用的那份不动），写走临时的可写挂载 ~/mnt/fnos-roms-rw，
# 解完自动卸载可写挂载。每个包解到它自己所在的目录，压缩包本身不删（省空间要删由主人决定）。
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
SRC="$HOME/mnt/fnos-roms/psp"
RW="$HOME/mnt/fnos-roms-rw"
RW_SECRET="$HOME/.secrets/fnos-smb-rw.txt"
RAR_SECRET="$HOME/.secrets/psp-rar-password.txt"
NAS_HOST="${NAS_HOST:-192.168.1.169}"
NAS_SHARE="${NAS_SHARE:-团队文件-roms}"

for f in "$RW_SECRET" "$RAR_SECRET"; do [ -s "$f" ] || { echo "缺 $f"; exit 1; }; done
command -v unrar >/dev/null || { echo "缺 ~/.local/bin/unrar"; exit 1; }
mountpoint -q "$SRC/.." || { echo "只读挂载 $SRC 不在"; exit 1; }

rw_user=$(sed -n 's/^user=//p' "$RW_SECRET"); rw_pass=$(sed -n 's/^pass=//p' "$RW_SECRET")
rar_pass=$(sed -n 's/^pass=//p' "$RAR_SECRET")
mkdir -p "$RW"
cleanup() { fusermount3 -uz "$RW" 2>/dev/null || true; }
trap cleanup EXIT
if ! mountpoint -q "$RW"; then
  RCLONE_SMB_PASS="$(printf '%s' "$rw_pass" | rclone obscure -)" \
    rclone mount ":smb,host=$NAS_HOST,user=$rw_user:$NAS_SHARE" "$RW" \
      --vfs-cache-mode writes --daemon --log-level NOTICE
  for _ in $(seq 1 20); do sleep 1; mountpoint -q "$RW" && break; done
  mountpoint "$RW"
fi
unset rw_pass

total=0; done_n=0; skipped=0; failed=0
mapfile -t archives < <(find "$SRC" -type f -name '*.7z' | sort)
total=${#archives[@]}
echo "[$(date +%F' '%T)] $total 个压缩包"
for a in "${archives[@]}"; do
  rel="${a#"$SRC"/}"; dir="$RW/psp/$(dirname "$rel")"; mkdir -p "$dir"
  # 已解过：同目录里已有非压缩包文件且名字前缀相同（PSPCH001.7z -> PSPCH001*.iso 之类）——
  # 更稳的判定是 unrar l 列出的文件名都已存在
  listed=$(unrar lb -p"$rar_pass" "$a" 2>/dev/null || true)
  if [ -z "$listed" ]; then echo "[skip] 列不出内容（口令错？）: $rel"; failed=$((failed+1)); continue; fi
  all_present=1
  while IFS= read -r inner; do [ -e "$dir/$inner" ] || { all_present=0; break; }; done <<< "$listed"
  if [ "$all_present" = 1 ]; then skipped=$((skipped+1)); continue; fi
  echo "[$(date +%T)] 解压 $rel -> $(dirname "$rel")/"
  if unrar x -o+ -y -idq -p"$rar_pass" "$a" "$dir/"; then
    done_n=$((done_n+1))
  else
    echo "[fail] $rel"; failed=$((failed+1))
  fi
done
unset rar_pass
echo "[$(date +%F' '%T)] 完成：解压 $done_n，已存在跳过 $skipped，失败 $failed，共 $total"
