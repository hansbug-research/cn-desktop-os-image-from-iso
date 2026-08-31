#!/usr/bin/env python3
"""只读 raw/、只写 derived/。不联网、不调 docker。

这条分界线的意义：重跑分析不需要重跑实验。正文里的每个统计量都必须出自
derived/stats.json，不许在 Markdown 里手写。
"""
import json, sys, pathlib, re, collections

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from _subjects import DIDS, TIERS, IMAGES
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
# d8 是国产桌面 OS 全名录 + 镜像实测。它比其余数据集晚加入，且可能在名录还没定稿时
# 就有人跑 analyze —— 缺就跳过对应表，但**不静默**：缺了要在 stats 里留痕，
# 否则「表没生成」与「表生成了但是空的」在输出上不可区分。
try:
    d8 = load("d8_os_census.json")
except FileNotFoundError:
    d8 = None
S = {}
S["census_present"] = d8 is not None
# 全局引用表：report 里每处 [Rn] 都指向它。放在 config/ 而不是 raw/，
# 因为它是文献而非测量 —— title_source 字段区分「抓自该页 <title>」与「人工标注」。
REFS = json.loads((ROOT / "config" / "references.json").read_text())["references"]
REF_BY_ID = {r["id"]: r for r in REFS}

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
rows = [[p["ref"], "存在" if p["exists"] else "不存在", p.get("stderr_tail", "") or "—（拉取成功，无 stderr）"]
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

# ── T14/T15 国产桌面 OS 全名录 ──────────────────────────────────────────────
# 刻意拆成两张表：t14 是**文献事实**（引官网/公告，每条带 source），
# t15 是**我们的实测**（registry 存在性，判据是退出码）。
# 合成一张会让读者无法分辨哪一格可以复核、哪一格只能溯源到厂商说法。
if d8:
    # 名录表：每个单元格自带引用标记（论文式），标记指向全局引用表 t16。
    # 早先是整行末尾堆一串 [[1]][[2]]、每行重新从 1 数起 —— 读者无法判断哪条支撑哪格。
    def _c(e, field):
        ids = e.get("refs", {}).get(field, [])
        # GitHub 原生脚注语法：[^Rn]。GitHub 会自动渲染成上标编号，
        # 并在文末生成带回跳链接的 Footnotes 区 —— 这是它的官方引用形态，
        # 比手写 [Rn](#Rn) 锚点链接更正规（早先那版方向搞反了）。
        return "".join(f"[^{i}]" for i in ids)

    rows = []
    for e in d8["entries"]:
        img = "有（非桌面）" if e["name"] in S.get("census_os_with_any_image", []) else "未公开"
        rows.append(["★" if e.get("subject") else "",
                     e["name"],
                     "商业" if e["type"].startswith("商业") else "社区开源",
                     e["vendor"],
                     e.get("s_lineage", e["lineage"]) + _c(e, "s_lineage"),
                     e.get("s_version", e["latest_version"]) + _c(e, "s_version"),
                     e.get("s_desktop", e["desktop"]) + _c(e, "s_desktop"),
                     (e.get("s_iso_access", "")
                      + ("（" + e["iso_access_qualifier"] + "）"
                         if e.get("iso_access_qualifier") else "")
                      + _c(e, "s_iso_access")),
                     e.get("s_customers", "") + _c(e, "s_customers"),
                     # 维护状态：优先用显式的短限定 s_maintained；没有就取首段。
                     # 不能一律截到「（」——那会把「品牌活跃（桌面线最近更新未查到）」
                     # 削成无条件的「品牌活跃」。
                     e.get("s_maintained") or e["maintained"].split("（")[0].split("：")[0],
                     img + _c(e, "image"),
                     _c(e, "general")])
    csv("t14_os_census.csv",
        ["subject", "os", "type", "vendor", "lineage", "latest_version", "desktop",
         "iso_access", "customers", "maintained", "official_image", "other_refs"], rows)

    rows = []
    for e in d8["entries"]:
        rows.append([e["name"], e["lineage"], e["latest_version"], e["desktop"],
                     e["maintained"], e.get("iso_access_note", ""),
                     e.get("official_image_note", "")])
    csv("t14b_os_census_detail.csv",
        ["os", "lineage_full", "version_full", "desktop_full", "maintained_full",
         "iso_access_note", "customers_note", "official_image_note"], rows)

    rows = []
    for pr in d8["probes"]:
        o = osrel(pr.get("os_release", ""))
        rows.append([pr["for_os"], pr["ref"], "存在" if pr["exists"] else "不存在",
                     pr.get("probe_method", ""), pr.get("pkg_format", ""),
                     o.get("NAME", ""), o.get("VERSION_ID", ""),
                     (pr.get("stderr_tail", "") or "—（探测成功，无 stderr）")])
    csv("t15_os_image_probes.csv",
        ["os", "ref", "result", "method", "pkg_format", "os_name", "version_id",
         "evidence"], rows)

    # t16 参考来源表。title_source 一列必须留着 —— 它区分「标题抓自该页」与
    # 「该页没有 title、标题是我们写的」，读者据此判断这条引用的可核对程度。
    csv("t16_references.csv",
        ["id", "publisher", "title", "url", "title_source", "accessed", "note"],
        [[r["id"], r["publisher"], r["title"], r["url"],
          r["title_source"], r["accessed"], r.get("note", "")] for r in REFS])
    S["references_total"] = len(REFS)
    S["references_title_from_page"] = sum(1 for r in REFS if r["title_source"] == "page")
    S["references_title_manual"] = sum(1 for r in REFS if r["title_source"] == "manual")
    S["census_field_citations"] = sum(len(v) for e in d8["entries"]
                                      for v in e.get("refs", {}).values())
    # 名录里的引用必须都能在引用表里找到 —— 悬空引用等于假引用
    _cited = {i for e in d8["entries"] for v in e.get("refs", {}).values() for i in v}
    S["census_dangling_refs"] = sorted(_cited - set(REF_BY_ID))
    # ISO 获取一列：以「直连能否 HEAD 到真实字节」为判据而非厂商说法。
    # 「未实测」必须单独成类 —— 把它并进「可下载」就是把查不到当成了有。
    # 四类，不是三类：「公开列出但直链未解引用」必须单独成类 ——
    # 它既不是「我们 HEAD 到了字节」，也不是「厂商设了门槛」，归进任一类都是失真。
    # 分类是受控取值（见 config 的 s_iso_access），形态差异走 iso_access_qualifier。
    # 早先用自由文本当分类，一个条目被算进两类，合计 23 > 21，断言当场抓到。
    # 五类受控取值。「网盘分发」与「未查到公开下载」是复核后新增的两类：
    # 前者既不是 HTTP 直链也不是设了门槛（提取码就明文印在页面上），
    # 后者与「需授权」的区别在于我们并未看到任何门槛、是根本找不到条目 —— 归并会失真。
    _ISO_CLS = ("直接下载", "公开列出·直链未解引用", "网盘分发",
                "需申请授权或登录", "未查到公开下载", "未实测或未查到")
    _by = {k: sorted(e["name"] for e in d8["entries"]
                     if e.get("s_iso_access") == k) for k in _ISO_CLS}
    S["iso_direct"] = _by["直接下载"]
    S["iso_public_unresolved"] = _by["公开列出·直链未解引用"]
    S["iso_netdisk"] = _by["网盘分发"]
    S["iso_gated"] = _by["需申请授权或登录"]
    S["iso_not_found"] = _by["未查到公开下载"]
    S["iso_unverified"] = _by["未实测或未查到"]
    S["iso_class_unknown"] = sorted(e["name"] for e in d8["entries"]
                                    if e.get("s_iso_access") not in _ISO_CLS)
    S["iso_access_missing"] = sorted(e["name"] for e in d8["entries"]
                                     if not e.get("s_iso_access"))
    S["customers_missing"] = sorted(e["name"] for e in d8["entries"]
                                    if not e.get("s_customers"))
    # 安可（安全可靠测评）桌面附表是这一列里唯一的第三方硬名录 —— 厂商自述与它必须分开。
    # 「在列」的家数由名录现算，不手写进正文。
    S["aqkk_desktop_listed"] = sorted(
        e["name"] for e in d8["entries"]
        if "安可桌面" in e.get("s_customers", "") and "在列" in e.get("s_customers", "")
        and "从未" not in e.get("s_customers", "") and "不在" not in e.get("s_customers", ""))
    S["aqkk_desktop_absent"] = sorted(
        e["name"] for e in d8["entries"]
        if any(k in e.get("s_customers", "") for k in ("从未在列", "从未入安可", "不在安可", "未在列")))

    S["census_os_count"] = len(d8["entries"])
    S["census_commercial"] = sum(1 for e in d8["entries"] if e["type"].startswith("商业"))
    S["census_community"] = sum(1 for e in d8["entries"] if e["type"].startswith("社区"))
    S["census_probes"] = len(d8["probes"])
    S["census_probes_exist"] = sum(1 for p in d8["probes"] if p["exists"])
    S["census_subjects"] = [e["name"] for e in d8["entries"] if e.get("subject")]
    # 名录里每条都必须有出处 —— 这是本节的立论基础，不能有一条裸奔
    S["census_entries_without_source"] = [e["name"] for e in d8["entries"]
                                          if not e.get("sources")]
    # 「有官方镜像」与「有桌面版官方镜像」是两件事，分开计
    S["census_os_with_any_image"] = sorted(
        {p["for_os"] for p in d8["probes"] if p["exists"]})

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
    "micro": {"pkgmgr", "pkg_update", "pkg_roundtrip", "pkg_check", "pkg_sources", "pkg_keyring",
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
INFO_PROBES = {"arch", "glibc", "os_id", "setuid_bins", "file_caps", "default_target",
               # 以下四项随「探针按包管理系分支」一起加入，全是事实不是能力：
               "pkgsys",        # deb / rpm / none —— 该镜像的包管理系
               "pkgmgr_name",   # apt-get / dnf / none —— 具体是哪个包管理器
               "pkgdb_count",   # 包数据库里的条数
               "probe_sha"}     # 探针自身的版本指纹
SENTINELS = {"probe_complete"}
# 早先把 sudo 从矩阵里删掉，理由写成「九档全是 NA、从未被真判定过」—— 这与数据相反：
# 探针实测九档全部是 N（t05b 可查），它压根不在任何 NA_POLICY 集合里，`tri()` 会把它
# 算成 9 格缺口，删掉它等于把缺口从 61 压到 52。现在改回正路：sudo 按档位定位归入
# 三档的 NA 集（容器内默认就是 root，非 root 场景用 USER 指令而非提权），
# 排除动作取消，去向在 report.md §6.1 里显式披露。
EXCLUDED = set()

probes = d3["probes"]
allkeys = sorted({k for v in probes.values() for k in v if not k.startswith("_")})

# 结构门禁：tri() 的兜底分支是「不是 Y 就算 N」。对布尔项没问题，对**非布尔**的新增
# 探针项就是灾难 —— `pkgsys=rpm` 会被读成「不支持 pkgsys」，凭空多一行缺口，而且
# 看起来完全像一条正常的缺口，不报任何错。所以凡取值不在受控集合里的键，必须显式
# 归入 INFO_PROBES 或 SENTINELS；忘了分类就在这里当场失败，而不是产出假缺口。
_TRISTATE_OK = {"Y", "N", "n/a", "nosrc", "PARTIAL", ""}
_unclassified = {}
for _k in allkeys:
    if _k in INFO_PROBES or _k in SENTINELS or _k in EXCLUDED:
        continue
    _vals = {probes[c].get(_k, "") for c in probes}
    _odd = _vals - _TRISTATE_OK
    if _odd:
        _unclassified[_k] = sorted(_odd)[:4]
if _unclassified:
    sys.exit("!! 以下探针项取值不是三态，却没归入 INFO_PROBES/SENTINELS：\n" +
             "\n".join(f"   {k}: {v}" for k, v in _unclassified.items()) +
             "\n   —— 归类后再跑；不归类会让它们各自变成一行假缺口。")
keys = [k for k in allkeys if k not in INFO_PROBES and k not in SENTINELS and k not in EXCLUDED]
order = [f"{d}:{t}" for d in DIDS for t in TIERS]   # 唯一真源：config/subjects.json

def tri(col, key):
    tier = col.split(":")[1]
    if key in NA_POLICY.get(tier, set()):
        return "NA"
    v = probes[col].get(key, "")
    if v in ("n/a", ""):
        return "NA"
    # nosrc = 该档位有包管理器，但出厂时一个可用软件源都没有。归入缺口而不是
    # 「不适用」：档位定位说 base/devel 应当能从源装包，做不到就是缺口。
    # 也不能记成 Y —— 源清单为空时 `apt-get update` 会成功（没东西要取），
    # 空集上的全称命题恒真。原始值 nosrc 留在 t05b 里，缺口的**原因**可追。
    # PARTIAL 同理归入 N：装上了但没卸干净，不是完整的往返。
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
# 「无源」缺口单独计数：它与「有源但更新失败」在矩阵上都是缺口，成因完全不同，
# 前者是厂商没有公开在线仓库，后者是配置或网络问题。
S["cells_nosrc"] = sum(1 for c in order for k in keys if probes[c].get(k) == "nosrc")
S["nosrc_detail"] = sorted(f"{c}/{k}" for c in order for k in keys if probes[c].get(k) == "nosrc")
S["probe_complete_all"] = all(v.get("_probe_complete") == "Y" for v in probes.values())
# d3 的 provenance：探针输出必须不早于镜像。⚠️ 这条判据依赖 mtime，而 git 不保留 mtime
# —— 新克隆里 caps 文件的 mtime 是签出时刻，必然晚于镜像，所以它只在「原地重采」这一种
# 场景下有鉴别力，不能当作提交物的 provenance 保证。落进 stats 是为了至少让它可被断言、
# 可被读者看见其局限；真正的内容锚点要由探针在运行时写入（见 report §6.1 的说明）。
import datetime as _dt
_stale = []
for k, v in probes.items():
    pm, ic = v.get("_probe_mtime"), v.get("_image_created")
    if pm and ic and _dt.datetime.fromisoformat(pm) < _dt.datetime.fromisoformat(ic):
        _stale.append(k)
S["probe_stale_vs_image"] = sorted(_stale)
S["probe_provenance_recorded"] = sum(
    1 for v in probes.values() if v.get("_probe_mtime") and v.get("_image_created"))
_tri = [tri(c, k) for k in keys for c in order]
# 198 格「不适用」不是一类东西，按探针原始值拆开 —— 这三个数必须由这里算出来，
# 不许在正文手写（CLAUDE.md 第一条）。早先手写时把 6 格 cc_clean_stderr 错归成了
# apt 相关，README 那句因此是确凿错误。
_na_by_raw = collections.Counter()
_na_na_cells = []
for k in keys:
    for c in order:
        if tri(c, k) != "NA":
            continue
        v = probes[c].get(k, "")
        _na_by_raw["n/a" if v == "n/a" else ("Y" if v == "Y" else "N")] += 1
        if v == "n/a":
            _na_na_cells.append(f"{k}@{c}")
S["cells_na_from_N"] = _na_by_raw["N"]
S["cells_na_from_na"] = _na_by_raw["n/a"]
S["cells_na_from_Y"] = _na_by_raw["Y"]
# n/a 那 15 格的来源明细：哪些项、哪些档
S["na_na_detail"] = sorted(_na_na_cells)
S["na_na_by_item"] = dict(collections.Counter(x.split("@")[0] for x in _na_na_cells))
S["cells_supported"] = _tri.count("Y")
S["cells_gap"] = _tri.count("N")

# sudo 若按探针原始值计入缺口，缺口会是多少 —— §7 与 §9.2 都引这个基线（61）。
# 正文写死一个手算数正是 §9.2 批判的形态，所以从矩阵现算。
_sudo_n = sum(1 for c in order if probes[c].get("sudo", "") == "N")
S["sudo_cells_n"] = _sudo_n
S["cells_gap_if_sudo_counted"] = S["cells_gap"] + _sudo_n
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
    [[i["distro_id"], i["method"], i["suite"] or "—（无在线源）", i["expect_glibc"], i["expect_glibcxx"],
      i["usrmerge"] or "—", i["immutable"] or "no"] for i in d5["isos"]])
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
rows = [[t] + [_cand(k, t) for k in DIDS] for t in d6["tools"]]
csv("t11_tool_installability.csv", ["tool", *DIDS], rows)
for k in DIDS:
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
# 「采集之后又重建」这一类，mtime 守卫抓不到（它比的是采集时刻记下的两个时间，
# 镜像在采集之后重建时那一对永远自洽）。用镜像 ID 与 manifest 记录的 ID 对账才行。
S["image_id_mismatches"] = sorted(
    f'{r["distro_id"]}:{r["tier"]}' for r in d2["ours"]    if r.get("image_id") and d4["manifests"].get(f'{r["distro_id"]}-{r["tier"]}', {}).get("image_id")
    and r["image_id"] != d4["manifests"][f'{r["distro_id"]}-{r["tier"]}']["image_id"])


# 「解包后比 tar 大四成上下」这句原先是手写进正文的、没有任何统计量兜底的数，
# 且下界 37.8% 被我抹成了 38%（有一档真的低于 38%，属于把下界往上报）。
# 一律从 t04 现算，正文只允许引用这里的数。
def _mb(v):
    m = re.match(r"([\d.]+)\s*([KMG]?)B?", str(v).strip(), re.I)
    if not m:
        return None
    x, u = float(m.group(1)), m.group(2).upper()
    return x / 1024 if u == "K" else x * 1024 if u == "G" else x

_ovh = []
for _r in d2["ours"]:
    _t = _r["tar_bytes"] / 1e6 if _r.get("tar_bytes") else None
    _u = _mb(_r.get("unpacked_human", ""))
    if _t and _u:
        _ovh.append(round((_u - _t) / _t * 100, 1))
# 九个镜像一个都不能少，否则「区间」是在子集上算的
assert len(_ovh) == len(d2["ours"]), f"解包开销只算到 {len(_ovh)}/{len(d2['ours'])} 个镜像"
S["unpack_overhead_pct_min"] = min(_ovh)
S["unpack_overhead_pct_max"] = max(_ovh)
S["unpack_overhead_n"] = len(_ovh)

# UOS「连 nano 都没有」这句的证据绑定：既要 nano 无候选，也要对照组能查到——
# 少了对照组，「查不到」和「探测坏了」无法区分。
_scale = d6.get("uos_apt_scale", "")
_nano = _scale.split("---nano---")[-1] if "---nano---" in _scale else ""
S["uos_nano_candidate_none"] = "Candidate: (none)" in _nano
S["keyrings_by_image"] = {f'{r["distro_id"]}:{r["tier"]}':
                          sorted((r.get("keyrings") or "").split())
                          for r in d2["ours"]}
# 我们注入的（无属主的）keyring —— 只有这些才受「不该多一把」的约束；
# 厂商包自带的属发行版内容，动它就越过了「等价环境」的底线。
S["injected_keyrings_by_image"] = {f'{r["distro_id"]}:{r["tier"]}':
                                   sorted((r.get("keyrings_unowned") or "").split())
                                   for r in d2["ours"]}
# 「跨厂商 keyring」的判据原先写死 `k.startswith("uos25")` 且只找 kylin ——
# 那样只能抓 UOS 里混进麒麟 key 这一种，结构上抓不到别的组合。实测漏过一次：
# 凝思三档各留一把麒麟 keyring（它 NO_CHECK_GPG=yes、出厂无源，那把 key 无任何
# 消费方），这条判据全绿。现在改成通用：keyring 文件名里的厂商标识不属于本发行版
# 即为跨厂商。
_VENDOR_TAG = {"kylin11": "kylin", "kylin10": "kylin", "uos25": "uos",
               "kylinsec6": "kylinsec", "linx6": "linx"}
_alien = []
for k, v in S["keyrings_by_image"].items():
    _did = k.split(":")[0]
    _own = _VENDOR_TAG.get(_did, _did)
    for _f in v:
        _tags = [t for t in _VENDOR_TAG.values() if t in _f]
        if _tags and _own not in _tags:
            _alien.append(k); break
S["alien_keyring_images"] = sorted(set(_alien))
# ⚠️ 不能写 `r.get(...) or 0` —— 字段不在落盘数据里时读成 0，断言就变成空转
# （实测：collect_d2 改了但 d2 没重采，三档全 0 全绿）。缺键必须显式失败。
_missing_adl = [f'{r["distro_id"]}:{r["tier"]}' for r in d2["ours"]
                if r["tier"] == "micro" and r.get("active_deb_lines") is None]
S["micro_active_deb_missing"] = _missing_adl
S["micro_active_deb_lines"] = {
    f'{r["distro_id"]}:{r["tier"]}':
        int((r["active_deb_lines"] or "0").strip().splitlines()[0] or 0)
        + int((r.get("active_deb822_lines") or "0").strip().splitlines()[0] or 0)
    for r in d2["ours"]
    if r["tier"] == "micro" and r.get("active_deb_lines") is not None}
S["micro_sources_list_bytes"] = {f'{r["distro_id"]}:{r["tier"]}': int(r.get("sources_list_bytes") or 0)
                                 for r in d2["ours"] if r["tier"] == "micro"}
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

# ── 锚点对账：d6/d7 记录的被测镜像必须与 d2 的产物同一批 ────────────────────
# 早先 d6/d7 只记镜像 tag，镜像一重建它们就悄悄锚在旧产物上，而任何门禁都发现不了
# —— 正是 report §8 讲的「两条链锚在不同构建上，看着都绿其实接不起来」。
_d2_tar = {f'{r["distro_id"]}:{r["tier"]}': r.get("tar_sha256") for r in d2["ours"]}
# ⚠️ 判据不能写成 `if a and ref and a != ref` —— ref 一空（tar 不在、manifest 格式变了
# 都会让 d2 的 tar_sha256 变空串）整条对账就无声跳过，12 对悄悄变 11 对而仍然全绿。
# 所以既要记**实际比过多少对**，也要校验两侧都是 64 位 hex。
_mismatch = []; _pairs = 0; _badhex = []
for k, v in _d2_tar.items():
    if not (isinstance(v, str) and len(v) == 64 and all(c in "0123456789abcdef" for c in v)):
        _badhex.append(k)
for x in d6["images"].values():
    a = x.get("anchor_tar_sha256")
    # image 名 → did 的反查。先前是链式 .replace()，加被试就要再加一行；
    # 改为从 config/subjects.json 现算。
    _img2did = {v: k for k, v in IMAGES.items()}
    _base = x["image"].split(":")[0]
    ref = _d2_tar.get(_img2did.get(_base, _base)
                      .replace("kylin-desktop-v10", "kylin10")
                      .replace("uos-desktop-v25", "uos25") + ":base")
    if not a or not ref:
        _mismatch.append(("d6-锚点或参照缺失", x["image"]))
    else:
        _pairs += 1
        if a != ref:
            _mismatch.append(("d6", x["image"]))
for x in d7["images"]:
    a = x.get("anchor_tar_sha256")
    ref = _d2_tar.get(f'{x["distro_id"]}:{x["image"].rsplit(":", 1)[1]}')
    if not a or not ref:
        _mismatch.append(("d7-锚点或参照缺失", x["image"]))
    else:
        _pairs += 1
        if a != ref:
            _mismatch.append(("d7", x["image"]))
# d2 ↔ d4 那条边原先缺着：三条链只连了两条边，三方同改成同一个假哈希就能全绿通过。
# d4 在 CI 里是从已提交的 artifacts/*.manifest 反向重算的，补上这条边，d2/d4/d6/d7 四方闭合；artifacts/*.manifest 那一侧由 CI 的反向重算保证。
_d4 = {k: v.get("tarball_sha256") for k, v in d4["manifests"].items()}
for k, v in _d2_tar.items():
    ref = _d4.get(k.replace(":", "-"))
    if ref and v and ref != v:
        _mismatch.append(("d2↔d4-manifest", k))
    elif not ref:
        _mismatch.append(("d4-manifest 缺失", k))
# f4-digest.log 的前缀 vs manifest 的 sha256：多连一条独立见证的边
_pref = d4["gates"].get("digest_prefixes") or {}
for k, pre in _pref.items():
    full = _d4.get(k)
    if not full or not full.startswith(pre):
        _mismatch.append(("f4-digest.log 前缀", k))
S["digest_log_prefixes_checked"] = len(_pref)
S["anchor_pairs_checked"] = _pairs
S["anchor_bad_hex"] = _badhex
S["anchor_mismatches"] = _mismatch
S["anchored_records"] = (sum(1 for x in d6["images"].values() if x.get("anchor_tar_sha256"))
                         + sum(1 for x in d7["images"] if x.get("anchor_tar_sha256")))

(DER / "stats.json").write_text(json.dumps(S, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
print(f"derived/：{len(list(TAB.glob('*.csv')))} 张表，stats.json {len(S)} 个统计量")
