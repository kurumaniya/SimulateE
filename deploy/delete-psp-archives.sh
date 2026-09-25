#!/usr/bin/env bash
# 删掉 NAS 上 psp 目录里已经解压完的 .7z 压缩包（ISO 留下）。
#   bash ~/simulatee/deploy/delete-psp-archives.sh          # 只列出会删什么（试跑）
#   bash ~/simulatee/deploy/delete-psp-archives.sh --yes    # 真删，删完顺手删掉可写账号的密钥文件
# 前置：~/.secrets/fnos-smb-rw.txt（对共享有写权限的 NAS 账号，user=/pass=，由 deploy/set-secret.sh 写入）。
# 服务用的 Retro 账号是只读的，所以删除走另一个账号，不经过挂载点。
# 只删 psp 目录下扩展名为 .7z 的文件；每个包都要求同目录里已有解出来的 iso/cso/pbp，否则跳过并报出来。
set -euo pipefail
export PATH="$HOME/.local/bin:$PATH"
RW_SECRET="$HOME/.secrets/fnos-smb-rw.txt"
NAS_HOST="${NAS_HOST:-192.168.1.169}"
NAS_SHARE="${NAS_SHARE:-团队文件-roms}"
[ -s "$RW_SECRET" ] || { echo "缺 $RW_SECRET（先 ssh -t kiora bash ~/simulatee/deploy/set-secret.sh fnos-smb-rw <账号>）"; exit 1; }
rw_user=$(sed -n 's/^user=//p' "$RW_SECRET"); rw_pass=$(sed -n 's/^pass=//p' "$RW_SECRET")
export RCLONE_SMB_PASS; RCLONE_SMB_PASS="$(printf '%s' "$rw_pass" | rclone obscure -)"; unset rw_pass
REMOTE=":smb,host=$NAS_HOST,user=$rw_user:$NAS_SHARE/psp"

mapfile -t archives < <(rclone lsf -R --files-only --include '*.7z' "$REMOTE" | sort)
mapfile -t images < <(rclone lsf -R --files-only --include '*.{iso,cso,pbp,ISO,CSO,PBP}' "$REMOTE" | sort)
declare -A has_image=()
for f in "${images[@]}"; do has_image["$(dirname "$f")"]=1; done

todo=(); skip=()
for a in "${archives[@]}"; do
  if [ -n "${has_image[$(dirname "$a")]:-}" ]; then todo+=("$a"); else skip+=("$a"); fi
done
echo "压缩包 ${#archives[@]} 个；同目录已有镜像、可删 ${#todo[@]} 个；没找到镜像、保留 ${#skip[@]} 个"
for s in "${skip[@]}"; do echo "  [保留] $s"; done
[ "${#todo[@]}" -gt 0 ] || exit 0
if [ "${1:-}" != "--yes" ]; then
  printf '%s\n' "${todo[@]}" | head -5 | sed 's/^/  [将删] /'; echo "  …（试跑，加 --yes 才真删）"; exit 0
fi
printf '%s\n' "${todo[@]}" > "$HOME/.cache/psp-archives-to-delete.txt"
rclone delete "$REMOTE" --files-from "$HOME/.cache/psp-archives-to-delete.txt" --stats-one-line -v 2>&1 | tail -3
left=$(rclone lsf -R --files-only --include '*.7z' "$REMOTE" | wc -l)
echo "删除完成，剩余 .7z：$left"
rm -f "$HOME/.cache/psp-archives-to-delete.txt"
shred -u "$RW_SECRET" 2>/dev/null || rm -f "$RW_SECRET"
echo "已删除 $RW_SECRET"
