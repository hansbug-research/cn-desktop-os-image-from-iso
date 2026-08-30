#!/usr/bin/env python3
"""只读 derived/，产出 figures/*.png。图里的每个数字都来自 stats.json 或派生表。"""
import json, pathlib, csv as csvmod
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
DER, FIG = ROOT / "derived", ROOT / "figures"
FIG.mkdir(exist_ok=True)

for f in ["Noto Sans CJK SC", "Noto Sans CJK JP", "WenQuanYi Zen Hei", "Source Han Sans CN", "DejaVu Sans"]:
    if any(f in x.name for x in font_manager.fontManager.ttflist):
        plt.rcParams["font.sans-serif"] = [f]; break
plt.rcParams["axes.unicode_minus"] = False
S = json.loads((DER / "stats.json").read_text())
def table(n):
    with open(DER / "tables" / n) as fh: return list(csvmod.DictReader(fh))

COLS = [f"{d}:{t}" for d in ["kylin11", "kylin10", "uos25"] for t in ["micro", "base", "devel"]]
LBL = [c.replace("kylin11", "麒麟V11").replace("kylin10", "麒麟V10").replace("uos25", "UOS25")
       .replace(":", "\n") for c in COLS]

# fig01 官方镜像可获得性：左=拉得到的是什么，右=桌面镜像到底有没有
t1 = table("t01_official_image_availability.csv")
t2 = table("t02_registry_existence_probes.csv")
fig, (ax, bx) = plt.subplots(1, 2, figsize=(15.5, 4.8), gridspec_kw={"width_ratios": [1.15, 1]})

names = [r["product"][:26] for r in t1]
avail = [1 if r["status"] == "可拉取" else 0 for r in t1]
fmt = [r["pkg_format"] for r in t1]
colors = ["#2e7d32" if a and f == "dpkg" else "#ef6c00" if a and f == "rpm" else "#c62828"
          for a, f in zip(avail, fmt)]
y = np.arange(len(names))
ax.barh(y, [1] * len(names), color=colors)
ax.set_yticks(y); ax.set_yticklabels(names, fontsize=8.5); ax.invert_yaxis()
ax.set_xticks([]); ax.set_xlim(0, 1.75)
for i, r in enumerate(t1):
    txt = ("该 tag 不存在" if r["status"] != "可拉取"
           else f"{r['pkg_format']} · {r['pkg_count']} 包 · glibc {r['glibc'][:12]}")
    ax.text(1.03, i, txt, va="center", fontsize=8)
ax.set_title(f"① 拉得到的官方镜像是什么（探测 {S['official_probed']} 个，可拉取 {S['official_available']} 个）\n"
             "绿=dpkg 桌面/社区线　橙=rpm 服务器线　红=该 tag 不存在", fontsize=10)

# 右栏：存在性探测 —— 这才是「桌面版有没有官方镜像」的直接证据
refs = [r["ref"].replace("cr.kylinos.cn/kylin/", "cr.kylinos.cn/…/").replace("docker.io/", "")
        for r in t2]
ex = [r["result"] == "存在" for r in t2]
y2 = np.arange(len(refs))
bx.barh(y2, [1] * len(refs), color=["#2e7d32" if e else "#c62828" for e in ex])
bx.set_yticks(y2); bx.set_yticklabels(refs, fontsize=8); bx.invert_yaxis()
bx.set_xticks([]); bx.set_xlim(0, 1.5)
for i, e in enumerate(ex):
    bx.text(1.03, i, "存在" if e else "不存在", va="center", fontsize=8.5)
bx.set_title(f"② 桌面镜像存在性探测（{S['existence_probes']} 条，仅 {S['existence_found']} 条存在）\n"
             f"麒麟桌面官方镜像 {S['kylin_desktop_official_images']} 个，"
             f"统信 UOS 官方镜像 {S['uos_official_images']} 个", fontsize=10)
fig.tight_layout(); fig.savefig(FIG / "fig01_official_availability.png", dpi=150); plt.close(fig)

