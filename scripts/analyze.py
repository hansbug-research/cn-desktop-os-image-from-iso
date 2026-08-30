#!/usr/bin/env python3
"""只读 raw/、只写 derived/。不联网、不调 docker。

这条分界线的意义：重跑分析不需要重跑实验。正文里的每个统计量都必须出自
derived/stats.json，不许在 Markdown 里手写。
"""
import json, pathlib, re, collections

ROOT = pathlib.Path(__file__).resolve().parent.parent
RAW, DER = ROOT / "raw", ROOT / "derived"
TAB = DER / "tables"; TAB.mkdir(parents=True, exist_ok=True)

def load(n): return json.loads((RAW / n).read_text())
def osrel(text):
    d = {}
    for l in (text or "").splitlines():
        if "=" in l:
            k, v = l.split("=", 1); d[k.strip()] = v.strip().strip('"')
    return d
def csv(name, header, rows):
    out = [",".join(header)]
    for r in rows:
        out.append(",".join('"' + str(x).replace('"', '""') + '"' if any(c in str(x) for c in ',"\n')
                            else str(x) for x in r))
    (TAB / name).write_text("\n".join(out) + "\n")

d1, d2, d3, d4, d5, d6, d7 = (load(f"d{i}_{n}.json") for i, n in
    [(1, "official_images"), (2, "our_images"), (3, "capabilities"), (4, "gates"),
     (5, "iso_and_defects"), (6, "installability"), (7, "cve")])
S = {}

# ── T01 官方容器镜像可获得性 ────────────────────────────────────────────────
rows = []
for im in d1["images"]:
    o = osrel(im.get("os_release", ""))
    counts = (im.get("pkg_count") or "").split("\n")
    n = next((c for c in counts if c.strip() and c.strip() != "0"), "0")
    rows.append([im["vendor"], im["product"], im["ref"], "可拉取" if im["available"] else "拉取失败",
                 o.get("NAME", ""), o.get("ID", ""), o.get("VERSION_ID", ""),
                 im.get("pkg_format", ""), n.strip(),
                 re.sub(r".*\)\s*", "", im.get("glibc", "")) or im.get("glibc", "")])
csv("t01_official_image_availability.csv",
    ["vendor", "product", "ref", "status", "os_name", "os_id", "version_id", "pkg_format", "pkg_count", "glibc"], rows)
S["official_probed"] = len(d1["images"])
S["official_available"] = sum(1 for i in d1["images"] if i["available"])

# ── T02 存在性探测（桌面镜像到底有没有）────────────────────────────────────
rows = [[p["ref"], "存在" if p["exists"] else "不存在", p.get("stderr_tail", "")[:120]]
        for p in d1.get("existence_probes", [])]
csv("t02_registry_existence_probes.csv", ["ref", "result", "evidence"], rows)
S["existence_probes"] = len(rows)
S["existence_found"] = sum(1 for p in d1.get("existence_probes", []) if p["exists"])
S["kylin_desktop_official_images"] = sum(
    1 for p in d1.get("existence_probes", []) if p["exists"] and "desktop" in p["ref"])
S["uos_official_images"] = sum(
    1 for p in d1.get("existence_probes", []) if p["exists"] and "uniontech" in p["ref"])

# ── T03 产品线对照：官方 server 镜像 vs 我们从桌面 ISO 造的 ────────────────
off = d2["official_reference"]; oo = osrel(off["os_release"])
def line(tag, img, o, rec):
    return [tag, img, o.get("NAME", ""), o.get("ID", ""), o.get("VERSION_ID", ""),
            rec["pkg_format"], rec.get("glibc_pkg", ""),
            (rec.get("repo_urls", "").splitlines() or [""])[0][:80]]
rows = [line("厂商官方", off["image"], oo, off)]
for r in d2["ours"]:
    if r["tier"] == "base":
        rows.append(line("本项目自建", r["image"], osrel(r["os_release"]), r))
