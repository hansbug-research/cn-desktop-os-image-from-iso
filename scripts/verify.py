#!/usr/bin/env python3
"""机器核对 report.md / README.md 里的每个声明。

约定：正文里的统计量必须能从 derived/stats.json 重算出来。这个脚本非 0 退出即不得提交。
它同时核对断言总数自洽 —— 正文声明的条数必须等于实际执行的条数。

⚠️ 它只覆盖被写成断言的那些数字。未被覆盖的仍需人工核对，
不要把「verify 全绿」等同于「每个数字都被机器核过」。
"""
import csv as csv_mod
import json, os, pathlib, re, sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _subjects import DIDS, TIERS as T_LIST, METHOD, FAMILY, SHORT, SUBJECTS   # 唯一真源 config/subjects.json
_DISPLAY = {s_["did"]: s_["display"] for s_ in SUBJECTS}
_N_IMG = len(DIDS) * len(T_LIST)

ROOT = pathlib.Path(__file__).resolve().parent.parent
S = json.loads((ROOT / "derived" / "stats.json").read_text())
REPORT = (ROOT / "report.md").read_text()
README = (ROOT / "README.md").read_text() if (ROOT / "README.md").exists() else ""
TAB = ROOT / "derived" / "tables"

# 正文 = 附录之前的部分。图表/缺陷 ID 的「被引用」只认正文：
# 附录 A/B 是完整索引，把它算进来会让相关断言永不失败。
_APPENDIX = REPORT.index("## 附录 A")
BODY = REPORT[:_APPENDIX]

N = 0; BAD = []
def ok(cond, msg):
    global N
    N += 1
    if not cond: BAD.append(msg)

def in_text(s, where="report", label=None, ctx=None):
    """在正文里找一个数字。**必须带上下文**：裸子串会撞车 —— 早先版本把
    cells_supported 400 改成 401 竟然通过，因为正文别处有「未授权返回 401」；
    102 改成 101 也通过，因为有「policy-rc.d 返回 101」。两个统计量同时改错，
    靠两个语义无关的巧合蒙混过去。"""
    t = REPORT if where == "report" else README
    # ⚠️ ctx 一律视为**已成形的正则**，不再走 .format() —— 正则量词 `{0,8}` 会被
    # format 当成占位符而抛 KeyError。需要插值的调用方自己用 f-string 拼好。
    pat = ctx if ctx else rf"(?<![0-9]){re.escape(str(s))}(?![0-9])"
    ok(re.search(pat, t) is not None, f"{where} 里找不到 {label or s!r}"
       + (f"（模式 {pat}）" if ctx else ""))

# ── README 与 report 抬头的同名量必须相等 ────────────────────────────────────
# 两份抬头列的是同一批统计量，措辞略有差异（一处写「条（镜像层，make verify）」、
# 另一处写「条」）。批量替换按字面匹配，字面差异恰恰是漂移已经发生的证据 ——
# 刚才就漏改了一处「厂商缺陷留档」。所以改成断言两边相等，不靠替换替干净。
_HEAD_QTY = ["构建镜像", "构建路径", "厂商缺陷留档"]
_hd = []
for _k in _HEAD_QTY:
    _a = re.search(rf"{_k} \*\*(\d+)\*\*", REPORT)
    _b = re.search(rf"{_k} \*\*(\d+)\*\*", README)
    if _a and _b and _a.group(1) != _b.group(1):
        _hd.append(f"{_k}: report={_a.group(1)} README={_b.group(1)}")
ok(not _hd, f"两份抬头的同名量必须相等{'：' + '；'.join(_hd) if _hd else ''}")

# ── 两个被试真源必须一致 ──────────────────────────────────────────────────────
# test/sbom.sh 与 test/verify.sh 的被试清单是从 `ls distros/*.conf` 推导的，
# 而采集与分析脚本读 config/subjects.json。两个真源自维护性都不错，但会分叉：
# 多一个 conf（试验中的发行版）会让镜像层门禁去找不存在的镜像，少一个会让某个
# 被试静默不过门禁。这里锁住对应关系，而不是把其中一边改掉。
_confs = {f.stem for f in (ROOT / "distros").glob("*.conf")}
ok(_confs == set(DIDS),
   f"distros/*.conf 与 config/subjects.json 必须一一对应；"
   f"仅在 conf: {sorted(_confs - set(DIDS))}，仅在 subjects: {sorted(set(DIDS) - _confs)}")

# ── 正文不得残留占位符 ──────────────────────────────────────────────────────
# 本仓库有过把 sed 的字面量 `\1` 发到公开报告里的先例（§9.2）。编辑正文时先占位、
# 回填前发布，是同一族事故。判据不用「全大写」这类宽特征——正文里合法的 TODO 与
# 环境变量名都会撞上，而会误报的门禁最终会被关掉。改用正文里不可能自然出现的
# 占位符语法 ⟪…⟫，判据因此零假阳性、零漏报。
_ph = []
for _name, _txt in (("report.md", REPORT), ("README.md", README)):
    for _m in re.finditer(r"⟪[^⟫]{1,40}⟫", _txt):
        _ph.append(f"{_name}:{_m.group(0)}")
    # 只查**行内代码之外**的出现。本报告 §9.2 正当地引用了字面量 `\1`（讲述那次
    # 把它发到公开报告的事故），而「内容黑名单」型判据对自我指涉的文档必然误报：
    # 讲述某个坏模式的文字，本身含有那个坏模式。反引号内的引用不算残留。
    _stripped = re.sub(r"`[^`]*`", "", _txt)
    _stripped = re.sub(r"```.*?```", "", _stripped, flags=re.S)
    for _bad in ("\\1", "\\2"):
        if _bad in _stripped:
            _ph.append(f"{_name} 含 sed 反向引用残留 {_bad}")
ok(not _ph, f"正文不得残留占位符{'：' + '、'.join(sorted(set(_ph))[:8]) if _ph else ''}")

# ── 出厂产物不得携带构建期路径 ────────────────────────────────────────────────
# 凝思是第一个「构建期用本地介质、出厂无源可写」的被试，一下顶出了 selfhost 路径里
# 一个隐含假设：SRCLIST 直接复用了 MIRROR。对另外四家这两者恰好重合（都是在线镜像
# 站），所以这行代码一直没暴露。单点修完之后这里加类级门禁，下一个本地介质被试不必
# 再踩一遍。
# 判据只认 **builder 的挂载路径**，不认所有 file://。麒麟信安出厂的
# `kylinsec.repo` 是厂商自带文件，里面有一条 enabled=0 的
# `[CDROM] baseurl=file:///run/media/$user/KylinSec/` —— 那是厂商约定的合法内容。
# 把判据写成「任何 file://」会误报，而误报会让人去改本来正确的东西（差点就改了）。
_leak = []
for _r in json.loads((ROOT / "raw" / "d2_our_images.json").read_text())["ours"]:
    _u = _r.get("repo_urls", "") or ""
    for _bad in ("/w/media", "/w/localrepo", "file:///w/", "copy:///w/"):
        if _bad in _u:
            # _r["image"] 已含 tag，别再拼 tier —— 这行只在失败时执行，平时看不见；
            # 变异测试是唯一会强制走失败分支的东西，错字只有那时才暴露。
            _leak.append(f'{_r["image"]} 的源清单含构建期路径 {_bad}')
ok(not _leak, f"出厂源清单不得含 builder 挂载路径{'：' + '；'.join(_leak) if _leak else ''}")

# ── d2 的标量字段必须是单行 ──────────────────────────────────────────────────
# 采集脚本里把两条命令串起来（`rpm -qa | wc -l; dpkg-query | wc -l`）会让值变成
# '112\n0'。这类脏值不总会炸：int() 会抛异常（能发现），而字符串直接拼进 README
# 表格会静默产出「112\n0 包」。所以在这一层断言，而不是指望采集时不写错。
_multi = []
for _r in json.loads((ROOT / "raw" / "d2_our_images.json").read_text())["ours"]:
    for _k in ("pkg_count", "pkg_format", "glibc_pkg", "image_id", "image_created"):
        _v = _r.get(_k)
        if isinstance(_v, str) and "\n" in _v.strip():
            _multi.append(f"{_r['image']}.{_k}={_v!r}")
ok(not _multi, f"d2 的标量字段必须是单行{'：' + '；'.join(_multi[:4]) if _multi else ''}")

# ── 缺陷台账的条数必须与源码一致 ────────────────────────────────────────────
# d5 的输入就是 collect_d5*.py 自己，两者之间没有文件时间戳关系可查 —— 加了
# 一条缺陷却忘了重采，stats.json 会停在旧值而无人报警（本轮真发生过：台账
# 19 条而 stats 停在 15）。所以直接比对源码里的条目数。
_d5src = (ROOT / "scripts" / "collect_d5_iso_and_defects.py").read_text()
_n_src = _d5src.count('dict(id="D')
ok(S["defects"] == _n_src,
   f"stats.json 的 defects={S['defects']} 应等于源码里的 {_n_src} 条 —— 不等说明改了台账没重采 d5")

# ── d2 的采集不得早于镜像 ────────────────────────────────────────────────────
# d3 一直有这条（探针输出的 mtime 不得早于镜像 Created），d2 没有 —— 于是镜像
# 迭代五轮而 d2 只采过一次时无人报警，README 的镜像表、§3 的规模表、体积统计
# 全建立在过期数据上。同一族缺口在另一个数据集上的翻版。
_d2 = json.loads((ROOT / "raw" / "d2_our_images.json").read_text())
_d2at = _d2.get("collected_at", "")
# ⚠️ 必须先归一到 UTC 再比。docker 的 .Created 带本地时区偏移（+08:00），
# 而 collected_at 是 UTC —— 直接比字符串会把 8 小时的时区差当成新鲜度问题，
# 实测把「镜像比采集早 2 分钟」误报成「镜像晚于采集 8 小时」。
# 与今天另外两处同型：判据用了错误的比较基准（os.path.exists 不认 chroot 边界、
# grep 模式被 shell 展开）。
import datetime as _dt
def _utc(x):
    x = (x or "").strip()
    if not x:
        return None
    x = _re_sub_ns(x)
    try:
        return _dt.datetime.fromisoformat(x.replace("Z", "+00:00")).astimezone(_dt.timezone.utc)
    except ValueError:
        return None
def _re_sub_ns(x):
    # docker 给 9 位小数，fromisoformat 在 3.11 前只吃 3/6 位
    return re.sub(r"(\.\d{6})\d+", r"\1", x)
_stale2 = []
_at = _utc(_d2at)
for _r in _d2["ours"]:
    _c = _utc(_r.get("image_created"))
    if _c and _at and _c > _at:
        _stale2.append(f"{_r['image']}（镜像 {_c:%Y-%m-%dT%H:%M:%SZ} 晚于采集 {_at:%Y-%m-%dT%H:%M:%SZ}）")
ok(not _stale2,
   f"d2 的采集时刻必须不早于每个镜像的 Created{'：' + '；'.join(_stale2[:4]) if _stale2 else ''}")
ok(all("image_created" in _r for _r in _d2["ours"]),
   "d2 每条记录都应带 image_created（缺了这条新鲜度就不可机器发现）")

# ── 15 份探针输出必须出自同一版探针 ──────────────────────────────────────────
# 改了探针只重跑一部分镜像，混着的矩阵横向对比就不成立，而输出本身看不出异常。
_shas = {}
for _d in DIDS:
    for _t in T_LIST:
        _f = ROOT / "artifacts" / f"caps-{_d}-{_t}.txt"
        if _f.exists():
            for _l in _f.read_text().splitlines():
                if _l.startswith("cap.probe_sha="):
                    _shas.setdefault(_l.split("=", 1)[1], []).append(f"{_d}:{_t}")
ok(len(_shas) == 1,
   f"全部探针输出应出自同一版 capabilities.sh，实际 {len(_shas)} 个版本：" +
   "；".join(f"{k}→{len(v)} 份" for k, v in _shas.items()))

# ── 规模量 ──────────────────────────────────────────────────────────────────
ok(S["images_built"] == 15, "构建镜像数应为 15")
# 同一个量既锚死字面值、又核对它与被试清单自洽：前者防正文漂移，
# 后者防「加了被试却忘了改这里」。只有前者时，新增被试会让断言静默失真。
ok(S["images_built"] == _N_IMG, f"镜像数应等于 被试数×档位数 = {_N_IMG}")
ok(sorted(S["distros"]) == sorted(DIDS), "被试发行版清单")
ok(sorted(S["tiers"]) == sorted(T_LIST), "档位清单")
ok(sorted(S["build_methods"]) == sorted(set(METHOD.values())), "构建路径清单")
in_text(S["capability_cells"], label="能力矩阵格数")
in_text(S["capability_items"], label="能力项数")
for k in ("cells_supported", "cells_gap", "cells_na"):
    in_text(S[k], label=f"三态计数 {k}")

# 198 格不适用的三分拆：三者之和必须等于 cells_na，且三个数都要在正文出现
ok(S["cells_na_from_N"] + S["cells_na_from_na"] + S["cells_na_from_Y"] == S["cells_na"],
   "NA 三分拆之和应等于 cells_na")
