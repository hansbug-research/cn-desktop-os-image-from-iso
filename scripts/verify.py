#!/usr/bin/env python3
"""机器核对 report.md / README.md 里的每个声明。

约定：正文里的统计量必须能从 derived/stats.json 重算出来。这个脚本非 0 退出即不得提交。
它同时核对断言总数自洽 —— 正文声明的条数必须等于实际执行的条数。

⚠️ 它只覆盖被写成断言的那些数字。未被覆盖的仍需人工核对，
不要把「verify 全绿」等同于「每个数字都被机器核过」。
"""
import csv as csv_mod
import json, os, pathlib, re, sys

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

# ── 规模量 ──────────────────────────────────────────────────────────────────
ok(S["images_built"] == 9, "构建镜像数应为 9")
ok(sorted(S["distros"]) == ["kylin10", "kylin11", "uos25"], "被试发行版清单")
ok(sorted(S["tiers"]) == ["base", "devel", "micro"], "档位清单")
ok(sorted(S["build_methods"]) == ["mmdebstrap", "selfhost", "slice"], "三条构建路径")
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
# n/a 那批的成因必须写对：apt 三项 × 3 micro = 9，cc_clean_stderr × 6 = 6
ok(S["na_na_by_item"].get("cc_clean_stderr") == 6,
   f"n/a 明细里 cc_clean_stderr 应为 6 格，实际 {S['na_na_by_item']}")
ok(sum(v for k, v in S["na_na_by_item"].items() if k.startswith("apt_")) == 9,
   f"n/a 明细里 apt 相关应为 9 格，实际 {S['na_na_by_item']}")
# ⚠️ 上面两条只核 stats 内部自洽，**不核正文把哪个数归给哪一项** —— 把 9 与 6 对调
# 三处全绿，而上一轮出错的就是「成因写错」这件事本身。所以必须把数字与项目绑在一起。
_apt_n = sum(v for k, v in S["na_na_by_item"].items() if k.startswith("apt_"))
_cc_n = S["na_na_by_item"].get("cc_clean_stderr", 0)
# 逐处核对，而不是「全文任一处命中即可」—— 只改一处、另一处仍对，宽松匹配会被满足。
for where, txt in (("report", REPORT), ("readme", README)):
    n_apt = len(re.findall(rf"{_apt_n} 格[是为][^。；]{{0,16}}?apt 三项", txt))
    n_cc = len(re.findall(rf"{_cc_n} 格[是为][^。；]{{0,20}}?`cc_clean_stderr`", txt))
    # 每一处提到 apt 成因的地方都必须配 9，提到 cc_clean_stderr 的都必须配 6：
    # 用「出现次数必须相等」把两者钉成对，单改一处就会失衡。
    tot_apt = len(re.findall(r"格[是为][^。；]{0,16}?apt 三项", txt))
    tot_cc = len(re.findall(r"格[是为][^。；]{0,20}?`cc_clean_stderr`", txt))
    ok(n_apt == tot_apt and n_apt >= 1,
       f"{where} 里提到 apt 成因的 {tot_apt} 处，只有 {n_apt} 处写的是 {_apt_n} 格")
    ok(n_cc == tot_cc and n_cc >= 1,
       f"{where} 里提到 cc_clean_stderr 成因的 {tot_cc} 处，只有 {n_cc} 处写的是 {_cc_n} 格")

# ── 核心结论：麒麟官方镜像不是桌面产品线 ────────────────────────────────────
ok(S["kylin_desktop_official_images"] == 0, "麒麟桌面官方镜像应为 0")
ok(S["uos_official_images"] == 0, "UOS 官方镜像应为 0")
ok(S["os_id_collision"] is True, "麒麟官方与桌面的 os-release ID 应相同")
ok(S["official_pkg_format"] == "rpm", "麒麟官方镜像应为 rpm")
ok(S["ours_pkg_formats"] == ["dpkg"], "自建镜像应全为 dpkg")
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
ok(S["devel_count"] == 3, "devel 档应为 3 个")
ok(S["devel_c_ok"] == 3, "三个 devel 档 C 编译应全通过")
ok(S["devel_cxx_ok"] == 2, "C++ 应只有两家通过")
ok(S["devel_cxx_ok"] < S["devel_count"], "C++ 覆盖应少于 C —— 这是 UOS 无 g++ 的直接证据")