csv("t03_product_line_comparison.csv",
    ["kind", "image", "os_name", "os_id", "version_id", "pkg_format", "glibc", "repo_url_sample"], rows)
S["official_pkg_format"] = off["pkg_format"]
S["ours_pkg_formats"] = sorted({r["pkg_format"] for r in d2["ours"]})
S["os_id_collision"] = (oo.get("ID") == osrel(
    next(r for r in d2["ours"] if r["distro_id"] == "kylin10")["os_release"]).get("ID"))

# ── T04 九个镜像的构建产物事实 ──────────────────────────────────────────────
rows = []
for r in d2["ours"]:
    o = osrel(r["os_release"])
    n = [c for c in (r.get("pkg_count") or "").split("\n") if c.strip() and c.strip() != "0"]
    rows.append([r["distro_id"], r["tier"], r["image"],
                 round(r["tar_bytes"] / 1e6) if r.get("tar_bytes") else "",
                 r.get("unpacked_human", ""),
                 (n[0].strip() if n else ""), o.get("VERSION_ID", ""), r.get("glibc_pkg", ""),
                 r.get("stopsignal", "") or "—", r.get("tar_sha256", "")[:16]])
csv("t04_built_images.csv",
    ["distro", "tier", "image", "rootfs_tar_mb", "unpacked_size", "packages", "version_id",
     "glibc", "stopsignal", "tar_sha256_16"], rows)
S["images_built"] = len(d2["ours"])
S["tiers"] = sorted({r["tier"] for r in d2["ours"]})
S["distros"] = sorted({r["distro_id"] for r in d2["ours"]})

# ── T05 能力矩阵（三态）──────────────────────────────────────────────────────
# 三态语义：Y=支持（实测通过）／N=不支持（该档位确有此需求却不满足，是缺口）／
# NA=不适用（该档位定位下这一需求不存在）。
#
# 「不适用」只在有明确定位依据时才用，不拿它掩盖缺口。档位定位：
#   micro = 纯运行时（应用在别处构建好再拷进来，不装包、不编译、不做运维排查）
#   base  = 平台可用（有包管理、能装东西、能排查，但不预置工具链）
#   devel = 构建用（工具链齐备）
# 这份策略是矩阵表与热力图的**唯一真源** —— 两处各写一份必然漂移。
NA_POLICY = {
    "micro": {"apt", "apt_update", "apt_roundtrip", "apt_check", "sources_list", "apt_keyring",
              "cc_present", "compile_c", "static_link", "cxx_present", "compile_cxx", "cxx17",
              "cxx20", "libc_headers", "binutils", "make", "make_build", "pkgconfig", "cmake",
              "autotools", "cc_clean_stderr", "python3_dev", "python3", "python3_run",
              "python3_ssl", "perl", "git", "zstd", "unzip", "ps", "top", "sock_tools",
              "ip_tools", "ping", "dnsutil", "file", "pager", "editor", "lsof", "strace", "gdb",
              "useradd", "useradd_works", "su_to_user", "systemd", "sudo"},  # policy_rcd 不在此列：verify.sh 对九个镜像一律要求它为 Y
    # base 的 NA 集里原先有 strace —— 但 §3 给 base 的定位明写了「线上排查」，
    # 而 strace 是纯排查工具、不依赖工具链，把它判成「不适用」与定位直接冲突。
    # 改为如实记 N（麒麟侧一条 apt 就有，见 t11；UOS 侧是真缺口）。
    # gdb 保留 NA：它要调试符号与工具链生态，属 devel 范畴。
    "base":  {"cc_present", "compile_c", "static_link", "cxx_present", "compile_cxx", "cxx17",
              "cxx20", "libc_headers", "binutils", "make", "make_build", "pkgconfig", "cmake",
              "autotools", "cc_clean_stderr", "python3_dev", "git", "gdb", "sudo"},
    "devel": {"sudo"},
}
# 探针输出里有两类东西，不能混算：
#   INFO_PROBES 是**环境指纹**（架构、glibc 版本、setuid 数量……），值是版本号或计数，
#     不是「支持/不支持」。早先版本把它们塞进布尔判据 `v == "Y" else "N"`，
#     于是 6 项 × 9 镜像里凭空多出 49 个假「缺口」——占当时缺口总数的近一半。
#   probe_complete 是**哨兵**（探针有没有跑完），也不是能力项。
# 指纹另出一张 t10 表，哨兵由 collect 阶段硬断言，两者都不进三态矩阵。
INFO_PROBES = {"arch", "glibc", "os_id", "setuid_bins", "file_caps", "default_target"}
SENTINELS = {"probe_complete"}
# 早先把 sudo 从矩阵里删掉，理由写成「九档全是 NA、从未被真判定过」—— 这与数据相反：
# 探针实测九档全部是 N（t05b 可查），它压根不在任何 NA_POLICY 集合里，`tri()` 会把它
# 算成 9 格缺口，删掉它等于把缺口从 61 压到 52。现在改回正路：sudo 按档位定位归入
# 三档的 NA 集（容器内默认就是 root，非 root 场景用 USER 指令而非提权），
# 排除动作取消，去向在 report.md §6.1 里显式披露。
EXCLUDED = set()