# ⚠️ ctx 必须带上 `N`/`Y` 的极性：只写「格**探针实测为」两条模式互相可满足，
# 把 172 与 11 对调、连「三类合计」一起改也全绿（与 9↔6 那次同型）。
in_text(S["cells_na_from_N"], label="NA 中探针为 N 的格数",
        ctx=rf"\*\*{S['cells_na_from_N']} 格\*\*探针实测为 `N`")
in_text(S["cells_na_from_na"], label="NA 中探针为 n/a 的格数",
        ctx=rf"\*\*{S['cells_na_from_na']} 格\*\*探针本身输出 `n/a`")
in_text(S["cells_na_from_Y"], label="NA 中探针为 Y 的格数",
        ctx=rf"\*\*{S['cells_na_from_Y']} 格\*\*探针实测为 `Y`")
ok(re.search(rf"三类合计 {S['cells_na_from_N']}\+{S['cells_na_from_na']}\+{S['cells_na_from_Y']}="
             rf"{S['cells_na']}", REPORT) is not None, "三类合计式必须与三个分量一致")
# X2：档位口径也要钉住，否则「三档均为 11」可被写回「base/devel 各 11」
ok("麒麟 V10 三档均为 11 个" in REPORT,
   "麒麟 V10 的 masked 单元是三档均 11（t12 可查），不得写成只有 base/devel")
# n/a 那批的成因必须写对。键名与构成随「探针按包管理系分支」变了：原先是 apt 三项
# × 3 个 micro = 9 格，现在是 pkg_update/pkg_roundtrip/pkg_check 各 5 格（5 个 micro
# 档没有包管理器）+ cc_clean_stderr 10 格（micro 与 base 各 5 家，没有编译器就无所谓
# stderr 干净）。判据从写死数字改成从 stats 推 —— 写死的数在被试数变化时必然失真。
_na_pkg = sum(v for k, v in S["na_na_by_item"].items() if k.startswith("pkg_"))
_cc_n = S["na_na_by_item"].get("cc_clean_stderr", 0)
ok(_cc_n == 2 * len(DIDS),
   f"cc_clean_stderr 的 n/a 应为 micro+base 两档 × {len(DIDS)} 家 = {2 * len(DIDS)} 格，实际 {_cc_n}")
ok(_na_pkg == 3 * len(DIDS),
   f"包管理三项的 n/a 应为 3 项 × {len(DIDS)} 个 micro 档 = {3 * len(DIDS)} 格，实际 {_na_pkg}")
# 正文必须把这两个数与各自成因绑在一起 —— 只核 stats 内部自洽的话，把两个数对调
# 也全绿，而上一轮出错的正是「成因写错」这件事本身。
for where, txt in (("report", REPORT), ("readme", README)):
    n_pkg = len(re.findall(rf"{_na_pkg} 格[是为][^。；]{{0,24}}?包管理", txt))
    n_cc = len(re.findall(rf"{_cc_n} 格[是为][^。；]{{0,24}}?`cc_clean_stderr`", txt))
    ok(n_pkg >= 1, f"{where} 必须有一处把 {_na_pkg} 格与「包管理三项」写在一起，实际 {n_pkg} 处")
    ok(n_cc >= 1, f"{where} 必须有一处把 {_cc_n} 格与 `cc_clean_stderr` 写在一起，实际 {n_cc} 处")

# ── 核心结论：麒麟官方镜像不是桌面产品线 ────────────────────────────────────
ok(S["kylin_desktop_official_images"] == 0, "麒麟桌面官方镜像应为 0")
ok(S["uos_official_images"] == 0, "UOS 官方镜像应为 0")
ok(S["os_id_collision"] is True, "麒麟官方与桌面的 os-release ID 应相同")
ok(S["official_pkg_format"] == "rpm", "麒麟官方镜像应为 rpm")
# 加入麒麟信安后不再全是 dpkg —— 这正是第二轮要扩的维度（§2.4）。
ok(sorted(S["ours_pkg_formats"]) == ["dpkg", "rpm"], "自建镜像应涵盖 dpkg 与 rpm 两种包格式")
in_text("Kylin Linux Advanced Server", label="官方镜像 NAME")
in_text("update.cs2c.com.cn", label="官方镜像软件源域名")
in_text("archive.kylinos.cn", label="桌面版软件源域名")
# 产品线对照表必须真的含有两种包格式，否则正文那张表是空口说
t3 = (TAB / "t03_product_line_comparison.csv").read_text()
ok("rpm" in t3 and "dpkg" in t3, "t03 应同时含 rpm 与 dpkg 行")
ok(S["existence_probes"] >= 8, "存在性探测至少 8 条")
ok(S["existence_found"] == 1, "存在性探测应只有 1 条命中")
in_text(S["existence_probes"], label="存在性探测条数",
        ctx=rf"另一组 {S['existence_probes']} 条是针对桌面 tag 的存在性探测")

# ── 编译能力 ────────────────────────────────────────────────────────────────
ok(S["devel_count"] == len(DIDS), f"devel 档应为 {len(DIDS)} 个")
ok(S["devel_c_ok"] == len(DIDS), f"{len(DIDS)} 个 devel 档 C 编译应全通过")
ok(S["devel_cxx_ok"] == 4, "C++ 应有四家通过（UOS 是唯一例外，它的 ISO 里没有 g++）")
ok(S["devel_c_ok"] == 5, "C 应五家全通过")
ok(S["devel_cxx_ok"] < S["devel_count"], "C++ 覆盖应少于 C —— 这是 UOS 无 g++ 的直接证据")

# ── 门禁 ────────────────────────────────────────────────────────────────────
ok(S["verify_failed"] == 0, "verify 不得有失败项")
ok(S["verify_passed"] >= S["verify_baseline"], "verify 通过数不得低于基线")
in_text(S["verify_passed"], label="verify 通过数")
in_text(S["verify_baseline"], label="verify 基线")
ok(S["digest_chain_passed"] == _N_IMG, f"摘要链应 {_N_IMG}/{_N_IMG}")
ok(S["mutation_missed"] == 0, "变异测试不得有漏抓")
# 变异用例数由 test/mutation.sh 的用例表决定，写死数字在加用例后必然失败。
# 判据改为「只允许涨」，与检查数量基线同一原则。
ok(S["mutation_caught"] >= 12, f"镜像层变异用例只允许涨，实际 {S['mutation_caught']}（基线 12）")
ok(S["mutation_missed"] == 0, f"变异用例不得有漏报，实际漏 {S['mutation_missed']}")
in_text(S["mutation_caught"], label="变异用例数")
# 覆盖面从 config/subjects.json 按 METHOD 推导：归一时间戳的路径纳入，selfhost 不纳入。
_n_repro = 3 * sum(1 for _d in DIDS if METHOD[_d] != "selfhost")
ok(S["repro_identical"] == _n_repro,
   f"可复现性应 {_n_repro} 个产物逐位一致（归一时间戳的路径 × 3 档），实际 {S['repro_identical']}")
in_text(S["repro_identical"], label="逐位一致产物数")
ok(S["manifests"] == _N_IMG, f"应有 {_N_IMG} 份 manifest")
ok(S["probe_complete_all"] is True, "所有探针必须跑完（哨兵为 Y）")
ok(S["probe_stale_vs_image"] == [],
   f"这些镜像的探针输出早于镜像本身（数据比被测对象旧）：{S['probe_stale_vs_image']}")
ok(S["probe_provenance_recorded"] == _N_IMG,
   f"全部 {_N_IMG} 个镜像都应记下探针时间与镜像创建时间，实际 {S['probe_provenance_recorded']}")

# ── 可复现性凭据必须与交付物对账（本仓库最该有、却一度没有的那条断言）──────
_re_ev = (ROOT / "artifacts" / "repro-evidence.txt")
if _re_ev.exists():
    ev = dict(re.findall(r"^(\S+)\s+一致\s+sha256=([0-9a-f]{64})", _re_ev.read_text(), re.M))
    ok(len(ev) == S["repro_identical"], f"凭据里的一致条数应为 {S['repro_identical']}")
    import json as _j
    mans = _j.loads((RAW := ROOT / "raw" / "d4_gates.json").read_text())["manifests"]
    for k, sha in ev.items():
        rec = mans.get(k, {})
        ok(rec.get("tarball_sha256") == sha,
           f"repro 凭据的 {k} sha256 与 manifest 不一致 —— 两条链锚在了不同构建上")

# ── 可装性（区分「没预装」与「装不上」的定量依据）────────────────────────────
ok(S["installable_kylin11"] == S["installability_tools"], "麒麟 V11 应 14/14 可装")
ok(S["installable_kylin10"] == S["installability_tools"], "麒麟 V10 应 14/14 可装")
ok(S["installable_uos25"] == 0, "UOS 应 0/14 —— 这是「硬缺口」论断的定量依据")
in_text(S["uos_iso_packages"], label="UOS ISO 包数")
ok(S["uos_iso_has_gxx"] is False, "UOS ISO 里不应有 g++（C++ 构建环境论断的依据）")
in_text(S["uos_apt_repo_packages"], label="UOS 源提供的包数",
        ctx=rf"源索引只有 {S['uos_apt_repo_packages']} 个条目")
ok(S["uos_apt_positive_control"] is True,
   "UOS 源规模采集必须带阳性对照 —— 否则「工具都装不上」区分不了「源里没有」与「源没通」")
ok(S["sbom_passed"] == _N_IMG, f"sbom 应 {_N_IMG} 个镜像全通过")
ok(S["mutation_skipped"] == 1, "变异测试有 1 条跳过（mtab），正文必须交代")
in_text("1 跳过", label="变异跳过项")
ok(S["masked_units_by_distro"]["kylin10"] != S["masked_units_by_distro"]["kylin11"],
   "masked 单元数应随发行版而变（正文不得写死一个数）")

# ── README 也要被核对（它承载十条主要结论，读者多半只看它）──────────────────
# README 的可装性表用「N / 14」形式写，必须按这个形状断言 —— 只找裸数字会漏
# （分析层变异测试实测：把 README 的 **0 / 14** 改成 **9 / 14** 曾经抓不到）。
# ⚠️ ctx 必须把**主体**和数字绑在一起，只绑「数字↔短语」挡不住归属对调：
# 把「麒麟 14/14、UOS 0/14」整体换成「UOS 14/14、麒麟 0/14」，两个数都还在、
# 两个模式都能匹配，而本仓库最硬的一条定量结论就被反转了（审稿实测全绿）。
_T = S["installability_tools"]
in_text(S["installable_uos25"], where="readme", label="README 可装性三家归属",
        ctx=rf"麒麟 V11 \*\*{S['installable_kylin11']} / {_T}\*\*、麒麟 V10 "
            rf"\*\*{S['installable_kylin10']} / {_T}\*\*、UOS V25 \*\*{S['installable_uos25']} / {_T}\*\*")
in_text(S["installable_uos25"], where="report", label="report 可装性三家归属",
        ctx=rf"\*\*{S['installable_kylin11']} / {_T}\*\* \| \*\*{S['installable_kylin10']} / {_T}\*\* \| "
            rf"\*\*{S['installable_uos25']} / {_T}\*\*")
in_text(S["uos_iso_packages"], where="readme", label="README 的 UOS ISO 包数")
for row in (ROOT / "derived" / "tables" / "t04_built_images.csv").read_text().splitlines()[1:]:
    c = row.split(",")
    in_text(f"{c[3]} MB / {c[5]} 包", where="readme", label=f"README 九镜像表 {c[0]}:{c[1]}",
            ctx=re.escape(f"{c[3]} MB / {c[5]} 包"))

# ── 厂商缺陷 ────────────────────────────────────────────────────────────────
# 台账条数从按发行版的分布现算，不写死 —— 写死的数在加缺陷或加被试时必然失真。
ok(S["defects"] == sum(S["defects_by_distro"].values()),
   f"厂商缺陷条数应与台账一致：defects={S['defects']}，按发行版分布合计"
   f"={sum(S['defects_by_distro'].values())}")
in_text(S["defects"], label="缺陷条数")
t8 = (TAB / "t08_vendor_defects.csv").read_text().splitlines()
ok(len(t8) - 1 == S["defects"], "t08 行数应等于缺陷数")
# 早先写成 `d in REPORT or d in t8[0] or any(d in l for l in t8)` —— t08 按构造必然
# 含每个 D**，第三支恒真，这 7 条断言零鉴别力（实测删光正文里的 D05 引用也全绿）。
# 改成只查正文：被正文讨论过的缺陷 ID 才算「有交代」。
for d in ("D01", "D02", "D05", "D08", "D09", "D10", "D12"):
    ok(d in BODY, f"缺陷 {d} 应在正文里被讨论（只在表里不算）")