# ── 门禁 ────────────────────────────────────────────────────────────────────
ok(S["verify_failed"] == 0, "verify 不得有失败项")
ok(S["verify_passed"] >= S["verify_baseline"], "verify 通过数不得低于基线")
in_text(S["verify_passed"], label="verify 通过数")
in_text(S["verify_baseline"], label="verify 基线")
ok(S["digest_chain_passed"] == 9, "摘要链应 9/9")
ok(S["mutation_missed"] == 0, "变异测试不得有漏抓")
ok(S["mutation_caught"] == 12, "变异用例应为 12 条")
in_text(S["mutation_caught"], label="变异用例数")
ok(S["repro_identical"] == 6, "可复现性应 6 个产物逐位一致")
in_text(S["repro_identical"], label="逐位一致产物数")
ok(S["manifests"] == 9, "应有 9 份 manifest")
ok(S["probe_complete_all"] is True, "所有探针必须跑完（哨兵为 Y）")
ok(S["probe_stale_vs_image"] == [],
   f"这些镜像的探针输出早于镜像本身（数据比被测对象旧）：{S['probe_stale_vs_image']}")
ok(S["probe_provenance_recorded"] == 9,
   f"九个镜像都应记下探针时间与镜像创建时间，实际 {S['probe_provenance_recorded']}")

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
ok(S["sbom_passed"] == 9, "sbom 应 9 个镜像全通过")
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
ok(S["defects"] == 12, "厂商缺陷应为 12 条")
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
    nm = {"kylin10": "麒麟 V10", "kylin11": "麒麟 V11", "uos25": "UOS"}[d]
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
    (S["capability_items"], r"{v} 项 × 9 镜像", "README 能力项数"),
    (S["verify_passed"], r"{v} 通过 / 0 失败", "README 门禁表 verify"),
    (S["verify_baseline"], r"基线 {v}", "README 门禁表基线"),
    (S["digest_chain_passed"], r"\| {v} / 9 \|", "README 门禁表 digest"),
    (S["mutation_caught"], r"{v} 抓到 / 0 漏", "README 门禁表 mutation"),
    (S["repro_identical"], r"{v} / 6 逐位一致", "README 门禁表 repro"),
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
        ctx=rf"9 个镜像有效覆盖 {S['cve_effective_coverage']} 个")
# 结论标题的极性也要钉住，避免整句被反转
ok("没有有效覆盖" in README and "没有有效覆盖" in REPORT,
   "「通用扫描器没有有效覆盖」这句判断应在两份文档里原样存在")
ok(S["cve_unrecognized"] + S["cve_misidentified"] == 9, "九个镜像应全部落在未识别或误判")
in_text(S["cve_misidentified"], label="被误判的镜像数", ctx=rf"误判成 Debian 的 {S['cve_misidentified']} 个")
in_text(S["cve_unrecognized"], label="未识别的镜像数", ctx=rf"未识别的 {S['cve_unrecognized']} 个")
# 「报 0 个 HIGH/CRITICAL」这句必须是实测而非推断
ok(S["cve_high_critical_total"] == 0,
   "正文称扫描报 0 个 HIGH/CRITICAL，实测总数应为 0")

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
ok(S["alien_keyring_images"] == [],
   f"这些 UOS 镜像里出现了麒麟的 keyring：{S['alien_keyring_images']}")