probes = d3["probes"]
allkeys = sorted({k for v in probes.values() for k in v if not k.startswith("_")})
keys = [k for k in allkeys if k not in INFO_PROBES and k not in SENTINELS and k not in EXCLUDED]
order = [f"{d}:{t}" for d in ["kylin11", "kylin10", "uos25"] for t in ["micro", "base", "devel"]]

def tri(col, key):
    tier = col.split(":")[1]
    if key in NA_POLICY.get(tier, set()):
        return "NA"
    v = probes[col].get(key, "")
    if v in ("n/a", ""):
        return "NA"
    return "Y" if v == "Y" else "N"

csv("t05_capability_matrix.csv", ["capability"] + order,
    [[k] + [tri(c, k) for c in order] for k in keys])
csv("t05b_capability_raw.csv", ["capability"] + order,
    [[k] + [probes[c].get(k, "") for c in order] for k in allkeys])
# t10 环境指纹：这些是事实不是能力，单独成表
# ⚠️ 探针的 os_id 输出的是 `ID-VERSION_ID`（如 kylin-v11），不是裸 ID。
# 直接以 os_id 为名列出来，会让读者以为三家 ID 各不相同，与「麒麟官方与桌面的
# os-release ID 都是 kylin」这条核心论点当面矛盾（裸 ID 的证据在 t01/t03）。
# 这里改名为 os_id_version 如实标注。
_FP_LABEL = {"os_id": "os_id_version（ID-VERSION_ID，裸 ID 见 t01/t03）"}
csv("t10_environment_fingerprint.csv", ["fingerprint"] + order,
    [[_FP_LABEL.get(k, k)] + [probes[c].get(k, "") for c in order] for k in sorted(INFO_PROBES)])
S["capability_items"] = len(keys)
S["info_probes"] = len(INFO_PROBES)
S["capability_cells"] = len(keys) * len(order)
S["probe_complete_all"] = all(v.get("_probe_complete") == "Y" for v in probes.values())
_tri = [tri(c, k) for k in keys for c in order]
S["cells_supported"] = _tri.count("Y")
S["cells_gap"] = _tri.count("N")
S["cells_na"] = _tri.count("NA")

# ── T06 编译能力（本研究的首要用途）────────────────────────────────────────
CC = ["compile_c", "static_link", "compile_cxx", "cxx17", "cxx20", "make_build",
      "cc_clean_stderr", "cmake", "autotools", "pkgconfig", "python3_dev"]
csv("t06_build_capability.csv", ["capability"] + order,
    [[k] + [probes[c].get(k, "") for c in order] for k in CC])
