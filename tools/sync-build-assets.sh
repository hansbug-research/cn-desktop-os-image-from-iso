#!/bin/bash
# 构建资产在两处存在：本仓库（发布物）与 /data/dosbuild（构建工作区）。
# 手工 cp 出过两次事故，方向都记在 report.md §9.2：
#   ① dosbuild → 本仓库，覆盖掉本仓库已接单一真源的 test/run-capabilities.sh；
#   ② 本仓库 → dosbuild，覆盖掉 dosbuild 里刚加的 chkconfig 与 RPM_DB_BACKEND，
#      导致 rpm -qa 归零、闭包少 4 个包。
# 把教训写进文档没能阻止第二次复发，所以改成脚本：方向固定、先报差异、要确认。
# 不能改成符号链接 —— builder 容器只挂了 dosbuild，指向本仓库的链接在容器内悬空。
#
# ⚠️ 纪律：**所有改动只在本仓库做，只用 to-work 方向同步。** dosbuild 是只读的执行
# 环境。四次事故都源于「在两个目录之间来回改」：在 dosbuild 改完，下一次 to-repo
# 同步就把改动用本仓库的旧版覆盖回去，而脚本报「已同步 N 项」看着像成功。
# to-repo 只在一种情况下用：确认 dosbuild 侧有本仓库没有的改动需要收回。
set -eu
REPO=${REPO:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)}
WORK=${WORK:-/data/dosbuild}
DIR=${1:?用法: sync-build-assets.sh <to-work|to-repo> [--apply]}
APPLY=${2:-}
case $DIR in
  to-work) SRC=$REPO; DST=$WORK ;;
  to-repo) SRC=$WORK; DST=$REPO ;;
  *) echo "方向只能是 to-work 或 to-repo"; exit 1 ;;
esac
# 资产按**文件**列，不按目录：build/ 里既有脚本，也有构建产生的 rootfs 工作目录
# （kylinsec6-base 之类，几百 MB），整目录同步既慢又危险。tools/ 同理有 __pycache__。
FILES="distros lib Dockerfile.builder Makefile
  config/subjects.json
  build/build.sh build/build-selfhost.sh build/selfhost-inner.sh build/customize.sh build/setup.sh build/import.sh
  tools/slice.py tools/rpmmedia.py tools/rpmslice.py tools/restore-alternatives.py
  tools/mk-localrepo.sh tools/gen-manifest.sh tools/render-capabilities.py tools/prepare-slice-src.sh
  test/verify.sh test/inner-checks.sh test/capabilities.sh test/run-capabilities.sh
  test/mutation.sh test/mutation-docs.sh test/digest-chain.sh test/sbom.sh test/cve.sh test/repro.sh
  test/fixtures"
echo "方向: $SRC → $DST"
n=0
for f in $FILES; do
  [ -e "$SRC/$f" ] || continue
  mkdir -p "$(dirname "$DST/$f")"
  if ! diff -rq "$SRC/$f" "$DST/$f" >/dev/null 2>&1; then
    echo "  差异: $f"
    # 打印双向修改时间：脚本只报「有差异」时，人容易不看内容就 --apply，
    # 结果用旧版覆盖新版（实测发生过，Makefile 的 target 被这么抹掉一次）。
    # 让「哪边新」直接可见，而不是靠人记得。
    if [ -f "$SRC/$f" ] && [ -f "$DST/$f" ]; then
      printf '      源 %s   目标 %s%s\n' \
        "$(date -r "$SRC/$f" '+%m-%d %H:%M')" "$(date -r "$DST/$f" '+%m-%d %H:%M')" \
        "$([ "$SRC/$f" -ot "$DST/$f" ] && echo '   ⚠ 目标更新，方向可能反了')"
    fi
    diff -rq "$SRC/$f" "$DST/$f" 2>&1 | sed 's/^/      /' | head -8
    n=$((n+1))
  fi
done
[ "$n" = 0 ] && { echo "无差异"; exit 0; }
if [ "$APPLY" != "--apply" ]; then
  echo "以上 $n 项有差异。确认方向无误后加 --apply 执行。"; exit 1
fi
# 目录条目要拷**内容**而非目录本身：`cp -a src/lib dst/lib` 在 dst/lib 已存在时
# 会拷成 dst/lib/lib。这个陷阱只在目标已存在且是目录时出现，第一次跑不会暴露。
for f in $FILES; do
  [ -e "$SRC/$f" ] || continue
  if [ -d "$SRC/$f" ]; then
    mkdir -p "$DST/$f"; cp -a "$SRC/$f/." "$DST/$f/"
  else
    mkdir -p "$(dirname "$DST/$f")"; cp -a "$SRC/$f" "$DST/$f"
  fi
done
echo "已同步 $n 项"
