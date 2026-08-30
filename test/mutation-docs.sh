#!/bin/bash
# 分析层的变异测试：故意改坏 stats.json 与正文数字，确认 scripts/verify.py 真的会失败。
#
# 为什么需要它：本项目对**镜像内检查集**做了变异测试（test/mutation.sh），却一直没对
# **分析层**做。审稿时在这层查出五类假阴性 —— 裸子串匹配撞车、抬头数字单点改错不报、
# 正文一批数字零覆盖、「断言总数自洽」只查那句话存在、图表引用被附录索引自动满足。
# 门禁自己也需要被门禁，这条规矩对分析层同样成立。
set -u
ROOT=${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)}
cd "$ROOT" || exit 1
PASS=0; FAIL=0

mut() { # $1=说明 $2=文件 $3=sed 表达式
  local name=$1 file=$2 expr=$3
  cp "$file" "$file.mutbak"
  sed -i "$expr" "$file"
  if python3 scripts/verify.py >/dev/null 2>&1; then
    echo "  ❌ $name — verify 没抓到"; FAIL=$((FAIL+1))
  else
    echo "  ✅ $name — verify 如期失败"; PASS=$((PASS+1))
  fi
  mv "$file.mutbak" "$file"
}

echo "分析层变异测试（改坏后 verify.py 必须非零退出）"
mut "统计量：UOS 可装性 0→9"        derived/stats.json 's/"installable_uos25": 0/"installable_uos25": 9/'
mut "统计量：变异跳过数 1→0"        derived/stats.json 's/"mutation_skipped": 1/"mutation_skipped": 0/'
mut "统计量：ISO 里有 g++"          derived/stats.json 's/"uos_iso_has_gxx": false/"uos_iso_has_gxx": true/'
mut "统计量：门禁失败数 0→2"        derived/stats.json 's/"verify_failed": 0/"verify_failed": 2/'
mut "统计量：摘要链 9→8"            derived/stats.json 's/"digest_chain_passed": 9/"digest_chain_passed": 8/'
mut "统计量：产品线包格式 rpm→dpkg" derived/stats.json 's/"official_pkg_format": "rpm"/"official_pkg_format": "dpkg"/'
mut "统计量：os_id 撞名 true→false" derived/stats.json 's/"os_id_collision": true/"os_id_collision": false/'
# ⚠️ 不能写死 sha256 前缀：镜像一重建它就变了，变异 sed 匹配不上等于没做变异，
# 而结果看起来是「verify 没抓到」—— 实际是用例自己失效了（踩过）。从凭据里现取。
_SHA=$(sed -n 's/.*sha256=\([0-9a-f]\{8\}\).*/\1/p' artifacts/repro-evidence.txt | head -1)
mut "凭据：repro 的一个 sha256"      artifacts/repro-evidence.txt "s/sha256=$_SHA/sha256=deadbeef/"
mut "正文：抬头的验收断言条数"        report.md 's/验收断言 \*\*365\*\* 条/验收断言 **99999** 条/'
mut "README：UOS 可装性 0\/14"       README.md 's|\*\*0 / 14\*\*|**9 / 14**|'

echo
[ "$FAIL" = 0 ] && echo "✅ $PASS 项变异全部被 verify.py 抓到（分析层门禁有效）" \
                || echo "❌ $((PASS+FAIL)) 项里有 $FAIL 项未被抓到"
exit $([ "$FAIL" = 0 ] && echo 0 || echo 1)