S["devel_c_ok"] = sum(1 for c in order if c.endswith(":devel") and probes[c].get("compile_c") == "Y")
S["devel_cxx_ok"] = sum(1 for c in order if c.endswith(":devel") and probes[c].get("compile_cxx") == "Y")
S["devel_count"] = sum(1 for c in order if c.endswith(":devel"))

# ── T07 门禁结果 ────────────────────────────────────────────────────────────
g = d4["gates"]
csv("t07_gates.csv", ["gate", "result", "detail"], [
    ["verify", f"{g['verify']['passed']} 通过 / {g['verify']['failed']} 失败",
     f"基线 {g['verify']['baseline']}"],
    ["digest-chain", f"{g['digest_chain']['passed']} 通过 / {g['digest_chain']['failed']} 失败",
     "manifest = tar = 镜像"],
    ["sbom", "全部可生成" if g["sbom"]["all_ok"] else "有失败", f"{len(g['sbom']['rows'])} 行"],
    ["mutation", f"{g['mutation']['caught']} 抓到 / {g['mutation']['missed']} 漏",
     f"{g['mutation']['skipped']} 跳过"],
    ["repro", f"{g.get('repro',{}).get('identical',0)} 逐位一致", "同 builder 连构两次"],
])
S["verify_passed"] = g["verify"]["passed"]; S["verify_failed"] = g["verify"]["failed"]
S["verify_baseline"] = g["verify"]["baseline"]
S["digest_chain_passed"] = g["digest_chain"]["passed"]
S["mutation_caught"] = g["mutation"]["caught"]; S["mutation_missed"] = g["mutation"]["missed"]
S["repro_identical"] = g.get("repro", {}).get("identical", 0)
S["manifests"] = len(d4["manifests"])

# ── T08 厂商缺陷清单 ────────────────────────────────────────────────────────
csv("t08_vendor_defects.csv", ["id", "distro", "title", "symptom", "root_cause", "impact", "fix", "where"],
    [[x["id"], x["distro"], x["title"], x["symptom"], x["root_cause"], x["impact"], x["fix"], x["where"]]
     for x in d5["defects"]])
S["defects"] = len(d5["defects"])
S["defects_by_distro"] = dict(collections.Counter(x["distro"] for x in d5["defects"]))

# ── T09 三条构建路径 ────────────────────────────────────────────────────────
csv("t09_build_paths.csv",
    ["distro", "method", "suite", "expect_glibc", "expect_glibcxx", "usrmerge", "immutable"],
    [[i["distro_id"], i["method"], i["suite"], i["expect_glibc"], i["expect_glibcxx"],
      i["usrmerge"] or "", i["immutable"] or ""] for i in d5["isos"]])
S["build_methods"] = sorted({i["method"] for i in d5["isos"]})

# ── T11 工具可装性：区分「没预装」与「装不上」的定量依据 ────────────────────
def _cand(k, t):
    """candidates[t] 形如 `iproute2: iproute2 | 6.1.0-ok1k0.1 | http://…`。
    早先按 `:` 切第一段，拿到的是包名而不是版本，整张明细表退化成工具名重复三遍。
    这里取 madison 输出的第二段（版本号），那才是「装得上、装的是哪版」的信息。"""
    v = d6["images"][k]["candidates"].get(t, "NOREPO")
    if v == "NOREPO":
        return "装不上"
    parts = [x.strip() for x in v.split("|")]
    return parts[1] if len(parts) > 1 else v
rows = [[t] + [_cand(k, t) for k in ("kylin11", "kylin10", "uos25")] for t in d6["tools"]]
csv("t11_tool_installability.csv", ["tool", "kylin11", "kylin10", "uos25"], rows)
for k in ("kylin11", "kylin10", "uos25"):
    S[f"installable_{k}"] = d6["images"][k]["installable"]
