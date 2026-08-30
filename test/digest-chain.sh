#!/bin/bash
# 摘要链门禁：manifest 记的 sha256 —— out/*.tar 实际字节 —— 本地已打标签的镜像，
# 三者必须首尾相扣。
#
# 为什么最后一环不能直接比 sha256：`docker import` 会把 tar 重新归一化
# （补 whiteout 语义、统一 header），layer 的 diff_id 与源 tar 的 sha256 天然不同。
# 但归一化是确定的，所以把同一个 tar 再导一次、比 diff_id 是等价且严格的做法。
#
# 这条链专防一类事故：镜像重建了但 manifest 没更新（审计凭据与实物脱钩）。
set -u
ROOT=${ROOT:-/data/dosbuild}
declare -A IMG=([kylin11]=kylin-desktop-v11 [kylin10]=kylin-desktop-v10 [uos25]=uos-desktop-v25)
PASS=0; FAIL=0
for d in kylin11 kylin10 uos25; do
  for t in micro base devel; do
    tar="$ROOT/out/$d-$t.tar"; man="$ROOT/out/$d-$t.manifest"; img="${IMG[$d]}:$t"
    [ -f "$tar" ] || { echo "  ✗ $d-$t 缺 tar"; FAIL=$((FAIL+1)); continue; }
    [ -f "$man" ] || { echo "  ✗ $d-$t 缺 manifest"; FAIL=$((FAIL+1)); continue; }
    rec=$(grep -oE '^# tarball sha256: [0-9a-f]{64}' "$man" | awk '{print $4}')
    act=$(sha256sum "$tar" | cut -d' ' -f1)
    if [ "$rec" != "$act" ]; then
      echo "  ✗ $d-$t manifest 与 tar 脱钩: 记录 ${rec:0:12}… 实际 ${act:0:12}…"
      FAIL=$((FAIL+1)); continue
    fi
    have=$(docker image inspect "$img" --format '{{index .RootFS.Layers 0}}' 2>/dev/null)
    if [ -z "$have" ]; then echo "  ✗ $d-$t 镜像 $img 不存在"; FAIL=$((FAIL+1)); continue; fi
    tmp="digestchain:$$-$d-$t"
    want=$(docker import "$tar" "$tmp" >/dev/null 2>&1 && \
           docker image inspect "$tmp" --format '{{index .RootFS.Layers 0}}' 2>/dev/null)
    docker rmi "$tmp" >/dev/null 2>&1
    if [ "$have" = "$want" ]; then
      echo "  ✅ $d-$t  manifest=tar=镜像  (${act:0:12}… → ${have#sha256:})" | cut -c1-96
      PASS=$((PASS+1))
    else
      echo "  ✗ $d-$t 镜像不是由该 tar 导入的: 镜像 ${have#sha256:} 期望 ${want#sha256:}"
      FAIL=$((FAIL+1))
    fi
  done
done
echo "══ 摘要链: 通过 $PASS / 失败 $FAIL"
[ "$FAIL" = 0 ] || { echo "❌ 摘要链断裂"; exit 1; }
echo "✅ 九个镜像的 manifest / tar / 镜像三者一致"