# ── 覆盖 review 点名的零覆盖数字（都带上下文，避免裸子串撞车）──────────────
for d, n in S["masked_units_by_distro"].items():
    nm = {"kylin10": "麒麟 V10", "kylin11": "麒麟 V11", "uos25": "UOS",
          "kylinsec6": "麒麟信安", "linx6": "凝思"}[d]
    # 同样要绑主体：只防数字边界挡不住「V11 与 UOS 各 11 个、V10 是 7 个」这种对调
    # 正文的写法是「麒麟 V10 三档均为 11 个」与「麒麟 V11 与 UOS 的 base/devel 各 7 个」，
    # 主体与数字之间隔着「三档均为」「的 base/devel 各」这类词，放宽到同句内即可，
    # 但必须同句 —— 只防数字边界挡不住整体对调。
    ok(re.search(rf"{nm}[^。；]{{0,24}}?(?<![0-9]){n} 个", REPORT) is not None,
       f"正文应把 {nm} 与它的 masked 单元数 {n} 写在同一句里（防归属对调）")
in_text(S["setuid_micro"]["kylin10"], label="V10 micro 的 setuid 数",
        ctx=rf"V10 micro 档有 {S['setuid_micro']['kylin10']} 个")
in_text(S["setuid_micro"]["kylin11"], label="micro 的 setuid 数",
        ctx=rf"各只有 {S['setuid_micro']['kylin11']} 个 setuid")
in_text(S["cells_supported"], label="支持格数", ctx=rf"支持 {S['cells_supported']}、")
in_text(S["cells_gap"], label="缺口格数", ctx=rf"缺口 {S['cells_gap']}、")
in_text(S["cells_na"], label="不适用格数", ctx=rf"不适用 {S['cells_na']}")
in_text(S["mutation_caught"], label="变异用例数", ctx=rf"变异用例 \*\*{S['mutation_caught']}\*\*（镜像层）")

# README 抬头的各项计数
for v, lbl, ctx in [
    (S["images_built"], "构建镜像数", r"构建镜像 \*\*{v}\*\* 个"),
    (len(S["build_methods"]), "构建路径数", r"构建路径 \*\*{v}\*\* 条"),
    (S["capability_cells"], "能力矩阵格数", r"能力矩阵 \*\*{v}\*\* 格"),
    (S["defects"], "缺陷条数", r"厂商缺陷留档 \*\*{v}\*\* 条"),
]:
    in_text(v, where="readme", label=f"README {lbl}", ctx=ctx.replace("{v}", str(v)))
    in_text(v, where="report", label=f"report {lbl}", ctx=ctx.replace("{v}", str(v)))

# ── README 抬头与结论表的逐项覆盖 ────────────────────────────────────────────
# README 是「读者多半只看的那份」，此前它抬头的验收断言数、三态分布、门禁表、
# 结论表里的关键数字全部零覆盖 —— 改成任意值都全绿。全部带上下文断言。
for v, ctx, lbl in [
    (S["verify_passed"], r"验收断言 \*\*{v}\*\* 条", "README 验收断言数"),
    (S["cells_supported"], r"支持 {v} 格", "README 支持格数"),
    (S["cells_gap"], r"缺口 {v} 格", "README 缺口格数"),
    (S["cells_na"], r"不适用 {v} 格", "README 不适用格数"),
    (S["capability_items"], r"{v} 项 × %d 镜像" % S["images_built"], "README 能力项数"),
    (S["verify_passed"], r"{v} 通过 / 0 失败", "README 门禁表 verify"),
    (S["verify_baseline"], r"基线 {v}", "README 门禁表基线"),
    (S["digest_chain_passed"], r"\| {v} / %d \|" % _N_IMG, "README 门禁表 digest"),
    (S["mutation_caught"], r"{v} 抓到 / 0 漏", "README 门禁表 mutation"),
    (S["repro_identical"], rf"{{v}} / {_n_repro} 逐位一致", "README 门禁表 repro"),
    (S["census_probes"], r"{v} 个候选引用实测", "README 结论 3 的实测引用数"),
    (S["census_os_count"], r"名录 {v} 个 OS", "README 结论 3 的名录规模"),
    (S["uos_iso_packages"], r"ISO（{v} 个包）", "README 结论 5 ISO 包数"),
]:
    in_text(v, where="readme", label=lbl, ctx=ctx.replace("{v}", str(v)))
# 官方镜像的 glibc 全版本号必须原样出现（此前改成 2.99-fake 也全绿）
_off = [r for r in (TAB / "t03_product_line_comparison.csv").read_text().splitlines()
        if r.startswith("厂商官方")][0].split(",")
ok(_off[6] in README and _off[6] in REPORT, f"官方镜像 glibc {_off[6]} 应在正文与 README 出现")
ok(_off[5] in README, f"官方镜像包格式 {_off[5]} 应在 README 出现")

# ── 漏洞扫描覆盖（十条主要结论里唯一涉及安全判断的一条，必须有凭据）──────────
ok(S["cve_effective_coverage"] == 0, "三个发行版应无一有效的漏洞库覆盖")
# 「有效覆盖 0」是十条结论里唯一涉及安全判断的数字，必须在两份文档里都被逐字校验
in_text(S["cve_effective_coverage"], label="report 有效覆盖数",
        ctx=rf"\*\*有效覆盖 {S['cve_effective_coverage']} 个\*\*")
in_text(S["cve_effective_coverage"], where="readme", label="README 有效覆盖数",
        ctx=rf"{_N_IMG} 个镜像有效覆盖 {S['cve_effective_coverage']} 个")
# 结论标题的极性也要钉住，避免整句被反转
ok("没有有效覆盖" in README and "没有有效覆盖" in REPORT,
   "「通用扫描器没有有效覆盖」这句判断应在两份文档里原样存在")
ok(S["cve_unrecognized"] + S["cve_misidentified"] == _N_IMG,
   f"全部 {_N_IMG} 个镜像应落在未识别或误判两类里，实际 {S['cve_unrecognized']}+{S['cve_misidentified']}")
in_text(S["cve_misidentified"], label="被误判的镜像数", ctx=rf"误判 {S['cve_misidentified']} 个")
in_text(S["cve_unrecognized"], label="未识别的镜像数", ctx=rf"未识别 {S['cve_unrecognized']} 个")
# 「报 0 个 HIGH/CRITICAL」这句必须是实测而非推断
# 加入凝思后总数不再是 0：它被判成 debian 10.6 且标 EOSL，三档报出非零 HIGH+CRITICAL。
# 「报 0」这个判断只对被误判成 Debian 的麒麟 V10 与 UOS 六档成立，判据因此收窄到那六档 ——
# 笼统断言总数为 0 会在有真数字时失败，而那个数字恰恰是有信息量的（见 §9.1）。
_zero_six = [i for i in json.loads((ROOT / "raw" / "d7_cve.json").read_text())["images"]
             if i["distro_id"] in ("kylin10", "uos25")]
ok(all(i["high_critical"] == 0 for i in _zero_six),
   f"麒麟 V10 与 UOS 六档应报 0 个 HIGH/CRITICAL（正文据此论证「比不出来」），"
   f"实际 {[(i['image'], i['high_critical']) for i in _zero_six if i['high_critical']]}")

# ── 信任根（本轮把「最小信任集」当成了结论，就必须有断言守住）────────────────
_keys = sorted(p.name for p in (ROOT / "keys").glob("*.gpg"))
ok(_keys == ["kylin-archive-keyring.gpg"],
   f"keys/ 应只含最小信任集的单一 keyring，实际 {_keys}")
import subprocess as _sp
_fp = _sp.run(f"gpg --show-keys --with-colons {ROOT}/keys/kylin-archive-keyring.gpg",
              shell=True, capture_output=True, text=True).stdout
# ⚠️ 数 key 要数 pub: 行。--with-colons 的 fpr: 行**把子密钥也算进去**，
# 用它计数会把「一把带子密钥的 key」误报成两把（本断言首版就这么误报过）。
_pubs = [l for l in _fp.splitlines() if l.startswith("pub:")]
_fps = [l.split(":")[9] for l in _fp.splitlines() if l.startswith("fpr:")]
ok(len(_pubs) == 1, f"keyring 里应只有一把主密钥，实际 {len(_pubs)} 把 —— 多一把就是多一份授权")
if _fps:
    _spaced = " ".join(_fps[0][i:i+8] for i in range(0, 40, 8))
    ok(_spaced in REPORT, f"§3.1 记录的指纹应与 keyring 实际指纹逐字符相符（{_spaced}）")

# 镜像层的信任面：UOS 走切片路径、信任根是 ISO，不该出现麒麟的 keyring。
# 仓库层的 keys/ 断言看不到这件事 —— 门禁自己又需要一层门禁。
# 判据已从「UOS 里混进麒麟 key」通用化为「keyring 的厂商标识不属于本发行版」，
# 失败消息也要跟着通用 —— 原措辞会把凝思的问题说成 UOS 的。
ok(S["alien_keyring_images"] == [],
   f"这些镜像里出现了不属于本发行版的 keyring：{S['alien_keyring_images']}")
# 按**档位**判，不只按发行版：micro 档没有 apt，写 sources.list 再塞 keyring 是纯冗余，
# 所以它应当两者皆空；base/devel 走在线源，需要且只需要麒麟那一把。
# 哪几家出厂时需要麒麟那把 keyring，从 distros/*.conf 现算而不是按名字前缀猜：
# 只有「出厂源是网络源、且要验签」的路径才用得上它。先前判据写的是
# `d.startswith("kylin")`，把 rpm 系的麒麟信安一起圈了进来 —— 它连 apt 都没有，
# 名字撞上而已，那两格必然为空却被要求有一把 key。
def _conf_val(did, key):
    _m = re.search(rf"^{key}=(\S*)", _CONF_TXT.get(did, ""), re.M)
    return _m.group(1).strip('"') if _m else ""
_CONF_TXT = {f.stem: f.read_text() for f in (ROOT / "distros").glob("*.conf")}
_NEEDS_KEYRING = {d for d in DIDS
                  if _conf_val(d, "MIRROR").startswith(("http://", "https://", "ftp://"))
                  and _conf_val(d, "NO_CHECK_GPG") != "yes"}
ok(_NEEDS_KEYRING == {d for d in DIDS if FAMILY[d] == "deb"
                      and _conf_val(d, "MIRROR").startswith("http")},
   f"需要 keyring 的被试只能是走网络源验签的那几家，实际 {sorted(_NEEDS_KEYRING)}")
# 我们注入了什么，同样由构建路径推导。selfhost-inner.sh 那句
# `cp /keys/kylin-archive-keyring.gpg` 是无条件的：麒麟 V10 走这条路，但那把 key 在
# V10 属厂商 kylin-keyring 包，按属主判不算注入；凝思走同一条路、介质源无签名用
# trusted=yes，它的 linx-keyring 包里只有 linx-archive-keyring.gpg（凭据
# artifacts/linx-keyring-deb-contents.txt），于是那把 kylin 的无属主、也无人读，
# 三档各多一份用不上的授权。这是一处已出厂的构建缺陷，§3.1 有记录。
# 判据不放宽成「随便注入什么都行」，而是钉成逐镜像的**逐字相等**：多注入一把、
# 例外扩散到别的被试、或哪天构建修好了这里没跟着改，都会失败。
# 缺陷 D20 已修：拷 keyring 之前先判 NO_CHECK_GPG，所以**任何被试都不该有注入**。
# 期望从「无签名路径允许一把麒麟 key」翻转成「一律为空」——判据仍是逐镜像逐字相等，
# 多注入一把、或哪天那句无条件 cp 被改回来，都会失败。
_INJ_EXPECT = {d: [] for d in DIDS}
for k, v in S["keyrings_by_image"].items():
    d, t = k.split(":")
    # 只约束**我们注入的**那些。麒麟 V10 的 micro 档带的那把属厂商 kylin-keyring 包，
    # 是发行版自带内容，删它就越过了「等价环境」的底线 —— 用属主区分，不一刀切。
    inj = S["injected_keyrings_by_image"].get(k, [])
    ok(inj == _INJ_EXPECT[d],
       f"{k} 注入的 keyring 应为 {_INJ_EXPECT[d]}，实际 {inj}")
    if t == "micro":
        nb = S["micro_sources_list_bytes"].get(k)
        ok(nb == 0, f"{k} 没有 apt，出厂的 sources.list 应为空，实际 {nb} 字节")
        # 真正该数的是 active deb 行数：源清单可以在 sources.list.d/ 下，
        # 只量 sources.list 会漏掉（uos25:micro 曾因此带着一条 appstore 源全绿）。
        ad = S["micro_active_deb_lines"].get(k)
        ok(ad == 0, f"{k} 没有 apt，不该出厂任何 active 在线源，实际 {ad} 条 deb 行")
    elif d in _NEEDS_KEYRING:
        ok(v == ["kylin-archive-keyring.gpg"],
           f"{k} 的 keyring 应只有 kylin-archive-keyring.gpg，实际 {v}")
# 注入例外必须在**§3.1 那一节之内**有交代 —— 没有这条，上面那份「逐字相等」就成了
# 把缺陷写进门禁。范围必须限定到本节：被试短名在全文出现上百次，查「名字在正文里」
# 是永真的，那正是本仓库反复踩的那种零鉴别力判据。
_S31 = REPORT[REPORT.index("### 3.1"):REPORT.index("## 4. 四条构建路径")]
# D20 修好之后，§3.1 该讲的不再是「一处例外」而是「这个缺陷怎么来的、怎么修的」。
# 仍要求本节之内有交代 —— 否则「零注入」这条断言就成了没有来历的硬约束。
# 范围限定到本节：被试短名在全文出现上百次，查「名字在正文里」是永真判据。
ok("D20" in _S31 or "NO_CHECK_GPG" in _S31,
   "§3.1 必须交代 keyring 注入是按 NO_CHECK_GPG 判的（否则「零注入」无从复核）")
