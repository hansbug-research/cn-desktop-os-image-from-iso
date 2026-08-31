#!/bin/bash
# 在全部被试镜像里逐一跑能力探针，结果直接落 artifacts/caps-<did>-<tier>.txt。
# 写 artifacts 而非 out：d3 采集与 render-capabilities 都读 artifacts，
# 中间留一个需要人手 cp 的目录，就会再出现「探针比镜像旧」那类错。
set -u
ROOT=${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)}   # 默认取仓库根，换机器无需改脚本
. "$ROOT/lib/subjects.sh"      # ALL_DIDS / ALL_TIERS / IMG[]，唯一真源 config/subjects.json
mkdir -p "$ROOT/artifacts"
fail=0
for d in ${DISTROS:-$ALL_DIDS}; do
  for t in ${TIERS:-$ALL_TIERS}; do
    img="${IMG[$d]:-}"
    # 未知 did 与缺失镜像都必须报错。`continue` 会让「少测一个发行版」
    # 表现为矩阵少一列，汇总照样全绿 —— 这类静默跳过在本仓库出过四次。
    [ -n "$img" ] || { echo "  !! 未知被试 $d（不在 config/subjects.json 里）"; fail=1; continue; }
    img="$img:$t"
    docker image inspect "$img" >/dev/null 2>&1 || { echo "  !! 缺镜像 $img"; fail=1; continue; }
    out="$ROOT/artifacts/caps-$d-$t.txt"
    echo "  探测 $img …"
    # rpm 系没法在镜像内凭空造一个 .rpm 来测「本地包直装」（造 rpm 要 rpm-build，
    # 只有 devel 档有）。所以把一个最小 noarch 包以只读方式挂进来，三档同样口径。
    # deb 侧在镜像内现造现装，两边测的都是「装一个本机没有的包再卸干净」。
    FIX=(); [ -d "$ROOT/test/fixtures" ] && FIX=(-v "$ROOT/test/fixtures:/probe-fixtures:ro")
    timeout 900 docker run --rm --init \
      -e http_proxy= -e https_proxy= -e HTTP_PROXY= -e HTTPS_PROXY= \
      "${FIX[@]}" \
      -v "$ROOT/test/capabilities.sh:/cap.sh:ro" "$img" /bin/bash /cap.sh > "$out" 2>/dev/null
    if grep -q '^cap.probe_complete=Y' "$out"; then
      echo "    ok ($(wc -l < "$out") 项)"
    else
      echo "    !! 探针未跑完（输出 $(wc -l < "$out") 行）"; fail=1
    fi
  done
done
exit $fail
