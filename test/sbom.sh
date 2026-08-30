#!/bin/bash
# SBOM 可生成性门禁：镜像必须能被扫描器枚举出包清单，否则安全团队无法审计。
# 关键坑：扫描器从镜像层 tar 里找 /var/lib/dpkg/status，**不跨归档跟随符号链接**，
# 所以 UOS 那种把 admindir 搬到 /usr 下的发行版必须把 status 放回标准位置。
set -u
ROOT=${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)}   # 默认取仓库根，换机器无需改脚本
SOCK=$(docker context inspect 2>/dev/null | grep -oE '/run/user/[0-9]+/docker.sock' | head -1)
SOCK=${SOCK:-/var/run/docker.sock}
TRIVY=${TRIVY:-aquasec/trivy:0.70.0}
FAIL=0
N=0
printf "%-28s %-10s %-10s %s\n" 镜像 dpkg包数 SBOM包数 判定
DISTROS=${DISTROS:-$(ls "$ROOT"/distros/*.conf 2>/dev/null | xargs -r -n1 basename | sed 's/\.conf$//' | tr '\n' ' ')}
for DID in $DISTROS; do
  unset IMMUTABLE ADMINDIR; . "$ROOT/distros/$DID.conf"
  for TIER in micro base devel; do
    IMG="$IMAGE:$TIER"
    docker image inspect "$IMG" >/dev/null 2>&1 || continue
    N=$((N+1))
    n_dpkg=$(docker run --rm "$IMG" /bin/sh -c 'if [ -f /var/lib/dpkg/status ]; then dpkg-query -W; else dpkg-query --admindir=/usr/lib/dpkg/var -W; fi 2>/dev/null | wc -l' 2>/dev/null)
    n_sbom=$(timeout 180 docker run --rm -e http_proxy= -e https_proxy= -e DOCKER_HOST=unix:///ds.sock \
        -v "$SOCK:/ds.sock" "$TRIVY" image --format spdx-json --quiet "$IMG" 2>/dev/null \
        | python3 -c 'import sys,json;print(len(json.load(sys.stdin).get("packages",[])))' 2>/dev/null)
    n_sbom=${n_sbom:-0}
    # SBOM 至少要覆盖 dpkg 报的包数（扫描器会多算 1~2 条镜像自身的元数据条目）
    if [ "$n_sbom" -ge "$n_dpkg" ] && [ "$n_dpkg" -gt 0 ]; then v="✅"; else v="❌"; FAIL=$((FAIL+1)); fi
    printf "%-28s %-10s %-10s %s\n" "$IMG" "$n_dpkg" "$n_sbom" "$v"
  done
done
echo
# 空集合不算通过：镜像不存在时上面 continue 掉，一个都没扫也会走到这里。
# README 给这道门禁写的职责正是「防 SBOM 静默失效（扫出来是空的却报成功）」。
if [ "$N" -eq 0 ]; then
  echo "❌ 一个镜像都没扫到 —— 空集合不算通过（DISTROS=$DISTROS，镜像是否已 import？）"
  exit 1
fi
if [ "$FAIL" -eq 0 ]; then
  echo "✅ 全部镜像可生成 SBOM（$N 个）"; exit 0
fi
echo "❌ $FAIL / $N 个镜像 SBOM 不完整"; exit 1