ok(SHORT["linx6"] in _S31,
   "§3.1 必须点名凝思：那把用不上的 keyring 曾经出现在它三档里")
for _d in DIDS:
    for _t in T_LIST:
        _got = S["injected_keyrings_by_image"].get(f"{_d}:{_t}")
        ok(_got == [], f"{_d}:{_t} 不该由构建注入任何 keyring，实际 {_got}")

# d6/d7 的被测镜像必须与 d2 的产物同一批，否则那两组结论锚在旧镜像上
# d6/d7 的锚点对账。本轮有六条对不上，成因已定位，逐条写在 §9.1：d7 停在
# 2026-08-30 那轮、只覆盖首轮三个被试；d6 采于 2026-08-31，麒麟信安与凝思两条
# 没有锚点字段；UOS 三档在这两轮采集之后又重建过（micro 档的源清单与 keyring 修正
# 改了内容），两处记录因此指向上一版产物。判据不放宽成「允许有漂移」——那等于把
# 这条对账关掉——而是钉成逐字相等的清单，外加正文逐镜像点名：新出现一处、消失一处、
# 或换成别的镜像，都会失败。
# d6/d7 重采之后锚点已全部对齐，漂移清零。判据因此从「与已披露的漂移清单逐字相等」
# 改为「必须为空」—— 更严，不是更松：新出现任何一处漂移都会失败。
# 对数只允许涨：d6 与 d7 都补齐锚点后从 12 对涨到 20 对，掉下来就是有对账被静默跳过。
ok(S["anchor_mismatches"] == [],
   f"d6/d7 的锚点必须与 d2 的产物完全对齐，实际漂移 {S['anchor_mismatches']}")
ok(S["anchored_records"] >= 12, f"d6/d7 应有锚点的记录数过少：{S['anchored_records']}")
ok(S["anchor_pairs_checked"] >= 12,
   f"实际比过的锚点对数只允许涨（基线 12），实际 {S['anchor_pairs_checked']} —— 少了就是有对账被静默跳过")
ok(S["micro_active_deb_missing"] == [],
   f"这些 micro 档的 active_deb_lines 字段没采到（缺键会让断言空转）：{S['micro_active_deb_missing']}")
ok(len(S["micro_active_deb_lines"]) == len(DIDS),
   f"{len(DIDS)} 个 micro 档都应有 active_deb_lines，实际 {len(S['micro_active_deb_lines'])}")
ok(S["image_id_mismatches"] == [],
   f"这些镜像的当前 ID 与 manifest 记录不符（采集之后又重建了）：{S['image_id_mismatches']}")
ok(S["digest_log_prefixes_checked"] == _N_IMG,
   f"应从 f4-digest.log 抽出 {_N_IMG} 条 sha256 前缀对账，实际 {S['digest_log_prefixes_checked']}")
ok(S["anchor_bad_hex"] == [], f"d2 的 tar_sha256 必须都是 64 位 hex，异常：{S['anchor_bad_hex']}")

# ── 结构性检查 ──────────────────────────────────────────────────────────────
# 图表引用只查**正文**：附录 A/B 是完整索引，若把附录算进来，这条断言永不失败
# —— 它以为自己在防「图表没人引用」，实际什么也没防（实测 fig06 与 5 张表只在索引里）。
for fig in sorted((ROOT / "figures").glob("*.png")):
    ok(fig.name in BODY, f"图 {fig.name} 只在附录索引里，正文未引用")
for tab in sorted(TAB.glob("*.csv")):
    ok(tab.stem.split("_")[0] in BODY or tab.name in BODY,
       f"表 {tab.name} 只在附录索引里，正文未引用")
for p in ["build/build.sh", "build/build-selfhost.sh", "tools/slice.py",
          "lib/common.sh", "test/capabilities.sh", "test/verify.sh", "Makefile"]:
    ok((ROOT / p).exists(), f"复现所需的 {p} 缺失")
# 仓库不许带镜像与 ISO
for pat in ("*.tar", "*.iso", "*.squashfs"):
    found = [p for p in ROOT.rglob(pat) if ".git" not in p.parts]
    ok(not found, f"仓库不应包含 {pat}：{[str(x) for x in found[:3]]}")
# 自然段内不硬换行：正文里不应出现「上一行以中文结尾、下一行紧接中文」的硬折
# 行尾判据要含中文标点：最常见的折行点是逗号顿号而不是汉字（实测行尾全角逗号漏检）。
# 两份文档都要查 —— 早先只查了 report。
for _name, _txt in (("report.md", REPORT), ("README.md", README)):
    _L = _txt.splitlines()
    hard = [i for i, l in enumerate(_L[:-1], 1)
            if re.search(r"[一-鿿，、；：）】」》]$", l)
            and not l.startswith(("|", "-", ">", "#", " ", "`", "*"))
            and re.match(r"^[一-鿿（【「《]", _L[i] or " ")]
    ok(not hard, f"{_name} 自然段内疑似硬换行，行号：{hard[:5]}")

# 断言自计数。早先版本只检查「这句话存在」，捕获了数字却从不比对 ——
# 把抬头的 365 改成 99999 照样全绿。那是本仓库 §9.2 自己批判的第三类假通过。
m = re.search(r"验收断言 \*\*(\d+)\*\* 条", REPORT)
ok(m is not None, "report.md 抬头应声明验收断言条数")
if m:
    ok(int(m.group(1)) == S["verify_passed"],
       f"抬头的验收断言数 {m.group(1)} 应等于 stats 里的 verify_passed {S['verify_passed']}")
mr = re.search(r"机器核对断言 \*\*(\d+)\*\* 条", README)
ok(mr is not None, "README 抬头应声明机器核对断言条数")

# ── 归因绑定：小整数在正文里出现上百处，裸 in_text 等于没查 ──────────────
# 每个数必须绑到它所论断的那一句上，否则改坏了也能在别处蒙到同样的数字。
ok(S["existence_probes"] == 8, "存在性探测应为 8 条")
in_text(S["existence_probes"], label="存在性探测条数",
        ctx=rf"另一组 {S['existence_probes']} 条是针对桌面 tag 的存在性探测")
ok(S["existence_found"] == 1, "8 条探测里应只有 1 条拉得到")
in_text("kylin/kylin-server-minimal:v10sp1", label="唯一拉得到的那条要写明是哪条",
        ctx=r"唯一拉得到的是 `kylin/kylin-server-minimal:v10sp1`")
ok(S["official_pkg_format"] == "rpm", "麒麟官方镜像应为 rpm 系")
in_text(S["official_pkg_format"], label="官方镜像包格式",
        ctx=rf"\*\*{S['official_pkg_format']}\*\*（\d+ 个包）")
ok(S["os_id_collision"] is True, "两条产品线的 os-release ID 应确实撞名（这是全文最易被质疑处）")
ok(S["kylin_desktop_official_images"] == 0, "麒麟桌面线官方镜像应为 0 个")
ok(S["uos_official_images"] == 0, "UOS 官方桌面镜像应为 0 个")
# 两个数从 d7 现算，不写死。加入 rpm 系被试后未识别由 3 变 6（麒麟信安三档也是
# Family:none），误判由 6 变 9（凝思三档被判成 debian 10.6）。写死的数在被试增加后
# 会把正确的数据判成错误。
ok(S["cve_unrecognized"] + S["cve_misidentified"] + S["cve_effective_coverage"] == _N_IMG,
   f"三种判定之和应等于镜像数 {_N_IMG}，实际 "
   f"{S['cve_unrecognized']}+{S['cve_misidentified']}+{S['cve_effective_coverage']}")
ok(S["cve_effective_coverage"] == 0,
   f"有效覆盖应为 0（正文据此论证扫描器不可用），实际 {S['cve_effective_coverage']}")
in_text(S["cve_unrecognized"], label="CVE 未识别数",
        ctx=rf"未识别 {S['cve_unrecognized']} 个")
in_text(S["cve_misidentified"], label="CVE 误判数",
        ctx=rf"误判 {S['cve_misidentified']} 个")
ok(len(S["uos_iso_missing"]) == 6, "UOS ISO 缺的构建工具应为 6 个")
for _t in S["uos_iso_missing"]:
    in_text(_t, label=f"UOS ISO 缺失工具 {_t} 应在正文列出")

# 同一个区间在 report 与 README 各写一份，实测已经漂过一次
# （report 改成 37.9%–46.9% 之后 README 还留着抹平的 38%–47%）。两份都绑。
in_text(S["unpack_overhead_pct_min"], where="readme", label="README 解包开销下界",
        ctx=r"实测 %s%%–" % S["unpack_overhead_pct_min"])
in_text(S["unpack_overhead_pct_max"], where="readme", label="README 解包开销上界",
        ctx=r"–%s%%，分母用 tar 精确字节" % S["unpack_overhead_pct_max"])

# README 里指向 report.md 的章节锚点：改标题会无声断链，发布页上直接点不动。
# 按 GitHub 的规则本地生成 anchor（小写、去标点、空格转连字符）再比对。
# 实测过 GitHub 确实把「」与 ASCII 引号一样剥掉（curl 渲染页核过 user-content-* id）。
def _gh_anchor(title):
    t = title.strip().lower()
    t = re.sub(r"[^\w\u4e00-\u9fff \-]", "", t)   # 保留字母数字下划线、CJK、空格、连字符
    return t.replace(" ", "-")

_heads = {_gh_anchor(m.group(1)) for m in re.finditer(r"^#{2,4}\s+(.+)$", REPORT, re.M)}
_refs = set(re.findall(r"report\.md#([^\)\s]+)", README))
_dead = sorted(_refs - _heads)
ok(_dead == [], f"README 指向 report.md 的章节锚点必须都存在（断链：{_dead}）")
ok(len(_refs) >= 7, f"README 应至少有 7 个 report 章节锚点，实际 {len(_refs)}")

# ── §2 名录：这一节的立论基础是「每条信息都有出处」，必须硬守 ──────────────
ok(S["census_present"] is True, "名录数据集 d8 必须存在")
ok(S["census_entries_without_source"] == [],
   f'名录里不许有缺出处的条目（缺：{S["census_entries_without_source"]}）')
ok(S["census_os_count"] == S["census_commercial"] + S["census_community"],
   "名录的商业/社区分类必须覆盖全部条目，不能有条目落在两类之外")
in_text(S["census_os_count"], label="名录 OS 总数",
        ctx=rf"名录含 \*\*{S['census_os_count']} 个\*\* OS")
in_text(S["census_commercial"], label="名录商业型个数",
        ctx=rf"商业 \*\*{S['census_commercial']} 个\*\*")
in_text(S["census_community"], label="名录社区型个数",
        ctx=rf"社区开源 \*\*{S['census_community']} 个\*\*")
in_text(S["census_probes"], label="名录实测引用数",
        ctx=rf"{S['census_probes']} 个引用中")
in_text(S["census_probes_exist"], label="名录实测存在数",
        ctx=rf"个引用中 {S['census_probes_exist']} 个存在")
# 「桌面命名的引用一条都不存在」是本节的核心结论，单独绑
_desk = [p for p in json.loads((ROOT / "raw" / "d8_os_census.json").read_text())["probes"]
         if any(k in p["ref"] for k in ("desktop", "ukui", "dde"))]
ok(len(_desk) == 13, f"桌面命名引用应为 13 条，实际 {len(_desk)}")
ok(all(not p["exists"] for p in _desk), "桌面命名引用必须全部匿名拉不到（本节核心结论）")
in_text("13 条", label="桌面命名引用条数",
        ctx=r"共 13 条，跨 3 家 registry")
# 结论已按证据强度改写：24 条负判里 18 条是 unauthorized（匿名不可见），
# 只有 5 条是真 not found。所以这句从「不存在」降为「不能匿名获取」。
in_text("一条都不能匿名获取", label="桌面命名引用匿名不可得这句结论")
# DevStation 那两个体积是本节唯一的一手数字，写死在正文里，必须与实测一致
in_text("2066238156", label="DevStation rootfs 字节数")
in_text("43690908", label="openEuler 基础镜像 rootfs 字节数")

# §2.2 的 registry 枚举是本节最强的一格证据（从「我们拉不到」升级为「厂商库里没有」），
# 两家的枚举结论各绑一次；代理陷阱那条方法学提醒也绑，它决定了别人复现时会不会得出反结论。
in_text("27", label="麒麟 kylin 项目仓库数", ctx=r"kylin\(27\)")
in_text("0 个", label="麒麟 registry 零桌面", ctx=r"含 desktop 或 ukui 的：0 个")
in_text("18 个公开项目", label="统信 registry 项目数",
        ctx=r"\*\*18 个公开项目，含 `desktop`/`dde`/`ukui` 的 0 个\*\*")
