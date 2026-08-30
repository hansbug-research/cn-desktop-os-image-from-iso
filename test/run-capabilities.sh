#!/bin/bash
# 在九个镜像里逐一跑能力探针，结果落 out/caps-<did>-<tier>.txt
set -u
ROOT=${ROOT:-/data/dosbuild}
declare -A IMG=([kylin11]=kylin-desktop-v11 [kylin10]=kylin-desktop-v10 [uos25]=uos-desktop-v25)
for d in ${DISTROS:-kylin11 kylin10 uos25}; do
  for t in ${TIERS:-micro base devel}; do
    img="${IMG[$d]}:$t"
    docker image inspect "$img" >/dev/null 2>&1 || continue
    out="$ROOT/out/caps-$d-$t.txt"
    echo "  探测 $img …"
    timeout 900 docker run --rm --init \
      -e http_proxy= -e https_proxy= -e HTTP_PROXY= -e HTTPS_PROXY= \
      -v "$ROOT/test/capabilities.sh:/cap.sh:ro" "$img" /bin/bash /cap.sh > "$out" 2>/dev/null
      grep -q '^cap.probe_complete=Y' "$out" && echo "    ok ($(wc -l < "$out") 项)" \
        || echo "    !! 探针未跑完（输出 $(wc -l < "$out") 行）"
  done
done
