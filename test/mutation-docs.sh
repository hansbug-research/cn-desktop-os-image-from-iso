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

mutcmd() { # $1=说明 $2=文件 $3=任意 shell 命令（sed 表达不出的变异用它，如「复制一段」）
  local name=$1 file=$2 cmd=$3
  cp "$file" "$file.mutbak"
  # 中途被信号打断会同时留下 .mutbak 与被改坏的文件 —— trap 保证还原
  trap '[ -f "$file.mutbak" ] && mv "$file.mutbak" "$file"' INT TERM
  eval "$cmd"
  if python3 scripts/verify.py >/dev/null 2>&1; then
    echo "  ❌ $name — verify 没抓到"; FAIL=$((FAIL+1))
  else
    echo "  ✅ $name — verify 如期失败"; PASS=$((PASS+1))
  fi
  mv "$file.mutbak" "$file"
  trap - INT TERM
}

mut() { # $1=说明 $2=文件 $3=sed 表达式
  local name=$1 file=$2 expr=$3
  cp "$file" "$file.mutbak"
  # 15 个用例里 10 个走这里 —— trap 与 mutcmd 一致，否则被打断会同时留下
  # .mutbak 与被改坏的文件（实测复现过）
  trap '[ -f "$file.mutbak" ] && mv "$file.mutbak" "$file"' INT TERM
  sed -i "$expr" "$file"
  if python3 scripts/verify.py >/dev/null 2>&1; then
    echo "  ❌ $name — verify 没抓到"; FAIL=$((FAIL+1))
  else
    echo "  ✅ $name — verify 如期失败"; PASS=$((PASS+1))
  fi
  mv "$file.mutbak" "$file"
  trap - INT TERM
}

echo "分析层变异测试（改坏后 verify.py 必须非零退出）"
mut "统计量：UOS 可装性 0→9"        derived/stats.json 's/"installable_uos25": 0/"installable_uos25": 9/'
mut "统计量：变异跳过数 1→0"        derived/stats.json 's/"mutation_skipped": 1/"mutation_skipped": 0/'
mut "统计量：ISO 里有 g++"          derived/stats.json 's/"uos_iso_has_gxx": false/"uos_iso_has_gxx": true/'
mut "统计量：门禁失败数 0→2"        derived/stats.json 's/"verify_failed": 0/"verify_failed": 2/'
mut "统计量：摘要链 15→14"           derived/stats.json 's/"digest_chain_passed": 15/"digest_chain_passed": 14/'
mut "统计量：产品线包格式 rpm→dpkg" derived/stats.json 's/"official_pkg_format": "rpm"/"official_pkg_format": "dpkg"/'
mut "统计量：os_id 撞名 true→false" derived/stats.json 's/"os_id_collision": true/"os_id_collision": false/'
# ⚠️ 不能写死 sha256 前缀：镜像一重建它就变了，变异 sed 匹配不上等于没做变异，
# 而结果看起来是「verify 没抓到」—— 实际是用例自己失效了（踩过）。从凭据里现取。
_SHA=$(sed -n 's/.*sha256=\([0-9a-f]\{8\}\).*/\1/p' artifacts/repro-evidence.txt | head -1)
mut "凭据：repro 的一个 sha256"      artifacts/repro-evidence.txt "s/sha256=$_SHA/sha256=deadbeef/"
# 同上：不写死会变的值，从 stats 现取
_VP=$(python3 -c "import json;print(json.load(open('derived/stats.json'))['verify_passed'])")
mut "正文：抬头的验收断言条数"        report.md "s/验收断言 \*\*${_VP}\*\* 条/验收断言 **99999** 条/"
_UI=$(python3 -c "import json;s=json.load(open('derived/stats.json'));print(f\"{s['installable_uos25']} / {s['installability_tools']}\")")
mut "README：UOS 可装性"             README.md "s|\*\*${_UI}\*\*|**9 / 14**|"

echo
# 段落/表格/脚注重复 —— 这三条门禁是 2026-08-30 那次编辑事故之后加的：
# 一次「删除」实际把待删块换成了前一段的副本，26 行陈旧重复在 322 条断言全过的
# 情况下躺在已发布报告里。按仓库规矩，新门禁必须自带变异用例。
mutcmd "正文：复制一个长段落" report.md 'python3 - <<PY
import pathlib
p=pathlib.Path("report.md"); s=p.read_text()
ps=[x for x in s.split("\n\n") if len(x.strip())>=120]
s=s.replace(ps[3], ps[3]+"\n\n"+ps[3], 1)
p.write_text(s)
PY'
mutcmd "正文：复制名录表表头" report.md 'python3 - <<PY
import pathlib
p=pathlib.Path("report.md"); s=p.read_text()
h="| | OS | 类型 | 厂商/主导方 |"
i=s.index(h); s=s[:i]+s[i:i+len(h)]+"\n"+s[i:]
p.write_text(s)
PY'
mutcmd "正文：复制一条脚注定义" report.md 'python3 - <<PY
import pathlib, re
p=pathlib.Path("report.md"); s=p.read_text()
m=re.search(r"^\[\^R\d+\]:.*$", s, re.M)
s=s[:m.start()]+m.group(0)+"\n"+s[m.start():]
p.write_text(s)
PY'
mutcmd "正文：复制一行表格数据行（不带表头）" report.md 'python3 - <<PY
import pathlib
p=pathlib.Path("report.md"); s=p.read_text()
rows=[l for l in s.split("\n") if l.startswith("| ") and len(l)>=80 and "---|" not in l]
s=s.replace(rows[0], rows[0]+"\n"+rows[0], 1)
p.write_text(s)
PY'
mutcmd "README：复制一个长段落" README.md 'python3 - <<PY
import pathlib
p=pathlib.Path("README.md"); s=p.read_text()
ps=[x for x in s.split("\n\n") if len(x.strip())>=120]
s=s.replace(ps[0], ps[0]+"\n\n"+ps[0], 1)
p.write_text(s)
PY'


[ "$FAIL" = 0 ] && echo "✅ $PASS 项变异全部被 verify.py 抓到（分析层门禁有效）" \
                || echo "❌ $((PASS+FAIL)) 项里有 $FAIL 项未被抓到"
exit $([ "$FAIL" = 0 ] && echo 0 || echo 1)