in_text("uos-server-base", label="统信基础镜像项目名")
ok("--noproxy" in REPORT, "代理陷阱那条方法学提醒必须在正文里（决定复现者会不会得出反结论）")
in_text("000", label="代理下的假不可达", ctx=r"经代理访问时\*\*都返回 000\*\*")
# 名录里「官方未声明血统」的家数是正文的一个论断，从名录现算而不是手写
# 剔除项与小型社区两个清单的条数也绑，避免悄悄增删
_cen = json.loads((ROOT / "config" / "os_census.json").read_text())
in_text(len(_cen["scope"]["exclusions"]), label="剔除项条数",
        ctx=rf"剔除 {len(_cen['scope']['exclusions'])} 项")
in_text(len(_cen["scope"]["small_community"]), label="小型社区条数",
        ctx=rf"另有 {len(_cen['scope']['small_community'])} 个\*\*小型社区发行版")

# §2.1 的 ★ 被试标记与 §2.4 的选型论证：名录必须真的标出被试，
# 且被试必须与我们实际构建的镜像对得上（否则名录与后文脱节，审稿时正好挑这个）。
# 名录按产品线列而被试按 ISO 算：银河麒麟一条覆盖 V10 SP1 与 V11 两个被试，
# 所以标记数是「被试数 − 1」而非被试数（§2.1 那句说明也是这么写的）。
ok(len(S["census_subjects"]) == len(DIDS) - 1,
   f'名录里应有 {len(DIDS) - 1} 个被试标记（银河麒麟一条覆盖两个被试），实际 {S["census_subjects"]}')
ok(any("麒麟" in x for x in S["census_subjects"]) and any("UOS" in x for x in S["census_subjects"]),
   "被试标记必须落在银河麒麟与统信 UOS 上")
# 被试与 t04 里实际构建的三个镜像的发行版必须一致
_built = {r["distro"] for r in [dict(zip(*[iter([])]))] } if False else set(
    l.split(",")[0] for l in (TAB / "t04_built_images.csv").read_text().splitlines()[1:] if l)
ok(_built == set(DIDS),
   f"实际构建的发行版应为 {'/'.join(DIDS)}，实际 {sorted(_built)}")
in_text("★ 标记的四个条目是本项目被试的来源", label="名录里说明 ★ 含义")
# ★ 行数与被试数**不相等**，因为名录按产品线列而被试按 ISO 算：银河麒麟一条
# 覆盖 V10 SP1 与 V11 两个被试。所以锚的是产品线条目数（5 个被试 - 1 个合并 = 4）。
# 这条断言在写下「五个」的当次就否掉了它，两种粒度混用是本仓库反复出的错。
_n_star = REPORT.count("\n| ★ |")
ok(_n_star == len(DIDS) - 1,
   f"名录 ★ 行数应为 {len(DIDS) - 1}（被试 {len(DIDS)} 个，银河麒麟两个被试共用一条名录条目），实际 {_n_star}")
in_text("银河麒麟桌面 V10 SP1、银河麒麟桌面 V11、统信 UOS V25", label="§2.4 点明首轮三个被试 ISO")
in_text("麒麟信安桌面 V6", label="§2.4 点明第二轮被试之一")
in_text("凝思安全操作系统 V6.0.100", label="§2.4 点明第二轮被试之二")
ok("材料可得性" in REPORT,
   "ISO 授权这条限制必须如实写成材料可得性，不许包装成技术理由")

# ── 引用体系：论文式 cite 的要求是双向闭合 ────────────────────────────────
# ① 正文/名录里出现的每个 [Rn] 都必须在参考来源表里有条目（否则是假引用）；
# ② 参考来源表里的每条都必须至少被引用一次（否则是凑数的参考文献）；
# ③ 每条引用必须标明标题是抓自页面还是人工标注 —— 后者的标题不是原文，
#    混在一起会让读者把我们写的描述当成该页的正式名称。
_REFS = json.loads((ROOT / "config" / "references.json").read_text())["references"]
_ref_ids = {r["id"] for r in _REFS}
ok(len(_ref_ids) == len(_REFS), "参考来源编号不许重复")
ok(S["references_total"] == len(_REFS), "stats 里的引用总数应与 config 一致")
ok(S["references_title_from_page"] + S["references_title_manual"] == len(_REFS),
   "每条引用都必须标明标题来源（page 或 manual），不许有第三种或缺失")
ok(all(r.get("url", "").startswith("http") for r in _REFS), "每条引用必须有 URL")
ok(all(r.get("accessed") for r in _REFS), "每条引用必须有访问日期")

# GitHub 原生脚注：引用处是 [^Rn]，定义处是行首 [^Rn]:。两者要分开数 ——
# 只有定义没有引用，GitHub 根本不渲染那条；只有引用没有定义，渲染成死链。
_cited_in_text = set(re.findall(r"\[\^(R\d+)\](?!:)", REPORT))
_defined = set(re.findall(r"^\[\^(R\d+)\]:", REPORT, re.M))
_cited_in_census = {i for e in json.loads((ROOT / "raw" / "d8_os_census.json").read_text())["entries"]
                    for v in e.get("refs", {}).values() for i in v}
_all_cited = _cited_in_text | _cited_in_census
ok(S["census_dangling_refs"] == [],
   f'名录里不许有悬空引用（悬空：{S["census_dangling_refs"]}）')
_dangling_text = sorted(_cited_in_text - _ref_ids)
ok(_dangling_text == [], f"正文里不许有悬空引用（悬空：{_dangling_text}）")
_unused = sorted(_ref_ids - _all_cited, key=lambda x: int(x[1:]))
ok(_unused == [], f"参考来源表里不许有从未被引用的条目（未引用：{_unused[:12]}）")
ok(S["census_field_citations"] >= 90,
   f'名录的字段级引用应不少于 90 处，实际 {S["census_field_citations"]}')
# 名录表里每个 OS 至少要有一处字段级引用，不许有整行裸奔
_no_ref = [e["name"] for e in json.loads((ROOT / "raw" / "d8_os_census.json").read_text())["entries"]
           if not e.get("refs")]
ok(_no_ref == [], f"名录里每个 OS 都必须至少有一处字段级引用（缺：{_no_ref}）")
# 引用形态必须是 GitHub 原生脚注：每条被引用的都要有定义，每条定义都要被引用，
# 否则 GitHub 侧渲染出来是死链或干脆不显示。
ok(_defined == _ref_ids,
   f"脚注定义必须与引用表一一对应（多出：{sorted(_defined - _ref_ids)[:8]}；"
   f"缺少：{sorted(_ref_ids - _defined)[:8]}）")
_undef = sorted(_cited_in_text - _defined, key=lambda x: int(x[1:]))
ok(_undef == [], f"正文引用的每个脚注都必须有定义（缺定义：{_undef[:8]}）")
ok(not re.search(r"\[R\d+\]\(#R\d+\)", REPORT),
   "不许残留手写锚点式引用（已统一为 GitHub 原生脚注 [^Rn]，两套并存会让编号对不上）")
ok(len(_cited_in_text) >= 20,
   f"正文里的脚注引用应不少于 20 处，实际 {len(_cited_in_text)}")
in_text(S["references_total"], label="正文写明的引用条数",
        ctx=rf"共 {S['references_total']} 条")
in_text(S["census_field_citations"], label="正文写明的字段级引用处数",
        ctx=rf"共 {S['census_field_citations']} 处字段级引用")

# ── ISO 获取列：三分类必须齐全，「未实测」不许被并进「可下载」──────────────
# 把「查不到」写成「有」正是 §9.2 批判过的错法，这里用断言把它钉住。
ok(S["iso_access_missing"] == [],
   f'名录里每个 OS 都必须有 ISO 获取一列（缺：{S["iso_access_missing"]}）')
ok(S["iso_class_unknown"] == [],
   f'ISO 获取必须用受控取值（越界：{S["iso_class_unknown"]}）—— 自由文本当分类会让条目被算进两类')
ok(len(S["iso_direct"]) + len(S["iso_public_unresolved"]) + len(S["iso_netdisk"])
   + len(S["iso_gated"]) + len(S["iso_not_found"]) + len(S["iso_unverified"])
   == S["census_os_count"],
   "ISO 获取的各分类必须恰好覆盖全部条目，既不重复也不遗漏")
# 「未查到」与「需授权」必须分开：前者是我们找不到条目，后者是看到了门槛。
# 复核后 5 家从「需授权」翻成「直接下载」，正是因为当初把「代理打成 000」当成了门槛。
ok(len(S["iso_not_found"]) + len(S["iso_unverified"]) > 0,
   "「未查到/未实测」这两类不许同时为空 —— 清空等于粉饰")
ok(S["customers_missing"] == [],
   f'名录里每个 OS 都必须有客户与场景一列（缺：{S["customers_missing"]}）')
# 安可桌面附表在列的家数由名录现算并与 §2.4 的选型对账 ——
# 这是「交付端需求」这条判据的第三方背书，不许悄悄变。
ok(len(S["aqkk_desktop_listed"]) == 3,
   f'安可桌面附表在列应为 3 家，实际 {S["aqkk_desktop_listed"]}')
ok(set(S["aqkk_desktop_listed"]) == {"银河麒麟桌面操作系统", "统信桌面操作系统 V25（UOS）",
                                     "方德桌面操作系统 V5.0"},
   f'安可在列的三家应为银河麒麟/统信/方德，实际 {S["aqkk_desktop_listed"]}')
ok("Google Chromebook 的海外案例" in REPORT,
   "FydeOS 那个易被误读的案例陷阱必须写明")
ok("图形工作站席位" in REPORT,
   "凝思的「桌面」实为调度席位这一区分必须写明，否则会被当成通用办公 PC")

in_text(len(S["iso_direct"]), label="ISO 直接下载家数",
        ctx=rf"\*\*直接下载 {len(S['iso_direct'])} 家\*\*")
in_text(len(S["iso_gated"]), label="ISO 需授权家数",
        ctx=rf"需申请授权或登录 \*\*{len(S['iso_gated'])} 家\*\*")
in_text(len(S["iso_unverified"]), label="ISO 未实测家数",
        ctx=rf"未实测 {len(S['iso_unverified'])} 家")
in_text(len(S["iso_not_found"]), label="ISO 未查到家数",
        ctx=rf"未查到公开下载 {len(S['iso_not_found'])} 家")
in_text(len(S["iso_netdisk"]), label="ISO 网盘分发家数",
        ctx=rf"网盘分发 {len(S['iso_netdisk'])} 家")
# 实测到的字节数写在正文里，必须与 t14b 的原文一致（防止正文数字被改而凭据不动）
_t14b = (TAB / "t14b_os_census_detail.csv").read_text()
for _b in ("6976131072", "5694060544", "5858738176", "5627537408",
           "7138705408", "8068329472", "4508876800", "3482347520",
           "2581036906", "7282405376", "3935305728"):
    ok(_b in _t14b, f"正文引用的 ISO 字节数 {_b} 必须在 t14b 的原文里")
    in_text(_b, label=f"ISO 字节数 {_b}")
ok("公司持有的正式授权" in REPORT,
   "拿到商业 ISO 靠的是授权这件事必须写明，不许暗示这两家比别家开放")

# 安可 8 批明细表：这是名录里唯一的第三方硬名录，逐批都要在，
# 少一批就会让「只出现过 4 家送测单位」这个结论失去覆盖面依据。
for _b in ("2023 年第 1 号", "2024 年第 1 号", "2024 年第 2 号", "2025 年第 1 号",
           "2025 年第 2 号", "2025 年第 3 号", "2026 年第 1 号", "2026 年第 2 号"):
    in_text(_b, label=f"安可明细表应含 {_b}")
ok(REPORT.count("无操作系统") >= 3,
   "三批「无操作系统」的期号必须如实列出 —— 只列有入围的那几批会高估覆盖面")
in_text("Ⅱ级", label="HarmonyOS 的 Ⅱ 级必须写明（唯一非 Ⅰ 级的桌面 OS）")
ok("未能访问" in REPORT,
   "「未能访问」与「站点下线」的区分必须在正文出现（普华官网 502 那处）")

# 名录与构建脚本的对账：凡 distros/*.conf 里有公开 ISO_URL 的发行版，
# 名录的 ISO 获取列不得标为「需授权」—— 这个矛盾本轮真的发生过（统信那条），
# 而当时没有任何断言在看，全靠用户指出。
_iso_urls = {}
for _cf in sorted((ROOT / "distros").glob("*.conf")):
    for _l in _cf.read_text().splitlines():
        if _l.startswith("ISO_URL="):
            _iso_urls[_cf.stem] = _l.split("=", 1)[1].strip().strip('"')
_DID2NAME = {"uos25": "统信桌面操作系统 V25（UOS）",
             "kylin11": "银河麒麟桌面操作系统", "kylin10": "银河麒麟桌面操作系统",
             "kylinsec6": "麒麟信安操作系统", "linx6": "凝思安全操作系统"}
_contra = []
_ent = {e["name"]: e for e in json.loads((ROOT / "raw" / "d8_os_census.json").read_text())["entries"]}
for _did, _u in _iso_urls.items():
    _nm = _DID2NAME.get(_did)
    if _nm and _nm in _ent and "授权" in _ent[_nm].get("s_iso_access", ""):
        _contra.append(f"{_did}（conf 里有公开 ISO_URL {_u[:48]}…）↔ 名录标为需授权")
