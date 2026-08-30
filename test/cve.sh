#!/bin/bash
# CVE 扫描门禁 —— 主要职责是**不产出假保证**。
#
# 实测结论（2026-08，trivy 0.70.0）：九个镜像没有一个有有效的漏洞库覆盖。
#   麒麟 V11 → trivy 判 OS='none'，压根没扫
#   麒麟 V10 → 被判成 debian bullseye/sid（误判）
#   UOS  V25 → 被判成 debian bookworm/sid（误判）
# 后两种最危险：trivy 拿**厂商改过的版本号**去比 **Debian 的公告数据**，
# 版本区间对不上，于是报 0 个漏洞。一个 151 个包的 bookworm 代镜像报 0 个
# HIGH/CRITICAL 是不可信的 —— 那是"比不出来"，不是"没有漏洞"。
#
# 所以本门禁：
#   ① 拿镜像自己的 os-release ID 和 trivy 判定的 OS family 对账，不一致就标为**无有效覆盖**
#   ② 无有效覆盖的镜像**不计入通过**，也绝不把 0 当成安全结论
#   ③ 真报出 HIGH/CRITICAL 仍然失败（命中就是命中，哪怕覆盖不全）
#
# 要真正跟踪这三个发行版的漏洞，得拿厂商安全公告（麒麟 KYSA、UOS 安全通告）比对包版本，
# 需要外部数据源，不在本仓库范围内 —— 见 README §11。
set -u
ROOT=${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)}   # 默认取仓库根，换机器无需改脚本
MAXSEV=${MAXSEV:-0}
TRIVY=${TRIVY:-aquasec/trivy:0.70.0}
SOCK=${SOCK:-$(docker context inspect -f '{{.Endpoints.docker.Host}}' 2>/dev/null | sed 's|^unix://||')}
SOCK=${SOCK:-/run/user/$(id -u)/docker.sock}
declare -A IMG=([kylin11]=kylin-desktop-v11 [kylin10]=kylin-desktop-v10 [uos25]=uos-desktop-v25)
docker image inspect "$TRIVY" >/dev/null 2>&1 || { echo "!! 本地无 $TRIVY 镜像，跳过（同 test/sbom.sh）"; exit 0; }
[ -S "$SOCK" ] || { echo "!! 找不到 docker socket ($SOCK)，跳过"; exit 0; }

COVERED=0; UNCOVERED=0; BAD=0
DISTROS=${DISTROS:-"kylin11 kylin10 uos25"}
for d in $DISTROS; do
  for t in micro base devel; do
    img="${IMG[$d]}:$t"
    docker image inspect "$img" >/dev/null 2>&1 || continue
    real=$(docker run --rm "$img" sh -c '. /etc/os-release 2>/dev/null; echo "${ID:-?}"' 2>/dev/null)
    j=$(timeout 300 docker run --rm -e http_proxy= -e https_proxy= \
          -e DOCKER_HOST=unix:///ds.sock -v "$SOCK:/ds.sock" "$TRIVY" \
          image --quiet --scanners vuln --format json "$img" 2>/dev/null)
    [ -n "$j" ] || { echo "  ✗ $img trivy 无输出"; BAD=$((BAD+1)); continue; }
    read -r fam nvuln <<EOF
$(printf '%s' "$j" | python3 -c '
import json,sys
d=json.load(sys.stdin)
fam=(d.get("Metadata") or {}).get("OS",{}).get("Family") or "none"
rs=d.get("Results") or []
n=sum(1 for r in rs for v in (r.get("Vulnerabilities") or []) if v.get("Severity") in ("HIGH","CRITICAL"))
print(fam, n)' 2>/dev/null)
EOF
    fam=${fam:-none}; nvuln=${nvuln:-0}
    if [ "$nvuln" -gt "$MAXSEV" ]; then
      echo "  ✗ $img HIGH+CRITICAL=$nvuln 超过阈值 $MAXSEV（真命中，需处理）"
      BAD=$((BAD+1)); continue
    fi
    # 真实 ID 与 trivy 判定必须对得上，才算有效覆盖
    case "$real/$fam" in
      kylin/kylin|uos/uos|uos/deepin)
        echo "  ✅ $img 有效覆盖（trivy 判 $fam），HIGH+CRITICAL=$nvuln"; COVERED=$((COVERED+1)) ;;
      */none)
        echo "  ⚠ $img 无覆盖：trivy 未识别该 OS（真实 ID=$real）→ 结果不构成安全结论"
        UNCOVERED=$((UNCOVERED+1)) ;;
      *)
        echo "  ⚠ $img 无有效覆盖：真实 ID=$real 却被判成 $fam（误判）→ 报出的 $nvuln 个漏洞数不可信"
        UNCOVERED=$((UNCOVERED+1)) ;;
    esac
  done
done
echo "══ CVE: 有效覆盖 $COVERED / 无有效覆盖 $UNCOVERED / 真命中或异常 $BAD"
if [ "$BAD" -gt 0 ]; then echo "❌ 有真实命中或扫描异常"; exit 1; fi
if [ "$UNCOVERED" -gt 0 ]; then
  cat <<'MSG'
⚠️  重要：上述「无有效覆盖」的镜像，扫描结果**不能**用来宣称无漏洞。
    trivy 会把麒麟/UOS 误判成 Debian，拿厂商改过的版本号比 Debian 的公告区间，
    比不出来就报 0 —— 这是"没有数据"，不是"没有漏洞"。
    真实漏洞跟踪需接厂商安全公告（麒麟 KYSA / UOS 安全通告），见 README §11。
MSG
fi
echo "✅ CVE 门禁执行完毕（无真实命中；覆盖情况见上）"