# 按**档位**判，不只按发行版：micro 档没有 apt，写 sources.list 再塞 keyring 是纯冗余，
# 所以它应当两者皆空；base/devel 走在线源，需要且只需要麒麟那一把。
for k, v in S["keyrings_by_image"].items():
    d, t = k.split(":")
    if t == "micro":
        # 只约束**我们注入的**那些。麒麟 V10 的 micro 档带的那把属厂商 kylin-keyring 包，
        # 是发行版自带内容，删它就越过了「等价环境」的底线 —— 用属主区分，不一刀切。
        inj = S["injected_keyrings_by_image"].get(k, [])
        ok(inj == [], f"{k} 是纯运行时档、没有 apt，不该由构建注入 keyring，实际注入 {inj}")
        nb = S["micro_sources_list_bytes"].get(k)
        ok(nb == 0, f"{k} 没有 apt，出厂的 sources.list 应为空，实际 {nb} 字节")
        # 真正该数的是 active deb 行数：源清单可以在 sources.list.d/ 下，
        # 只量 sources.list 会漏掉（uos25:micro 曾因此带着一条 appstore 源全绿）。
        ad = S["micro_active_deb_lines"].get(k)
        ok(ad == 0, f"{k} 没有 apt，不该出厂任何 active 在线源，实际 {ad} 条 deb 行")
    elif d.startswith("kylin"):
        ok(v == ["kylin-archive-keyring.gpg"],
           f"{k} 的 keyring 应只有 kylin-archive-keyring.gpg，实际 {v}")

# d6/d7 的被测镜像必须与 d2 的产物同一批，否则那两组结论锚在旧镜像上
ok(S["anchor_mismatches"] == [],
   f"d6/d7 的锚点与 d2 的产物不符（锚在旧镜像上）：{S['anchor_mismatches']}")
ok(S["anchored_records"] >= 12, f"d6/d7 应有锚点的记录数过少：{S['anchored_records']}")
ok(S["anchor_pairs_checked"] == 12,
   f"实际比过的锚点对数应为 12，实际 {S['anchor_pairs_checked']} —— 少了就是有对账被静默跳过")
ok(S["micro_active_deb_missing"] == [],
   f"这些 micro 档的 active_deb_lines 字段没采到（缺键会让断言空转）：{S['micro_active_deb_missing']}")
ok(len(S["micro_active_deb_lines"]) == 3,
   f"三个 micro 档都应有 active_deb_lines，实际 {len(S['micro_active_deb_lines'])}")
ok(S["image_id_mismatches"] == [],
   f"这些镜像的当前 ID 与 manifest 记录不符（采集之后又重建了）：{S['image_id_mismatches']}")
ok(S["digest_log_prefixes_checked"] == 9,
   f"应从 f4-digest.log 抽出 9 条 sha256 前缀对账，实际 {S['digest_log_prefixes_checked']}")
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
ok(S["cve_unrecognized"] == 3, "trivy 未识别应为 3 个")
in_text(S["cve_unrecognized"], label="CVE 未识别数",
        ctx=rf"未识别的 {S['cve_unrecognized']} 个是麒麟 V11 三档")
ok(S["cve_misidentified"] == 6, "trivy 误判为 Debian 应为 6 个")
in_text(S["cve_misidentified"], label="CVE 误判数",
        ctx=rf"误判成 Debian 的 {S['cve_misidentified']} 个")
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
ok(all(not p["exists"] for p in _desk), "桌面命名引用必须全部不存在（本节核心结论）")
in_text("13 条", label="桌面命名引用条数",
        ctx=r"共 13 条，跨 5 家 registry")
in_text("一条都不存在", label="桌面命名引用全不存在这句结论")
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
_unstated = sum(1 for e in json.loads((ROOT / "config" / "os_census.json").read_text())["entries"]
                if "未" in e["lineage"][:12])
in_text(_unstated, label="血统未声明的家数", ctx=rf"\*\*：{_unstated} 家的血统是「官方未声明」")
# 剔除项与小型社区两个清单的条数也绑，避免悄悄增删
_cen = json.loads((ROOT / "config" / "os_census.json").read_text())
in_text(len(_cen["scope"]["exclusions"]), label="剔除项条数",
        ctx=rf"剔除 {len(_cen['scope']['exclusions'])} 项")
in_text(len(_cen["scope"]["small_community"]), label="小型社区条数",
        ctx=rf"另有 {len(_cen['scope']['small_community'])} 个\*\*小型社区发行版")

# §2.1 的 ★ 被试标记与 §2.4 的选型论证：名录必须真的标出被试，
# 且被试必须与我们实际构建的镜像对得上（否则名录与后文脱节，审稿时正好挑这个）。
ok(len(S["census_subjects"]) == 2,
   f'名录里应有 2 个被试标记（银河麒麟桌面、统信 UOS），实际 {S["census_subjects"]}')