ok(_contra == [], "名录不得与构建脚本矛盾：" + "；".join(_contra))
ok(len(_iso_urls) >= 1, f"至少应有一个发行版在 conf 里记了 ISO_URL，实际 {len(_iso_urls)}")

# 两条方法学纪律必须留在正文：搜索摘要伪造原文、证据要分「能否纯 HTTP 复现」。
# 它们决定第三方复核时会不会把不可复现的东西当成已核实。
ok("必须能在抓到的页面里 grep 命中才算" in REPORT,
   "「原文引用必须 grep 命中」这条纪律必须写在正文")
ok("能不能纯 HTTP 复现" in REPORT,
   "证据分级（纯 HTTP 可复现 vs 依赖浏览器渲染）必须写在正文")
# EulerOS 的低信心判定已被正对照取代（TaiShan 98 个版本 vs EulerOS 三节点全空），
# 原先守「信心最低的一格」那条断言随之空转，改为守正对照本身。
ok("TaiShan 节点匿名可取到 98 个版本" in REPORT,
   "EulerOS 判定所依赖的正对照必须写在正文 —— 没有它，「门户里没条目」与「藏在登录墙后」无法区分")

# ── 段落重复检测：本轮真正的伤害来源 ────────────────────────────────────
# 一次「删除」实际把待删块换成了前一段的副本，留下 26 行陈旧重复，
# 并由此在正文里留下三处自相矛盾（同一现象既是两次又是三次、
# 同一结论既「无法区分」又「已定案」）。322 条断言当时全过 —— 它们
# 逐字锚定数字，却没有一条在看「同一段是不是出现了两次」。
_paras = [x.strip() for x in REPORT.split("\n\n") if len(x.strip()) >= 80]
_dupes = sorted({x[:60] for x in _paras if _paras.count(x) > 1})
ok(_dupes == [],
   f"正文不许有重复段落（重复 {len(_dupes)} 处，首处：{_dupes[:1]}）")
# 表格也查：整张表被复制一份时，表头会出现两次
for _hdr in ("| 公告期号 | 桌面操作系统入围 |", "| | OS | 类型 | 厂商/主导方 |"):
    ok(REPORT.count(_hdr) == 1,
       f"表头「{_hdr[:24]}…」应只出现 1 次，实际 {REPORT.count(_hdr)} 次")
# 脚注定义不许重复：GitHub 只取首个，重复定义会让附录 C 的完整版被中段的覆盖
_defs = re.findall(r"^\[\^(R\d+)\]:", REPORT, re.M)
_ddup = sorted({d for d in _defs if _defs.count(d) > 1})
ok(_ddup == [], f"脚注定义不许重复（重复：{_ddup}）")

# 安可缺席的 7 家：先前只断言在列 3 家的名字，缺席那 7 家的点名没人守，
# 结果正文把 FydeOS 写成了优麒麟（两者都不在列，但名单是错的）。逐名核对。
# 逐名核对必须限定在**那一句话之内** —— 只查「名字出现在正文任意位置」是永真的
# （FydeOS、deepin 这些在别处大量出现），上一轮那个 bug 其实是靠写死的黑名单抓到的，
# 而黑名单只防已经犯过的那一次。
def _shortname(n):
    """把名录里的全名压成正文实际用的简称。
    先前只剥「桌面操作系统」这类后缀，剥不掉版本号尾巴 ——
    `统信桌面操作系统 V25（UOS）` → `统信 V25`、`方德桌面操作系统 V5.0` → `方德 V5.0`，
    都不是正文用的写法，于是反向名单对在列的 3 家里有 2 家永不命中（实测）。"""
    x = n.split("（")[0]
    for suf in ("桌面操作系统", "安全操作系统", "操作系统"):
        x = suf and x.replace(suf, "") or x
    x = re.sub(r"\s*V?\d+(?:\.\d+)*(?:\s*SP\d+)?\s*$", "", x)
    return x.strip() or n


_ent8_names = json.loads((ROOT / "raw" / "d8_os_census.json").read_text())["entries"]
_absent_sent = re.search(r"另有 \d+ 家明确不在（[^）]*）", REPORT)
ok(_absent_sent is not None, "缺席名单那句话必须存在")
_as = _absent_sent.group(0) if _absent_sent else ""
for _n in S["aqkk_desktop_absent"]:
    # 名称在正文里会用简称（「麒麟信安操作系统」→「麒麟信安」），去掉这些后缀再比
    _short = _shortname(_n)
    ok(_short in _as, f"安可缺席名单里的「{_short}」必须出现在缺席那句话里，实际句子：{_as[:70]}")
# 反向：那句话里点到的名字都得真的在缺席集里（防止把在列的或无关的塞进去）
_names = re.findall(r"[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9]{1,12}", _as)
_absent_short = {n.split("（")[0].replace("桌面操作系统", "").replace("安全操作系统", "").strip()
                 for n in S["aqkk_desktop_absent"]}
# 反向名单从数据现算：凡不在 aqkk_desktop_absent 里的 OS 名（含在列那 3 家）
# 都不该出现在这句话里。先前写死黑名单，恰好漏掉在列的 3 家（实测塞「统信UOS」不报）。
_all_os = {e["name"] for e in _ent8_names}
_notabsent = set()
for _n in _all_os - set(S["aqkk_desktop_absent"]):
    _sh = _shortname(_n)
    if len(_sh) >= 2:
        _notabsent.add(_sh)
_listed_but_absent = sorted(n for n in _notabsent if n in _as)
ok(_listed_but_absent == [],
   f"缺席那句话里不许出现这些名字（它们不在 aqkk_desktop_absent 集里）：{_listed_but_absent}")
# 加包代价那四个数：两个起点都有锚点，说成一个是错的

in_text("只有两个起点有现存锚点", label="加包代价四个数的锚点计数")

# sudo 的 61 / 189 / 639 三个数：正文引它们，就必须由矩阵现算并逐个绑住 ——
# 「数写进正文却没有断言守」正是 §9.2 认定的病根形态。
# sudo 每个镜像一格，格数应等于镜像数 —— 写死 9 是三被试时代的遗留。
ok(S["sudo_cells_n"] == _N_IMG, f'sudo 应有 {_N_IMG} 格探针为 N，实际 {S["sudo_cells_n"]}')
ok(S["cells_gap_if_sudo_counted"] == S["cells_gap"] + S["sudo_cells_n"],
   "「sudo 计入缺口」的基线必须等于当前缺口加 sudo 格数")
in_text(S["cells_gap_if_sudo_counted"], label="sudo 计入缺口时的基线",
        ctx=rf"缺口数由 {S['cells_gap_if_sudo_counted']} 变为 {S['cells_gap']}")
in_text(S["cells_na"] - S["sudo_cells_n"], label="删除 sudo 后的不适用数",
        ctx=rf"不适用从 {S['cells_na']} 降到 {S['cells_na'] - S['sudo_cells_n']}")
in_text(S["capability_cells"] - S["sudo_cells_n"], label="删除 sudo 后的总格数",
        ctx=rf"总格数从 {S['capability_cells']} 降到 {S['capability_cells'] - S['sudo_cells_n']}")

# README 也要查段落重复 —— 上一轮四个 ❌ 里的第 4 个就在 README，
# 而重复检测当时只切了 REPORT。
_rparas = [x.strip() for x in README.split("\n\n") if len(x.strip()) >= 80]
_rdup = sorted({x[:50] for x in _rparas if _rparas.count(x) > 1})
ok(_rdup == [], f"README 不许有重复段落（重复 {len(_rdup)} 处，首处：{_rdup[:1]}）")
# 表格行级重复：整张表被复制时表头会重复，但只复制表体不会 —— 单独查数据行
_trows = [l for l in REPORT.split("\n") if l.startswith("| ") and len(l) >= 60
          and not l.startswith("|---") and "---|" not in l]
_tdup = sorted({l[:50] for l in _trows if _trows.count(l) > 1})
ok(_tdup == [], f"表格数据行不许重复（重复 {len(_tdup)} 处，首处：{_tdup[:1]}）")

# 分析层变异用例数：镜像层是 12（来自 d4 门禁日志），分析层是 mutation-docs.sh 里的
# mut/mutcmd 调用数。两者不是一个数，抬头混写会让人以为门禁只有 12 例。
_mdocs = (ROOT / "test" / "mutation-docs.sh").read_text()
_ncases = len(re.findall(r"^mut(?:cmd)? ", _mdocs, re.M))
ok(_ncases >= 14, f"分析层变异用例应不少于 14 例，实际 {_ncases}")
in_text(_ncases, label="抬头写明的分析层变异用例数",
        ctx=rf"\+ \*\*{_ncases}\*\*（分析层）")

# ── 抬头计数与附录索引：本轮两个阻塞项的根因是这两处没有门禁 ──────────────
# 抬头「一手数据集 7 组」错了很久（实际 8），附录 B 表目录停在 t13 缺 4 张，
# 而 verify.py 自己的注释把「附录 A/B 是完整索引」当成排除附录的前提写着 ——
# 门禁建立在一个不成立的假设上。现在把这两件事都算出来核。
_raws = sorted(x.name for x in (ROOT / "raw").glob("d*_*.json"))
ok(len(_raws) >= 8, f"raw/ 应有至少 8 组一手数据，实际 {len(_raws)}")
for _w in (REPORT, README):
    _m = re.search(r"一手数据集 \*\*(\d+)\*\* 组", _w)
    ok(_m is not None and int(_m.group(1)) == len(_raws),
       f"抬头的一手数据集组数应为 {len(_raws)}，实际写 {_m.group(1) if _m else '缺'}")

_tables = sorted(x.name for x in (TAB).glob("*.csv"))
for _w, _lbl in ((REPORT, "report"), (README, "README")):
    for _m in re.finditer(r"(\d+) 张可复算表", _w):
        ok(int(_m.group(1)) == len(_tables),
           f"{_lbl} 里的「N 张可复算表」应为 {len(_tables)}，实际 {_m.group(1)}")
    _m = re.search(r"可复算表 \*\*(\d+)\*\* 张", _w)
    ok(_m is not None and int(_m.group(1)) == len(_tables),
       f"{_lbl} 抬头的表数应为 {len(_tables)}")

# 附录 B 必须是**完整**索引 —— 这是把附录排除在引用检查外的前提
_appb = REPORT[REPORT.index("## 附录 B"):REPORT.index("## 附录 C")]
_listed = set(re.findall(r"derived/tables/(\S+?\.csv)", _appb))
ok(_listed == set(_tables),
   f"附录 B 表目录必须列全（缺 {sorted(set(_tables) - _listed)}；多 {sorted(_listed - set(_tables))}）")
_appa = REPORT[REPORT.index("## 附录 A"):REPORT.index("## 附录 B")]
_figs = sorted(x.name for x in (ROOT / "figures").glob("*.png"))
_lf = set(re.findall(r"figures/(\S+?\.png)", _appa))
ok(_lf == set(_figs), f"附录 A 图目录必须列全（缺 {sorted(set(_figs) - _lf)}）")

# 抬头引用条数与图张数
_m = re.search(r"参考来源 \*\*(\d+)\*\* 条", REPORT)
ok(_m is not None and int(_m.group(1)) == S["references_total"],
   f"抬头引用条数应为 {S['references_total']}")
for _w, _lbl in ((REPORT, "report"), (README, "README")):
    _m = re.search(r"图 \*\*(\d+)\*\* 张", _w)
    ok(_m is not None and int(_m.group(1)) == len(_figs),
       f"{_lbl} 抬头的图张数应为 {len(_figs)}")

# d8 必须出现在 README 的采集清单与目录树里 —— 它是 §2.1 整节的唯一凭据
for _t in ("d8_os_census.json", "collect_d8_os_census.py"):
    ok(_t in README, f"README 必须列出 {_t}（§2.1 名录的唯一凭据）")

# ⚠️ maintained 全文曾被短限定覆写过一次（72 字 → 16 字），而 t14b 正是被标为
# 「完整原文」的表。凡两个字段并存的条目，全文必须长于短限定，否则就是又覆写了。
_ent8 = json.loads((ROOT / "raw" / "d8_os_census.json").read_text())["entries"]
_ovw = [e["name"] for e in _ent8
        if e.get("s_maintained") and len(e["maintained"]) <= len(e["s_maintained"])]
ok(_ovw == [], f"maintained 全文不许被 s_maintained 覆写（可疑：{_ovw}）")
_pairs = sum(1 for e in _ent8 if e.get("s_maintained"))
ok(_pairs >= 3, f"应有至少 3 条同时带 maintained 与 s_maintained，实际 {_pairs}")

# ⚠️ artifacts/euleros-loginwall.txt 是孤儿凭据：文件在但正文不指向它、门禁不知道它。
# 「证据消失即断言消失」——凭据必须被引用，否则删掉它没人发现。
_lw = ROOT / "artifacts" / "euleros-loginwall.txt"
ok(_lw.exists(), "artifacts/euleros-loginwall.txt 必须存在（「对任意 nid」的一手凭据）")
_lwt = _lw.read_text() if _lw.exists() else ""
ok(_lwt.count("x-login-url: https://uniportal.huawei.com/uniportal1/") == 3,
   "该凭据应含 3 个 nid 的 Uniportal 头（其中一个是刻意乱填的）")
