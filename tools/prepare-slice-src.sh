#!/bin/bash
# 准备切片源：抽 squashfs -> 校验 sha256 -> unsquashfs -> 落一个带指纹的标记。
# 之前 SQUASHFS_SHA256 全仓无人引用，解包结果与那个哈希之间没有任何绑定——
# 目录被改过、被换过、上次只解了一半，构建都会照常进行。
set -eu
ROOT="${ROOT:-/w}"; . "$ROOT/lib/common.sh"
DID=$1
. "$ROOT/distros/$DID.conf"
[ -n "${SRC_ROOTFS:-}" ] || die "conf 里缺 SRC_ROOTFS"

python3 "$ROOT/tools/fetch-squashfs.py" "$DID" "$ROOT"
SQ="$ROOT/iso/$DID-filesystem.squashfs"
FP="${SQUASHFS_SHA256:-$(sha256sum "$SQ" | cut -d' ' -f1)}"

if [ "$(cat "$SRC_ROOTFS/.verified" 2>/dev/null)" = "$FP" ]; then
  log "[$DID] 切片源已就绪且指纹一致（$(du -sh "$SRC_ROOTFS" | cut -f1)）"
  exit 0
fi

log "[$DID] unsquashfs（须以 root 跑才能保住属主；xattr 在 rootless 下写不了，见 report.md §5（精简与容器化改造））"
rm -rf "$SRC_ROOTFS"
unsquashfs -no-progress -no-xattrs -d "$SRC_ROOTFS" "$SQ" 2>&1 | tail -2 || true
[ -d "$SRC_ROOTFS/usr" ] || die "解包结果不完整"
printf '%s' "$FP" > "$SRC_ROOTFS/.verified"
log "[$DID] 切片源就绪 $(du -sh "$SRC_ROOTFS" | cut -f1)，指纹 ${FP:0:16}…"