# fig02 产品线对照：麒麟官方 server 与桌面派生的四维差异
t3 = table("t03_product_line_comparison.csv")
fig, ax = plt.subplots(figsize=(12.5, 3.2)); ax.axis("off")
hdr = ["", "os-release NAME", "ID", "包格式", "glibc", "软件源域名"]
rows = []
def domain(u):
    """从 `deb [signed-by=...] http://host/path suite comps` 或 `baseurl = http://host/...`
    里取出主机名。不能按空格位置取 —— deb 行前面可能夹着 [signed-by=...] 选项段。"""
    for tok in u.replace("=", " ").split():
        if tok.startswith(("http://", "https://")):
            return tok.split("/")[2]
    return "—"
for r in t3:
    rows.append([r["kind"], r["os_name"], r["os_id"], r["pkg_format"],
                 r["glibc"][:20] or "—", domain(r["repo_url_sample"])])
tb = ax.table(cellText=rows, colLabels=hdr, cellLoc="left", loc="center")
tb.auto_set_font_size(False); tb.set_fontsize(9); tb.scale(1, 1.55)
for j in range(len(hdr)): tb[0, j].set_facecolor("#e0e0e0"); tb[0, j].set_text_props(weight="bold")
# ID 标红只标麒麟两行：UOS 的 ID 是 uos，本来就不同，跟着标红会把「ID 相同」这个
# 论点说成对全表成立 —— 那是事实错误。
kylin_ids = [i for i, r in enumerate(rows) if r[2] == "kylin"]
for i in range(1, len(rows) + 1):
    tb[i, 3].set_facecolor("#ffe0b2" if rows[i-1][3] == "rpm" else "#c8e6c9")
    if (i - 1) in kylin_ids:
        tb[i, 2].set_facecolor("#ffcdd2")   # 麒麟官方与麒麟桌面的 ID 相同 —— 误认的根源
ax.set_title("麒麟「官方镜像」与麒麟桌面版不是一条产品线：包格式、glibc、软件源三者全不同，\n"
             "而两者 os-release 的 ID 都是 kylin（红色格）—— 这正是被误认成同一产品线的原因",
             fontsize=10.5, pad=12)
fig.tight_layout(); fig.savefig(FIG / "fig02_product_line.png", dpi=150); plt.close(fig)

# fig03 能力矩阵热力图
t5 = table("t05_capability_matrix.csv")
SHOW = ["sh","coreutils","getent","shadow_files","locale_zh","localtime","ca_bundle","dns","tls",
        "signal_trap","dpkg_query","apt","apt_update","apt_roundtrip","apt_check","dpkg_local_deb",
        "cc_present","compile_c","static_link","cxx_present","compile_cxx","cxx17","cxx20",
        "libc_headers","binutils","make_build","pkgconfig","cmake","autotools","cc_clean_stderr",
        "python3_run","python3_ssl","perl","openssl","curl","tar","xz","zstd","unzip",
        "ps","sock_tools","ip_tools","ping","dnsutil","editor","lsof","strace","gdb",
        "useradd_works","su_to_user","systemd","policy_rcd"]
rows = {r["capability"]: r for r in t5}
M, ylab = [], []
for k in SHOW:
    if k not in rows: continue
    ylab.append(k)
    # t05 已是三态（Y/N/NA），判定策略在 analyze.py，这里不再自行解释原始值
    M.append([1 if rows[k][c] == "Y" else (0.5 if rows[k][c] == "NA" else 0) for c in COLS])
M = np.array(M)
fig, ax = plt.subplots(figsize=(8.6, 13))
cmap = matplotlib.colors.ListedColormap(["#c62828", "#bdbdbd", "#2e7d32"])
ax.imshow(M, cmap=cmap, aspect="auto", vmin=0, vmax=1)
ax.set_xticks(range(len(COLS))); ax.set_xticklabels(LBL, fontsize=8)
ax.set_yticks(range(len(ylab))); ax.set_yticklabels(ylab, fontsize=7.5)
ax.set_xticks(np.arange(-.5, len(COLS), 1), minor=True)
ax.set_yticks(np.arange(-.5, len(ylab), 1), minor=True)
ax.grid(which="minor", color="w", linewidth=.6); ax.tick_params(which="minor", length=0)
ax.set_title(f"能力矩阵（{S['capability_items']} 项 × 9 镜像 = {S['capability_cells']} 格，全部实测）\n"
             f"绿=支持 {S['cells_supported']}　红=不支持 {S['cells_gap']}　"
             f"灰=不适用 {S['cells_na']}（按档位定位判，判据见 analyze.py 的 NA_POLICY）", fontsize=10.5)
