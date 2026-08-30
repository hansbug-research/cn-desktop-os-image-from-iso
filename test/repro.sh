#!/bin/bash
# 可复现性凭据：重建一次，比对 tar 的 sha256，把实测结果写进 out/repro-evidence.txt。
# README §10 原先只有结论没有凭据，这个脚本负责生成凭据。
#
# 覆盖范围说明（别把话说大）：本脚本做的是**同一 builder 内连构两次**。
# 跨 builder（把 Dockerfile.builder 整个重建后再构）需要单独跑，结论另记。
set -u
ROOT=${ROOT:-/data/dosbuild}; BUILDER=${BUILDER:-dosb}
EV="$ROOT/out/repro-evidence.txt"
DISTROS=${1:-"kylin11 uos25"}
{
  echo "# 可复现性实测凭据"
  echo "# 生成时间: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "# 方法: 同一 builder 内连续构建两次，比对产物 tar 的 sha256"
  echo "# 注意: selfhost 路径（麒麟 V10）走 docker export/import，层时间戳每次不同，"
  echo "#       本脚本不覆盖它；其包集可复现性由 out/kylin10-*.manifest 承担。"
  echo
} > "$EV"
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