ok("EDOC1100xxxx" in _lwt, "凭据里必须有那个刻意乱填的 nid —— 它才是「任意 nid」的关键")
ok("euleros-loginwall.txt" in REPORT,
   "正文必须指向 artifacts/euleros-loginwall.txt，否则读者从结论走不到凭据")

# ⚠️ t04 锚点那条改为从列现算，不用裸子串
_t04rows = list(csv_mod.DictReader((TAB / "t04_built_images.csv").open()))
_anch = {r["unpacked_size"] for r in _t04rows}
ok("345MB" in _anch and "281MB" in _anch,
   f"345MB 与 281MB 都应出现在 t04 的 unpacked_size 列，实际该列：{sorted(_anch)}")

# ── 章节编号漂移与正文内的陈旧例数：第四轮两个 ❌ 的整类根因 ──────────────
# ① 「§x.y」标签与它 anchor 指向的标题编号必须一致 —— 插入名录那次把
#    「麒麟是另一条产品线」从 §2.1 挤到 §2.3，anchor slug 改了、可见的标签没改。
_heads = {}
for _m in re.finditer(r"^#{2,4}\s+((\d+(?:\.\d+)?)[\s.、]\s*.+)$", REPORT, re.M):
    _heads[_gh_anchor(_m.group(1))] = _m.group(2)
_mismatch = []
for _m in re.finditer(r"\[§(\d+(?:\.\d+)?)\]\(report\.md#([^\)]+)\)", README):
    _lbl, _anc = _m.group(1), _m.group(2)
    _real = _heads.get(_anc)
    if _real and _real != _lbl:
        _mismatch.append(f"标签 §{_lbl} → anchor 实为 §{_real}")
ok(_mismatch == [], f"README 里「§x.y」标签必须与 anchor 指向的标题编号一致（不符：{_mismatch}）")

# ② 正文里写的「分析层 N 例」必须等于 mutation-docs.sh 的实际用例数。
#    先前只绑抬头那一处，正文 §9.1 的两处漂了三个版本没人发现。
_nc = len(re.findall(r"^(?:mut|mutcmd) ", (ROOT / "test" / "mutation-docs.sh").read_text(), re.M))
for _m in re.finditer(r"分析层 (\d+) 例", REPORT):
    ok(int(_m.group(1)) == _nc,
       f"正文的「分析层 N 例」应为 {_nc}，实际写 {_m.group(1)}")
ok(len(re.findall(r"分析层 \d+ 例", REPORT)) >= 2,
   "正文应至少两处提到分析层例数（§9.1 的两处），否则这条断言等于空转")

# ③ report 的门禁结果表五个数也要绑 —— 先前只绑 README 那张，两份可以互相矛盾。
for _v, _ctx, _lbl in [
    (S["verify_passed"], rf"\*\*{S['verify_passed']} 通过 / 0 失败\*\*", "report 门禁表 verify"),
    (S["digest_chain_passed"], rf"\*\*{S['digest_chain_passed']} / {_N_IMG}\*\*", "report 门禁表 digest/sbom"),
    (S["mutation_caught"], rf"\*\*{S['mutation_caught']} 抓到 / 0 漏", "report 门禁表 mutation"),
    (S["repro_identical"], rf"\*\*{S['repro_identical']} / {_n_repro} 逐位一致\*\*", "report 门禁表 repro"),
]:
    in_text(_v, label=_lbl, ctx=_ctx)

# ④ config/ 与 raw/ 的名录必须一致 —— report 说 config 是「可核对的源文件」，
#    而门禁读的是 raw；只改 config 那一边先前两个方向都不报警。
_cfg = json.loads((ROOT / "config" / "os_census.json").read_text())["entries"]
_raw8 = json.loads((ROOT / "raw" / "d8_os_census.json").read_text())["entries"]
ok(_cfg == _raw8,
   "config/os_census.json 与 raw/d8_os_census.json 的 entries 必须逐字段相等"
   "（前者是报告声明的可核对源文件，后者是门禁实际读的）")


# ⑥ 缺席那句话里的两个可现算数字
in_text(len(S["aqkk_desktop_listed"]), label="安可在列家数",
        ctx=rf"在列的是 \*\*{len(S['aqkk_desktop_listed'])} 家")
in_text(len(S["aqkk_desktop_absent"]), label="安可缺席家数",
        ctx=rf"另有 {len(S['aqkk_desktop_absent'])} 家明确不在")

# ── 按「量」批量核对，而不是逐句绑 ────────────────────────────────────────
# 前四轮 10 个 ❌ 里有 6 个是同一模式：某个量在一处更新了、另一处没跟上，
# 而门禁只绑了其中一处。系统扫描发现两份 md 里 142 处数字有 84 处无门禁、
# 其中 53 处能从派生数据现算。逐句加 in_text 治不了这个类别 —— 换成按量核：
# 每个量配一组「量词模式」，凡文中以该模式出现的地方，数值必须等于派生值。
_QTY = [
    (S["census_os_count"],        [r"名录里 (\d+) 个 OS", r"扩到 (\d+) 个 OS",
                                   r"全部 (\d+) 个 OS", r"(\d+) 个 OS 逐个直连",
                                   r"全名录（(\d+) 个", r"名录 \*\*(\d+)\*\* 个"], "名录 OS 数"),
    (S["census_probes"],          [r"(\d+) 个候选引用实测", r"实测（(\d+) 个引用",
                                   r"存在性实测（(\d+) 个引用"], "名录实测引用数"),
    (S["references_total"],       [r"共 (\d+) 条，定义见附录", r"共 (\d+) 条，可复算副本",
                                   r"全局引用表（(\d+) 条", r"参考来源 \*\*(\d+)\*\* 条"], "引用条数"),
    (S["references_title_from_page"], [r"(\d+) 条的标题由脚本抓自"], "抓自页面的标题数"),
    (S["references_title_manual"],[r"另 (\d+) 条的页面不返回"], "人工标注的标题数"),
    (len(S["iso_direct"]),        [r"\*\*直接下载 (\d+) 家\*\*", r"(\d+) 家直连可取"], "ISO 直接下载家数"),
    (S["existence_probes"],       [r"(\d+) 个候选引用 \d+ 个可匿名拉取",
                                   r"上面那 (\d+) 个候选引用", r"在这 (\d+) 条里",
                                   r"对 (\d+) 条探测的观察"], "d1 候选引用数"),
    (S["official_available"],     [r"\d+ 个候选引用 (\d+) 个可匿名拉取"], "可匿名拉取数"),
    (S["installability_tools"] if isinstance(S.get("installability_tools"), int)
     else len(S.get("installability_tools", [])),
                                  [r"(\d+) 个工具在各自源里", r"这 (\d+) 个工具在各自软件源",
                                   r"「(\d+) 个工具全都装不上」", r"(\d+) 个常见工具的源内可装性",
                                   r"(\d+) 个工具是 `ipr"], "可装性工具数"),
    (S["uos_iso_packages"],       [r"（(\d+) 个包的 ISO 清单", r"（(\d+) 个包的清单可查"], "UOS ISO 包数"),
    (S["defects"],                [r"\+ (\d+) 条厂商缺陷"], "厂商缺陷数"),
    (S["mutation_caught"],        [r"(\d+) 个用例覆盖删", r"上面那 (\d+) 例打的是镜像内",
                                   r"镜像层 (\d+) 例）"], "镜像层变异用例数"),
    (S["uos_apt_repo_packages"],  [r"源索引只有 (\d+) 个条目"], "UOS 源索引条目数"),
    (S["census_probes_exist"],    [r"个候选引用实测 (\d+) 个存在"], "名录实测存在数"),
    (S["images_built"],           [r"× (\d+) 个镜像 = \d+ 格", r"(\d+) 个镜像实测 \d"], "镜像数"),

]
for _val, _pats, _lbl in _QTY:
    _hits = 0
    for _pat in _pats:
        for _w in (REPORT, README):
            for _m in re.finditer(_pat, _w):
                _hits += 1
                ok(int(_m.group(1)) == _val,
                   f"{_lbl}应为 {_val}，但有一处写 {_m.group(1)}（模式 {_pat}）")
    ok(_hits > 0, f"{_lbl}的量词模式在文中一处都没匹配到 —— 模式过时了，这条断言在空转")

# 这几个量不在 stats 里，但同样能从名录或表格现算，正文引了就该绑。
_ent = json.loads((ROOT / "raw" / "d8_os_census.json").read_text())["entries"]
_deb = sum(1 for e in _ent if any(k in e.get("s_lineage", "")
                                  for k in ("Debian", "deb 系", "Ubuntu")))
_m = re.search(r"名录里 \d+ 个 OS 里，有 (\d+) 个是 deb 系", REPORT)
ok(_m is not None and int(_m.group(1)) == _deb,
   f"deb 系家数应为 {_deb}，实际写 {_m.group(1) if _m else '缺'}")
# 口径必须是**读者在表里看到的那份**（s_lineage）；同时要求长文 lineage 同口径 ——
# 先前门禁读 lineage、表里印 s_lineage，两者一个 6 一个 7，读者数出来的和断言守的不是一个数。
# 判据用整串里是否出现「未声明/未查到/未书面确认/推断」这组限定词，
# 不用「前 N 字」—— 那个截断让同口径的两个字段判成不同（银河麒麟的「未声明」
# 在短版括号里、长版开头，前 16 字这个判据只抓到一边）。
_UNST = ("未声明", "未查到", "未书面确认", "未给出", "推断")
_unst_s = {e["name"] for e in _ent if any(k in e.get("s_lineage", "") for k in _UNST)}
_unst_l = {e["name"] for e in _ent if any(k in e["lineage"] for k in _UNST)}
ok(_unst_s == _unst_l,
   f"血统「未声明」的判定在 s_lineage 与 lineage 两个字段上必须一致（差集：{_unst_s ^ _unst_l}）")
_unst = len(_unst_s)
in_text(_unst, label="血统未声明的家数", ctx=rf"：{_unst} 家的血统是「官方未声明」")
_m = re.search(r"那一列显示 (\d+) 家的血统「官方未声明」", REPORT)
ok(_m is not None and int(_m.group(1)) == _unst,
   f"血统未声明家数应为 {_unst}，实际写 {_m.group(1) if _m else '缺'}")
# DevStation 版本数：正文那张表里 DevStation/ 为 200 的行数
_dev = REPORT[REPORT.index("| 版本 | `DevStation/`"):]
_dev = _dev[:_dev.index("\n\n")]
_dev200 = sum(1 for l in _dev.split("\n")
              if l.startswith("| ") and re.search(r"\| 200 \|", l))
_m = re.search(r"DevStation 本身有 (\d+) 个版本", REPORT)
ok(_m is not None, "DevStation 版本数那句必须存在")
ok(int(_m.group(1)) == 6,
   f"DevStation 版本数应为 6（SP1/SP2/SP3/24.09/25.03/25.09），实际写 {_m.group(1)}")

# ── README 目录结构树：❌1 能通过 437 条断言的唯一原因是这一段从没被看过 ────
# 那次事故在正文留下字面量 `\1` 并吞掉了 `distros/` 整行描述。现在把树里出现的
# 每个路径与真实文件系统对账，并禁止正则替换的残留物进入正文。
_tree_start = README.index("## 6. 目录结构") if "## 6. 目录结构" in README else README.index("目录结构")
_tree = README[_tree_start:]
_tree = _tree[:_tree.index("\n## ")] if "\n## " in _tree else _tree
# 树是缩进式的：顶层项无缩进，子项缩进两格并相对上一个顶层目录。
# 先前不跟踪层级，把 `kylin11.conf` 当成仓库根下的路径，全部判成不存在。
_paths = set(); _cur = ""
for _l in _tree.split("\n"):
    # 顶层目录行可能只有目录名、没有描述（如 `test/`），所以描述部分不能是必需的 ——
    # 先前要求 `\s{2,}\S`，于是 `test/` 没被识别成父项，它底下的文件全对不上。
    _m = re.match(r"^(\s*)([A-Za-z_][\w./*-]*)(?:\s{2,}\S|\s*$)", _l)
    if not _m:
        continue
    _ind, _nm = len(_m.group(1)), _m.group(2)
    if _ind == 0:
        _cur = _nm if _nm.endswith("/") else ""
        _paths.add(_nm)
    elif _cur:
        _paths.add(_cur + _nm)
_missing = []
for _pp in sorted(_paths):
    if "*" in _pp:
        import glob as _glob
        if not _glob.glob(str(ROOT / _pp)):
            _missing.append(_pp)
    elif not (ROOT / _pp).exists():
        _missing.append(_pp)
ok(_missing == [], f"README 目录树里的路径必须都真实存在（不存在：{_missing}）")
ok(len(_paths) >= 20, f"README 目录树应列出至少 20 个路径，实际 {len(_paths)} —— 太少说明整段被吞了")
# 真实存在的顶层目录都该在树里出现（防止像 config/ 那样整个漏掉）
_SKIP = {".git", "out", "logs", "archive", "__pycache__"}
_topdirs = {d.name + "/" for d in ROOT.iterdir()
            if d.is_dir() and not d.name.startswith(".") and d.name not in _SKIP}