ok(any("麒麟" in x for x in S["census_subjects"]) and any("UOS" in x for x in S["census_subjects"]),
   "被试标记必须落在银河麒麟与统信 UOS 上")
# 被试与 t04 里实际构建的三个镜像的发行版必须一致
_built = {r["distro"] for r in [dict(zip(*[iter([])]))] } if False else set(
    l.split(",")[0] for l in (TAB / "t04_built_images.csv").read_text().splitlines()[1:] if l)
ok(_built == {"kylin11", "kylin10", "uos25"},
   f"实际构建的发行版应为 kylin11/kylin10/uos25，实际 {sorted(_built)}")
in_text("★ 标记的两个是本项目的被试", label="名录里说明 ★ 含义")
in_text("银河麒麟桌面 V10 SP1、银河麒麟桌面 V11、统信 UOS V25", label="§2.4 点明三个被试 ISO")
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
             "kylin11": "银河麒麟桌面操作系统", "kylin10": "银河麒麟桌面操作系统"}
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
_absent_sent = re.search(r"另有 \d+ 家明确不在（[^）]*）", REPORT)
ok(_absent_sent is not None, "缺席名单那句话必须存在")
_as = _absent_sent.group(0) if _absent_sent else ""
for _n in S["aqkk_desktop_absent"]:
    # 名称在正文里会用简称（「麒麟信安操作系统」→「麒麟信安」），去掉这些后缀再比
    _short = _n.split("（")[0]
    for _suf in ("桌面操作系统", "安全操作系统", "操作系统"):
        _short = _short.replace(_suf, "")
    _short = _short.strip() or _n
    ok(_short in _as, f"安可缺席名单里的「{_short}」必须出现在缺席那句话里，实际句子：{_as[:70]}")
# 反向：那句话里点到的名字都得真的在缺席集里（防止把在列的或无关的塞进去）
_names = re.findall(r"[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9]{1,12}", _as)
_absent_short = {n.split("（")[0].replace("桌面操作系统", "").replace("安全操作系统", "").strip()
                 for n in S["aqkk_desktop_absent"]}
_listed_but_absent = [n for n in _names if n in {"优麒麟", "deepin", "openKylin", "openEuler",
                                                 "Anolis", "OpenCloudOS", "Loongnix", "AOSC"}]
ok(_listed_but_absent == [],
   f"缺席那句话里不许出现这些名字（它们不在 aqkk_desktop_absent 集里）：{_listed_but_absent}")
# 加包代价那四个数：两个起点都有锚点，说成一个是错的

in_text("只有两个起点有现存锚点", label="加包代价四个数的锚点计数")

# sudo 的 61 / 189 / 639 三个数：正文引它们，就必须由矩阵现算并逐个绑住 ——
# 「数写进正文却没有断言守」正是 §9.2 认定的病根形态。
ok(S["sudo_cells_n"] == 9, f'sudo 应有 9 格探针为 N，实际 {S["sudo_cells_n"]}')
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
BASELINE = int(os.environ.get("VERIFY_BASELINE", "365"))
if N < BASELINE:
    print(f"❌ 执行断言 {N} 条，低于基线 {BASELINE} —— 有断言被静默跳过"
          f"（证据文件缺失？条件分支没进去？）")
    sys.exit(1)
# README 抬头的断言数必须与实际执行数相等（此前只捕获不比对，写 99999 也全绿）。
# ⚠️ 这条检查**不走 ok()**：它自己若计入 N，抬头数就永远比实跑少 1，形成自指。
if mr and int(mr.group(1)) != N:
    BAD.append(f"README 抬头写的机器核对断言 {mr.group(1)} 条 ≠ 实际执行 {N} 条")
print(f"执行断言 {N} 条（基线 {BASELINE}）")
if BAD:
    print(f"❌ {len(BAD)} 条未过：")
    for b in BAD: print("  ✗", b)
    sys.exit(1)
print("✅ 全部通过")
