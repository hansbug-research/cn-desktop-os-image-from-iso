# 被试清单的唯一读取入口（shell 侧）。Python 侧是 scripts/_subjects.py。
# 先前这份清单在 10 个文件里各写一份，新增被试要改 10 处；漏改一处就是
# 静默的覆盖缺口 —— 测试照样全绿，只是少测了一个发行版。
# 唯一真源：config/subjects.json
_SUBJ_ROOT=${_SUBJ_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)}
_SUBJ_JSON="$_SUBJ_ROOT/config/subjects.json"
[ -f "$_SUBJ_JSON" ] || { echo "!! 找不到 $_SUBJ_JSON" >&2; return 1 2>/dev/null || exit 1; }

# ALL_DIDS：空格分隔的 did 列表；IMG[did]：镜像名
ALL_DIDS=$(python3 -c "
import json,sys
d=json.load(open('$_SUBJ_JSON'))
print(' '.join(s['did'] for s in d['subjects']))")
ALL_TIERS=$(python3 -c "
import json
d=json.load(open('$_SUBJ_JSON'))
print(' '.join(d['tiers']))")
declare -A IMG
while IFS=$'\t' read -r _d _i; do
  [ -n "$_d" ] && IMG["$_d"]="$_i"
done < <(python3 -c "
import json
d=json.load(open('$_SUBJ_JSON'))
for s in d['subjects']: print(s['did'], s['image'], sep='\t')")

# m_of <did> —— 取该被试的构建路径（METHOD）。用函数而非关联数组，
# 因为调用方可能在 set -u 下取不存在的键，函数可以显式回落并报错。
m_of() {
  python3 -c "
import json,sys
d=json.load(open('$_SUBJ_JSON'))
m={s['did']: s['method'] for s in d['subjects']}
k=sys.argv[1]
if k not in m: sys.exit(f'!! 未知被试 {k}')
print(m[k])" "$1"
}