S["installability_tools"] = len(d6["tools"])
S["uos_iso_packages"] = (d6.get("uos_iso_inventory") or {}).get("package_count")
_has = (d6.get("uos_iso_inventory") or {}).get("has", {})
S["uos_iso_has_gxx"] = _has.get("g++")
S["uos_iso_missing"] = sorted(k for k, v in _has.items() if v is False)
# UOS apt 源规模：从 apt-cache stats 的原文里取
import re as _re
# 源规模用索引条目数，不用 Total package names（后者含已装与被引用的名字）
_sc = d6.get("uos_apt_scale") or ""
_m = _re.search(r"---repo-entries---\s*\n\s*(\d+)", _sc)
S["uos_apt_repo_packages"] = int(_m.group(1)) if _m else None
_m0 = _re.search(r"Total package names:\s*(\d+)", _sc)
S["uos_apt_total_names"] = int(_m0.group(1)) if _m0 else None
# 阳性对照：源里真实存在的包必须查得到，用来区分「源里没有」与「源没通」
S["uos_apt_positive_control"] = bool(_re.search(r"---positive-control---\s*\nsample=\S+\n\s*\S+\s*\|", _sc))
_m2 = _re.search(r"Normal packages:\s*(\d+)", d6.get("uos_apt_scale") or "")
S["uos_apt_normal_packages"] = int(_m2.group(1)) if _m2 else None

# ── T12 masked 单元与 setuid 面（随发行版而变，不能在正文写死）────────────────
rows = []
for r in d2["ours"]:
    rows.append([r["distro_id"], r["tier"],
                 len((r.get("masked_units") or "").split()),
                 len((r.get("setuid_bins") or "").split())])
csv("t12_hardening_surface.csv", ["distro", "tier", "masked_units", "setuid_bins"], rows)
# 信任面：每个镜像装了哪些 keyring。麒麟两版走在线源、需要它自己那把；
# UOS 走切片、不该出现麒麟的 key。
S["keyrings_by_image"] = {f'{r["distro_id"]}:{r["tier"]}':
                          sorted((r.get("keyrings") or "").split())
                          for r in d2["ours"]}
S["alien_keyring_images"] = sorted(
    k for k, v in S["keyrings_by_image"].items()
    if k.startswith("uos25") and any("kylin" in x for x in v))
S["masked_units_by_distro"] = {r["distro_id"]: len((r.get("masked_units") or "").split())
                               for r in d2["ours"] if r["tier"] == "base"}
S["setuid_micro"] = {r["distro_id"]: len((r.get("setuid_bins") or "").split())
                     for r in d2["ours"] if r["tier"] == "micro"}
# sbom 通过数：原先正文写 9/9 却没有统计量，fig05 里是手写常量
_sb = [r for r in d4["gates"]["sbom"]["rows"] if len(r) >= 4 and r[3] == "✅"]
S["sbom_passed"] = len(_sb)
S["mutation_skipped"] = d4["gates"]["mutation"]["skipped"]

# ── T13 漏洞扫描器的覆盖判定 ────────────────────────────────────────────────
# 判定事实（真实 ID vs trivy 判定）而非漏洞明细：明细随库更新而漂，判定不会。
csv("t13_cve_coverage.csv",
    ["image", "real_os_id", "trivy_os_family", "trivy_os_name", "high_critical", "verdict"],
    [[x["image"], x["real_os_id"], x["trivy_os_family"], x["trivy_os_name"],
      x["high_critical"], x["verdict"]] for x in d7["images"]])
_v = collections.Counter(x["verdict"] for x in d7["images"])
S["cve_effective_coverage"] = _v.get("有效覆盖", 0)
S["cve_misidentified"] = _v.get("误判", 0)
S["cve_unrecognized"] = _v.get("未识别", 0)
S["cve_high_critical_total"] = sum(x["high_critical"] for x in d7["images"])
S["cve_scanner"] = d7["scanner"]

(DER / "stats.json").write_text(json.dumps(S, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
print(f"derived/：{len(list(TAB.glob('*.csv')))} 张表，stats.json {len(S)} 个统计量")