_untreed = sorted(d for d in _topdirs if d not in _tree)
ok(_untreed == [], f"真实存在的顶层目录都必须在 README 目录树里（漏：{_untreed}）")
# 正则替换的残留物一律不许进正文（`\1` `\2` `\g<1>` 这类）
for _w, _lbl in ((REPORT, "report"), (README, "README")):
    _junk = re.findall(r"(?<!`)\\[1-9](?!`)|\\g<\d>", _w)
    ok(_junk == [], f"{_lbl} 里不许出现正则替换残留（发现：{_junk[:5]}）")

# ── §2.5／§2.6 后续候选与 TODO ────────────────────────────────────────────
# 三条排除标准筛掉的每一家，都必须能在名录里找到对应依据，否则就是凭印象排除。
_ent25 = {e["name"]: e for e in _ent8_names}
# ① 淘汰：名录的维护状态必须真的写着停更/沉寂/疑似停止
for _n, _kw in (("中标麒麟桌面操作系统（NeoKylin）", ("停更",)),
                ("一铭桌面操作系统（EmindDesktop）", ("疑似停止",)),
                ("普华桌面操作系统", ("沉寂",))):
    _m = _ent25[_n].get("s_maintained") or _ent25[_n]["maintained"]
    ok(any(k in _m for k in _kw),
       f"§2.5 以「已淘汰」排除 {_n}，名录的维护状态必须支持这一点，实际：{_m[:30]}")
# ② 官方已有满足需求的形态：名录的桌面一列必须写着无桌面 ISO
for _n in ("openEuler", "Anolis OS（龙蜥）", "OpenCloudOS"):
    ok("无桌面 ISO" in _ent25[_n]["s_desktop"],
       f"§2.5 以「官方基础镜像 + 按包装」排除 {_n}，名录必须显示它无桌面 ISO")
# ③ ISO 拿不到：分类必须落在拿不到或不可脚本化那几类
for _n, _cls in (("方德桌面操作系统 V5.0", ("未查到公开下载",)),
                 ("EulerOS（华为）", ("未查到公开下载",)),
                 ("新支点桌面操作系统（NewStart NSDL）", ("网盘分发",))):
    ok(_ent25[_n]["s_iso_access"] in _cls,
       f"§2.5 以「ISO 拿不到」排除 {_n}，其 ISO 获取分类必须是 {_cls}，实际 {_ent25[_n]['s_iso_access']}")
# 三个优先候选的 ISO 必须真的是直接下载 —— 否则「优先做」就落不了地
for _n in ("麒麟信安操作系统（KylinSec）", "凝思安全操作系统", "Loongnix（龙芯）"):
    ok(_ent25[_n]["s_iso_access"] == "直接下载",
       f"§2.5 把 {_n} 列为优先候选，其 ISO 必须是直接下载，实际 {_ent25[_n]['s_iso_access']}")
    ok(_n.split("（")[0] in REPORT, f"§2.5 必须点到候选 {_n}")
# 安可桌面附表那三家与「第三家拿不到 ISO」这处尴尬，都由数据现算
ok("恰好是 ISO 拿不到的那家" in REPORT, "§2.5 必须点明方德是拿不到 ISO 的那家")
# TODO 表必须存在且条目数不少于 8
_todo = REPORT[REPORT.index("### 2.6 后续 TODO"):]
_todo = _todo[:_todo.index("\n## ")] if "\n## " in _todo else _todo
_rows = [l for l in _todo.split("\n") if re.match(r"^\| \d+ \|", l)]
ok(len(_rows) >= 8, f"§2.6 的 TODO 表应有至少 8 条，实际 {len(_rows)}")
# 麒麟信安与凝思已在第二轮做完，状态从「优先」变「已完成」。断言随之改为
# 「至少 4 条已完成」—— 留着旧判据会在事情做完之后失败，那是判据落后于事实。
ok(sum(1 for l in _rows if "已完成" in l) >= 4, "TODO 里应有至少 4 条标为已完成（麒麟信安与凝思各两条）")
ok(sum(1 for l in _rows if "待定" in l) >= 2, "Loongnix 那两条应标为待定")

# 替换整段时最容易悄悄丢掉支撑性信息点。这几条是 §2.5 各项排除与推荐的**依据**，
# 缺了任一条，对应结论就变成无据断言（本轮替换 §2.4 末段时真丢过两条）。
for _kw, _why in (
    ("2025 年第 3 号公告", "方德与银河麒麟 V11 同批过评 —— 「该做的第三家是方德」的依据"),
    ("桌面线自身的最近更新时间未查到", "新支点桌面线活跃度存疑 —— 排除它的第二个理由"),
    ("车用 AUTOSAR", "普华桌面线沉寂的依据"),
    ("不可脚本化", "把网盘分发归入「拿不到」的理由"),
    ("上游镜像近似", "openKylin/deepin 归入「视需求做」的理由"),
    ("只差一个 tag", "Loongnix 那个陷阱比 §2.3 更隐蔽的原因"),
    ("dnf --installroot", "麒麟信安扩包格式维度的具体代价"),
    ("不适合商业部署", "AOSC 归入「不建议做」的依据"),
):
    ok(_kw in REPORT, f"§2.5 缺少支撑信息点「{_kw}」——{_why}")

# ⚠️ 先前 20 条断言只核「名录支不支持 verify.py 里硬写的名字」，不核「报告的表里
# 到底写了谁」—— 实测三张表的内容可以整段漂移而全绿（删掉一家、把某家从③挪到优先、
# 整行删掉一条标准、改「剩下 N 个」都不报）。改为从报告里**解析出**那三张表再对账。
_s25 = REPORT[REPORT.index("### 2.5 候选梯度"):REPORT.index("### 2.6 后续 TODO")]
# ① 三条排除标准必须都在，且每条的「排除」格必须点到该标准对应的全部厂商
_EXCL = {"① 已基本淘汰、使用率极低": ("中标麒麟", "一铭", "普华"),
         "② 官方已有能满足对标需求的交付形态": ("Anolis OS", "OpenCloudOS"),
         "③ ISO 拿不到": ("方德", "EulerOS", "新支点")}
for _std, _who in _EXCL.items():
    _row = [l for l in _s25.split("\n") if l.startswith("| " + _std)]
    ok(len(_row) == 1, f"§2.5 排除表必须有且仅有一行「{_std}」，实际 {len(_row)} 行")
    if _row:
        # 只看**排除**那一列（第 2 格）。查整行会被第 3 格的依据文字兜住 ——
        # 实测删掉排除格里的「、普华」后整行仍含「普华」（依据格里也写着），检查放行。
        _cells = [c.strip() for c in _row[0].strip().strip("|").split("|")]
        _excl_cell = _cells[1] if len(_cells) > 1 else ""
        for _w in _who:
            ok(_w in _excl_cell,
               f"§2.5 标准「{_std}」的排除格必须点到 {_w}，实际该格：{_excl_cell}")
        for _bad in ("麒麟信安", "Loongnix"):
            ok(_bad not in _excl_cell,
               f"§2.5 标准「{_std}」的排除格不许出现优先候选 {_bad}")
_SUBJ_AT_GRADIENT = 2   # 排梯度那个时点，名录里被试条目是 2 个（麒麟一条 + UOS 一条）
ok("这份梯度是首轮三个被试做完之后排的" in _s25,
   "§2.5 必须写明梯度是首轮三个被试做完之后排的（否则 19 这个分母无从解释）")
ok("已在第二轮" in _s25,
   "§2.5 必须点明梯度里排最前的两个候选已在第二轮做完（区分历史口径与现状）")
_n_excl = sum(len(v) for v in _EXCL.values())
_expect = S["census_os_count"] - _SUBJ_AT_GRADIENT - _n_excl
_m = re.search(r"剩下 (\d+) 个再看交付需求", _s25)
ok(_m is not None and int(_m.group(1)) == _expect,
   f"§2.5「剩下 N 个」应为 {S['census_os_count']} − {_SUBJ_AT_GRADIENT} − {_n_excl} = {_expect}，实际写 {_m.group(1) if _m else '缺'}")
_m = re.search(r"除两个被试条目之外的 (\d+) 个 OS", _s25)
ok(_m is not None and int(_m.group(1)) == S["census_os_count"] - _SUBJ_AT_GRADIENT,
   f"§2.5 的非被试 OS 数应为 {S['census_os_count'] - _SUBJ_AT_GRADIENT}（排梯度时的口径）")
for _who, _dim in (("麒麟信安 KylinSec", "包格式"), ("凝思安全操作系统", "场景类型"),
                 ("Loongnix（龙芯）", "架构与 ABI 世代")):
  _row = [l for l in _s25.split("\n") if l.startswith("| **" + _who.split("（")[0])]
  ok(len(_row) >= 1, f"§2.5 优先候选表必须有 {_who} 那一行")
  if _row:
      ok(_dim in _row[0], f"{_who} 那一行必须写明它扩的维度「{_dim}」")
# ③ TODO 表逐行绑：麒麟信安与凝思的行必须标优先，Loongnix 的行必须标待定
_s26 = REPORT[REPORT.index("### 2.6 后续 TODO"):]
_s26 = _s26[:_s26.index("\n## ")] if "\n## " in _s26 else _s26
# 麒麟信安与凝思已在第二轮做完，状态是「已完成」；Loongnix 仍待定。
for _kw, _flag in (("麒麟信安 KylinSec", "已完成"), ("凝思安全操作系统", "已完成"),
                 ("Loongnix 25.1", "待定")):
  _row = [l for l in _s26.split("\n") if re.match(r"^\| \d+ \|", l) and _kw in l]
  ok(len(_row) == 1, f"§2.6 TODO 必须有且仅有一行提到 {_kw}，实际 {len(_row)}")
  if _row:
      ok(_row[0].rstrip().rstrip("|").split("|")[-1].strip().startswith(_flag),
         f"§2.6 里 {_kw} 那一行的状态必须是「{_flag}」，实际：{_row[0][-24:]}")
# 依赖关系「随 N」「先于 N」引用的编号必须存在
for _m in re.finditer(r"(随|先于) (\d+)", _s26):
  _n = int(_m.group(2))
  ok(any(re.match(rf"^\| {_n} \|", l) for l in _s26.split("\n")),
     f"§2.6 里的依赖「{_m.group(0)}」指向不存在的条目 {_n}")

# §6.2「连 nano 都没有」——负面结论必须连对照组一起绑，
# 否则「源里没有」与「探测本身坏了」在证据上不可区分。
ok(S["uos_nano_candidate_none"] is True, "UOS 的 nano 在 apt 源里无候选")
in_text("Candidate: (none)", label="正文引用的是实际执行的 apt-cache policy 输出",
      ctx=r"apt-cache policy nano` 返回 `Candidate: \(none\)")
in_text("1000-notepad", label="正文写明对照组")
in_text(S["unpack_overhead_pct_min"], label="解包开销下界",
      ctx=r"实测 %s%%–" % S["unpack_overhead_pct_min"])
in_text(S["unpack_overhead_pct_max"], label="解包开销上界",
      ctx=r"–%s%%，分母用 tar 的精确字节" % S["unpack_overhead_pct_max"])

# 断言总数基线。没有它，删掉 artifacts/repro-evidence.txt 会让 7 条交叉断言整块被
# if 跳过，断言数从 113 悄悄掉到 106 而汇总照样全绿 —— 证据消失即断言消失。
# 这与 test/verify.sh 里对镜像检查数设基线是同一个道理，之前只给那边设了。
BASELINE = int(os.environ.get("VERIFY_BASELINE", "504"))
if N < BASELINE:
  print(f"❌ 执行断言 {N} 条，低于基线 {BASELINE} —— 有断言被静默跳过"
        f"（证据文件缺失？条件分支没进去？）")
  sys.exit(1)
# README 抬头的断言数必须与实际执行数相等（此前只捕获不比对，写 99999 也全绿）。
# ⚠️ 这条检查**不走 ok()**：它自己若计入 N，抬头数就永远比实跑少 1，形成自指。
if mr and int(mr.group(1)) != N:
  BAD.append(f"README 抬头写的机器核对断言 {mr.group(1)} 条 ≠ 实际执行 {N} 条")
# report 抬头那份先前无人比对，改错全绿。与 README 同判据，同样不走 ok()。
_mrep = re.search(r"机器核对断言 \*\*(\d+)\*\* 条", REPORT)
if _mrep and int(_mrep.group(1)) != N:
  BAD.append(f"report 抬头写的机器核对断言 {_mrep.group(1)} 条 ≠ 实际执行 {N} 条")
if not _mrep:
  BAD.append("report 抬头缺「机器核对断言 N 条」")
print(f"执行断言 {N} 条（基线 {BASELINE}）")
if BAD:
  print(f"❌ {len(BAD)} 条未过：")
  for b in BAD: print("  ✗", b)
  sys.exit(1)
print("✅ 全部通过")
