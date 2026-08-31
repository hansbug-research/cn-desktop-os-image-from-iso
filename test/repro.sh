#!/bin/bash
# 可复现性凭据：重建一次，比对 tar 的 sha256，把实测结果写进 out/repro-evidence.txt。
# report.md §8（可复现性） 原先只有结论没有凭据，这个脚本负责生成凭据。
#
# 覆盖范围说明（别把话说大）：本脚本做的是**同一 builder 内连构两次**。
# 跨 builder（把 Dockerfile.builder 整个重建后再构）需要单独跑，结论另记。
set -u
mkdir -p "${ROOT:-$(cd "$(dirname "$0")/.." && pwd)}/logs"   # 无此目录时重定向失败会被误报成「哈希漂移」
ROOT=${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)}   # 默认取仓库根，换机器无需改脚本
BUILDER=${BUILDER:-dosb}
EV="$ROOT/out/repro-evidence.txt"
. "$ROOT/lib/subjects.sh"      # ALL_DIDS / METHOD_OF[]，唯一真源 config/subjects.json
# 默认覆盖范围**从被试清单推导**，不写死：凡走 make_tarball 归一时间戳的路径
# （mmdebstrap / slice / rpmmedia）都该纳入实测；selfhost 走 docker export/import，
# 层时间戳每次不同，逐位复现无从谈起，由 manifest 的包集可复现性承担。
# 写死清单的后果是新增被试后它静默不被测，而凭据文件看着照样完整。
_repro_dids=""
for _d in $ALL_DIDS; do
  case "$(m_of "$_d")" in selfhost) ;; *) _repro_dids="$_repro_dids $_d" ;; esac
done
DISTROS=${1:-$_repro_dids}
{
  echo "# 可复现性实测凭据"
  echo "# 生成时间: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "# 方法: 同一 builder 内连续构建两次，比对产物 tar 的 sha256"
  echo "# 注意: selfhost 路径（麒麟 V10 与凝思）走 docker export/import，层时间戳每次"
  echo "#       不同，本脚本不覆盖；其包集可复现性由各自的 *.manifest 承担。"
  echo "# 覆盖的被试:$DISTROS"
  echo
} > "$EV"
# 互斥检查：本脚本要连构两次，与任何并发的构建或门禁争用同一个 build/ 工作目录。
# §9.2 记过一次 tar_mtab 假失败（verify 读 tar 时并发重建覆写了它），这次又踩了 ——
# repro 跑第二次构建时我并行跑着 d2 采集与 verify，`rm -rf` 撞上正被读取的目录，
# 报 `Directory not empty`，构建被判失败而实际退出码是 0。
# 纪律记录过、引用过，但没有机制强制，所以在这里加一道。
for _p in build.sh build-selfhost.sh verify.sh sbom.sh cve.sh collect_d2_our_images.py; do
  if pgrep -f "[/]$_p" >/dev/null 2>&1; then
    echo "!! 检测到并发任务 $_p —— repro 必须独占 build/ 与 out/，先等它结束" >&2
    exit 1
  fi
done

RC=0
for d in $DISTROS; do
  declare -A first
  for t in micro base devel; do first[$t]=$(sha256sum "$ROOT/out/$d-$t.tar" 2>/dev/null | cut -d' ' -f1); done
  echo "  [$d] 第二次构建…"
  docker exec "$BUILDER" bash -c "unset http_proxy https_proxy; umask 022; ROOT=/w /w/build/build.sh $d micro base devel" \
    > "$ROOT/logs/repro-$d.log" 2>&1 || { echo "  ✗ $d 重建失败"; RC=1; continue; }
  for t in micro base devel; do
    second=$(sha256sum "$ROOT/out/$d-$t.tar" 2>/dev/null | cut -d' ' -f1)
    if [ "${first[$t]}" = "$second" ] && [ -n "$second" ]; then
      echo "  ✅ $d-$t  ${second:0:16}…（两次一致）"
      printf '%-16s 一致  sha256=%s\n' "$d-$t" "$second" >> "$EV"
    else
      echo "  ✗ $d-$t 哈希漂: ${first[$t]:0:16}… → ${second:0:16}…"
      printf '%-16s 不一致 first=%s second=%s\n' "$d-$t" "${first[$t]}" "$second" >> "$EV"
      RC=1
    fi
  done
  unset first
done
echo; echo "凭据已写入 $EV"
[ "$RC" = 0 ] && echo "✅ 覆盖到的路径全部逐位可复现" || echo "❌ 有产物哈希漂移"
exit $RC
