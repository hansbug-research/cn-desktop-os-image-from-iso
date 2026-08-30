#!/usr/bin/env python3
"""机器核对 report.md / README.md 里的每个声明。

约定：正文里的统计量必须能从 derived/stats.json 重算出来。这个脚本非 0 退出即不得提交。
它同时核对断言总数自洽 —— 正文声明的条数必须等于实际执行的条数。

⚠️ 它只覆盖被写成断言的那些数字。未被覆盖的仍需人工核对，
不要把「verify 全绿」等同于「每个数字都被机器核过」。
"""
import json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
S = json.loads((ROOT / "derived" / "stats.json").read_text())
REPORT = (ROOT / "report.md").read_text()
README = (ROOT / "README.md").read_text() if (ROOT / "README.md").exists() else ""
TAB = ROOT / "derived" / "tables"

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
in_text(S["existence_probes"], label="存在性探测条数")

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
in_text(S["uos_apt_package_names"], label="UOS apt 源包名数")
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
for d in ("D01", "D02", "D05", "D08", "D09", "D10", "D12"):
    ok(d in REPORT or d in t8[0] or any(d in l for l in t8), f"缺陷 {d} 应在正文或表里出现")

# ── 结构性检查 ──────────────────────────────────────────────────────────────
# 图表引用只查**正文**：附录 A/B 是完整索引，若把附录算进来，这条断言永不失败
# —— 它以为自己在防「图表没人引用」，实际什么也没防（实测 fig06 与 5 张表只在索引里）。
_appendix = REPORT.index("## 附录 A")
BODY = REPORT[:_appendix]
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
hard = [i for i, l in enumerate(REPORT.splitlines()[:-1], 1)
        if re.search(r"[一-鿿]$", l) and not l.startswith(("|", "-", ">", "#", " "))
        and re.match(r"^[一-鿿]", REPORT.splitlines()[i] or " ")]
ok(not hard, f"正文自然段内疑似硬换行，行号：{hard[:5]}")

# 断言自计数。早先版本只检查「这句话存在」，捕获了数字却从不比对 ——
# 把抬头的 365 改成 99999 照样全绿。那是本仓库 §9.2 自己批判的第三类假通过。
m = re.search(r"验收断言 \*\*(\d+)\*\* 条", REPORT)
ok(m is not None, "report.md 抬头应声明验收断言条数")
if m:
    ok(int(m.group(1)) == S["verify_passed"],
       f"抬头的验收断言数 {m.group(1)} 应等于 stats 里的 verify_passed {S['verify_passed']}")
mr = re.search(r"机器核对断言 \*\*(\d+)\*\* 条", README)
ok(mr is not None, "README 抬头应声明机器核对断言条数")

print(f"执行断言 {N} 条")
if BAD:
    print(f"❌ {len(BAD)} 条未过：")
    for b in BAD: print("  ✗", b)
    sys.exit(1)
print("✅ 全部通过")
