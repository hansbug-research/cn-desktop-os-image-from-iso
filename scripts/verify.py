#!/usr/bin/env python3
"""机器核对 report.md / README.md 里的每个声明。

约定：正文里的统计量必须能从 derived/stats.json 重算出来。这个脚本非 0 退出即不得提交。
它同时核对断言总数自洽 —— 正文声明的条数必须等于实际执行的条数。

⚠️ 它只覆盖被写成断言的那些数字。未被覆盖的仍需人工核对，
不要把「verify 全绿」等同于「每个数字都被机器核过」。
"""
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
    pat = ctx.format(v=s) if ctx else rf"(?<![0-9]){re.escape(str(s))}(?![0-9])"
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
in_text(S["existence_probes"], label="存在性探测条数", ctx=rf"{S['existence_probes']} 条存在性探测")

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
        ctx=rf"源只提供 {S['uos_apt_repo_packages']} 个包")
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
for k, lbl in (("installable_kylin11", "麒麟 V11"), ("installable_kylin10", "麒麟 V10"),
               ("installable_uos25", "UOS V25")):
    in_text(S[k], where="readme", label=f"README 可装性 {lbl}",
            ctx=rf"\*\*{S[k]} / {S['installability_tools']}\*\*")
    in_text(S[k], where="report", label=f"report 可装性 {lbl}",
            ctx=rf"\*\*{S[k]} / {S['installability_tools']}\*\*")
in_text(S["uos_iso_packages"], where="readme", label="README 的 UOS ISO 包数")
for row in (ROOT / "derived" / "tables" / "t04_built_images.csv").read_text().splitlines()[1:]:
    c = row.split(",")
    in_text(f"{c[3]} MB / {c[5]} 包", where="readme", label=f"README 九镜像表 {c[0]}:{c[1]}",
            ctx=r"{v}")

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
    ok(re.search(rf"(?<![0-9]){n} 个", REPORT) is not None,
       f"正文应写明 {nm} 的 masked 单元数 {n}（需带数字边界，否则 11 会被 111 满足）")
in_text(S["setuid_micro"]["kylin10"], label="V10 micro 的 setuid 数",
        ctx=rf"V10 micro 档有 {S['setuid_micro']['kylin10']} 个")
in_text(S["setuid_micro"]["kylin11"], label="micro 的 setuid 数",
        ctx=rf"各只有 {S['setuid_micro']['kylin11']} 个 setuid")
in_text(S["cells_supported"], label="支持格数", ctx=rf"支持 {S['cells_supported']}、")
in_text(S["cells_gap"], label="缺口格数", ctx=rf"缺口 {S['cells_gap']}、")
in_text(S["cells_na"], label="不适用格数", ctx=rf"不适用 {S['cells_na']}")
in_text(S["mutation_caught"], label="变异用例数", ctx=rf"变异用例 \*\*{S['mutation_caught']}\*\* 条")

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
    (S["existence_probes"], r"{v} 条存在性探测", "README 结论 3 探测数"),
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
for k, v in S["keyrings_by_image"].items():
    if k.startswith("kylin"):
        ok(v == ["kylin-archive-keyring.gpg"],
           f"{k} 的 keyring 应只有 kylin-archive-keyring.gpg，实际 {v}")

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

# 断言总数基线。没有它，删掉 artifacts/repro-evidence.txt 会让 7 条交叉断言整块被
# if 跳过，断言数从 113 悄悄掉到 106 而汇总照样全绿 —— 证据消失即断言消失。
# 这与 test/verify.sh 里对镜像检查数设基线是同一个道理，之前只给那边设了。
BASELINE = int(os.environ.get("VERIFY_BASELINE", "165"))
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