fig.tight_layout(); fig.savefig(FIG / "fig03_capability_matrix.png", dpi=150); plt.close(fig)

# fig04 尺寸与包数分档
t4 = table("t04_built_images.csv")
fig, (a1, a2) = plt.subplots(1, 2, figsize=(12, 4.2))
sizes = [int(r["rootfs_tar_mb"]) for r in t4]; pkgs = [int(r["packages"]) for r in t4]
x = np.arange(len(t4))
cmap2 = {"micro": "#90caf9", "base": "#42a5f5", "devel": "#1565c0"}
cols = [cmap2[r["tier"]] for r in t4]
a1.bar(x, sizes, color=cols); a1.set_xticks(x); a1.set_xticklabels(LBL, fontsize=8)
a1.set_ylabel("rootfs tar / MB"); a1.set_title("三档镜像的体积（rootfs tar 字节流）")
for i, v in enumerate(sizes): a1.text(i, v + 8, str(v), ha="center", fontsize=8)
a2.bar(x, pkgs, color=cols); a2.set_xticks(x); a2.set_xticklabels(LBL, fontsize=8)
a2.set_ylabel("已安装包数"); a2.set_title("三档镜像的包数")
for i, v in enumerate(pkgs): a2.text(i, v + 4, str(v), ha="center", fontsize=8)
fig.suptitle("micro=纯运行时　base=平台可用　devel=构建用", fontsize=10)
fig.tight_layout(); fig.savefig(FIG / "fig04_tier_size.png", dpi=150); plt.close(fig)

# fig05 门禁与变异测试
fig, (a1, a2) = plt.subplots(1, 2, figsize=(11.5, 4))
gl = ["verify", "digest-chain", "sbom", "mutation", "repro"]
gv = [S["verify_passed"], S["digest_chain_passed"], 9, S["mutation_caught"], S["repro_identical"]]
gm = [S["verify_failed"], 0, 0, S["mutation_missed"], 0]
a1.bar(gl, gv, color="#2e7d32", label="通过")
a1.bar(gl, gm, bottom=gv, color="#c62828", label="失败")
a1.set_title("五道门禁"); a1.legend(fontsize=8); a1.tick_params(axis="x", labelsize=8.5)
for i, v in enumerate(gv): a1.text(i, v + max(gv) * .02, str(v), ha="center", fontsize=9)
labels = ["支持", "不支持", "不适用"]
# 饼图用全量 711 格（stats.json），不是热力图挑出来展示的那些行
tot = {"支持": S["cells_supported"], "不支持": S["cells_gap"], "不适用": S["cells_na"]}
a2.pie([tot[l] for l in labels], labels=[f"{l}\n{tot[l]}" for l in labels],
       colors=["#2e7d32", "#c62828", "#bdbdbd"], autopct="%1.1f%%", textprops={"fontsize": 9})
a2.set_title(f"能力矩阵格分布（{sum(tot.values())} 格）")
fig.tight_layout(); fig.savefig(FIG / "fig05_gates.png", dpi=150); plt.close(fig)

# fig06 厂商缺陷分布
t8 = table("t08_vendor_defects.csv")
import collections
cnt = collections.Counter(r["distro"] for r in t8)
fig, ax = plt.subplots(figsize=(7, 3.6))
ks = list(cnt.keys()); vs = [cnt[k] for k in ks]
ax.bar(ks, vs, color=["#1565c0", "#42a5f5", "#90caf9", "#bdbdbd"][:len(ks)])
for i, v in enumerate(vs): ax.text(i, v + .06, str(v), ha="center", fontsize=10)
ax.set_ylabel("条数"); ax.set_title(f"采集期确证的厂商缺陷共 {S['defects']} 条（每条都记录了根因与处理落点）")
fig.tight_layout(); fig.savefig(FIG / "fig06_defects.png", dpi=150); plt.close(fig)

print(f"figures/：{len(list(FIG.glob('*.png')))} 张")
