#!/usr/bin/env python3
"""把 artifacts/caps-*.txt 渲染成能力矩阵。

三态语义（用户要求）：
  ✅ 支持    —— 实测通过
  ❌ 不支持  —— 实测不通过，且这一需求在该档位**确实存在**（是缺口）
  ➖ 不适用  —— 该档位定位下这一需求不存在（不是缺口）

「不适用」只在有明确定位依据时才用，不拿它掩盖缺口：
  micro = 纯运行时（无包管理/无工具链，应用在别处构建好再拷进来）
  base  = 平台可用（有包管理，能装东西、能跑运维排查，但不预置工具链）
  devel = 构建用（工具链齐备）
"""
import glob, os, pathlib, re, sys, collections

ROOT = os.environ.get("ROOT") or str(pathlib.Path(__file__).resolve().parent.parent)
sys.path.insert(0, f"{ROOT}/scripts")
from _subjects import DIDS, TIERS, SHORT      # 被试清单的唯一真源：config/subjects.json
DISTROS = [(d, SHORT[d]) for d in DIDS]

data = {}
for d, _ in DISTROS:
    for t in TIERS:
        p = f"{ROOT}/artifacts/caps-{d}-{t}.txt"
        if not os.path.exists(p):
            # 静默 continue 会让缺一家被试只表现为「矩阵少一列」，汇总照样全绿。
            sys.exit(f"缺探针输出 {p}；先跑 test/run-capabilities.sh")
        kv = {}
        for line in open(p):
            if line.startswith("cap."):
                k, _, v = line[4:].rstrip("\n").partition("=")
                kv[k] = v
        data[(d, t)] = kv

# 每项：(显示名, key, 在哪些档位算「不适用」)
NA = {}  # key -> set of tiers where the need doesn't exist
def na(*tiers): return set(tiers)

SECTIONS = [
 ("基础运行时（所有档位都必须有）", [
    ("POSIX shell",                ["sh"],               set()),
    ("bash",                       ["bash"],             set()),
    ("coreutils / findutils / grep-sed-awk", ["coreutils","findutils","textutils"], set()),
    ("用户数据库查询 getent",      ["getent"],           set()),
    ("影子文件 shadow/gshadow",    ["shadow_files"],     set()),
    ("zh_CN.UTF-8 locale",         ["locale_zh"],        set()),
    ("时区 /etc/localtime",        ["localtime"],        set()),
    ("CA 根证书",                  ["ca_bundle"],        set()),
    ("DNS 解析",                   ["dns"],              set()),
    ("HTTPS/TLS 真握手",           ["tls"],              set()),
    ("nsswitch.conf",              ["nsswitch"],         set()),
    ("/tmp、/var 可写",            ["tmp_writable","var_writable"], set()),
    ("信号 trap（优雅退出基础）",  ["signal_trap"],      set()),
 ]),
 ("包管理", [
    # 标签按**能力**命名而不是按工具：同一行在 deb 侧由 dpkg/apt 测，rpm 侧由
    # rpm/dnf 测（见 report §6.1）。写成「dpkg 数据库可查」会让 rpm 系被试
    # 在这一行必然不支持，而那量的是尺子不是被试。
    ("包数据库可查（SBOM 前提）",   ["pkgdb_query"],      set()),
    ("包管理器存在",               ["pkgmgr"],           na("micro")),
    ("软件源配置 + 密钥环",        ["pkg_sources","pkg_keyring"], na("micro")),
    ("软件源元数据可刷新",         ["pkg_update"],       na("micro")),
    ("装卸往返（含维护者脚本）",   ["pkg_roundtrip"],    na("micro")),
    ("已装包依赖自洽",             ["pkg_check"],        na("micro")),
    ("本地包直装（离线分发）",     ["pkg_local_install"], set()),
 ]),
 ("编译构建", [
    ("C 编译器存在",               ["cc_present"],       na("micro","base")),
    ("C 真编真跑",                 ["compile_c"],        na("micro","base")),
    ("C 静态链接",                 ["static_link"],      na("micro","base")),
    ("C++ 编译器存在",             ["cxx_present"],      na("micro","base")),
    ("C++ 真编真跑（含 thread/mutex）", ["compile_cxx"], na("micro","base")),
    ("-std=c++17",                 ["cxx17"],            na("micro","base")),
    ("-std=c++20",                 ["cxx20"],            na("micro","base")),
    ("libc 头文件",                ["libc_headers"],     na("micro","base")),
    ("binutils（ld/ar/strip/objdump）", ["binutils"],    na("micro","base")),
    ("make 驱动真实构建",          ["make","make_build"], na("micro","base")),
    ("pkg-config",                 ["pkgconfig"],        na("micro","base")),
    ("cmake",                      ["cmake"],            na("micro","base")),
    ("autoconf/automake",          ["autotools"],        na("micro","base")),
    ("编译器 stderr 干净",         ["cc_clean_stderr"],  na("micro","base")),
    ("Python 开发头文件",          ["python3_dev"],      na("micro","base")),
 ]),
 ("语言运行时与常用工具", [
    ("python3 可跑",               ["python3","python3_run"], na("micro")),
    ("python3 ssl 可用",           ["python3_ssl"],      na("micro")),
    ("perl",                       ["perl"],             na("micro")),
    ("openssl CLI",                ["openssl"],          set()),
    ("curl 或 wget",               ["curl","wget"],      set(), "any"),
    ("git",                        ["git"],              na("micro","base")),
    ("tar / gzip",                 ["tar","gzip"],       set()),
    ("xz",                         ["xz"],               set()),
    ("zstd",                       ["zstd"],             na("micro")),
    ("unzip",                      ["unzip"],            na("micro")),
 ]),
 ("运维排查", [
    ("ps",                         ["ps"],               na("micro")),
    ("top/htop",                   ["top"],              na("micro")),
    ("ss/netstat",                 ["sock_tools"],       na("micro")),
    ("ip/ifconfig",                ["ip_tools"],         na("micro")),
    ("ping",                       ["ping"],             na("micro")),
    ("dig/nslookup/host",          ["dnsutil"],          na("micro")),
    ("file",                       ["file"],             na("micro")),
    ("less/more",                  ["pager"],            na("micro")),
    ("vi/vim/nano",                ["editor"],           na("micro")),
    ("lsof",                       ["lsof"],             na("micro")),
    ("strace",                     ["strace"],           na("micro","base")),
    ("gdb",                        ["gdb"],              na("micro","base")),
 ]),
 ("容器与账户语义", [
    ("useradd 建非 root 用户",     ["useradd","useradd_works"], na("micro")),
    ("su 切到该用户",              ["su_to_user"],       na("micro")),
    ("sudo",                       ["sudo"],             na("micro","base","devel")),
    ("systemd 可作 PID 1",         ["systemd"],          na("micro")),
    ("policy-rc.d（阻止装包起服务）", ["policy_rcd"],    na("micro")),
 ]),
]

def cell(kv, keys, na_tiers, tier, mode="all"):
    """mode="all" 要求全部为 Y；mode="any" 只要有一个 Y 即可（「curl 或 wget」这类）。
    探针输出 n/a 表示该项在此镜像上不构成需求（如 micro 没有 apt），按不适用处理。"""
    if tier in na_tiers:
        return "➖"
    vals = [kv.get(k, "") for k in keys]
    if any(v == "" for v in vals):
        return "❓"
    if all(v == "n/a" for v in vals):
        return "➖"
    if mode == "any":
        return "✅" if any(v == "Y" for v in vals) else "❌"
    if all(v == "Y" for v in vals):
        return "✅"
    if any(v == "PARTIAL" for v in vals):
        return "⚠️"
    return "❌"

cols = [(d, t) for d, _ in DISTROS for t in TIERS]
hdr = "| 需求 | " + " | ".join(f"{dn}<br>{t}" for d, dn in DISTROS for t in TIERS) + " |"
sep = "|---|" + "---|" * len(cols)

out = []
gaps = []
for title, rows in SECTIONS:
    out.append(f"\n**{title}**\n")
    out.append(hdr); out.append(sep)
    for row in rows:
        name, keys, na_tiers = row[0], row[1], row[2]
        mode = row[3] if len(row) > 3 else "all"
        cs = []
        for (d, t) in cols:
            kv = data.get((d, t))
            if kv is None:
                cs.append("·"); continue
            c = cell(kv, keys, na_tiers, t, mode)
            cs.append(c)
            if c in ("❌", "⚠️", "❓"):
                gaps.append((c, d, t, name, {k: kv.get(k, "缺") for k in keys}))
        out.append(f"| {name} | " + " | ".join(cs) + " |")
print("\n".join(out))
print("\n\n## 非 ✅ 项明细（共 %d 处）\n" % len(gaps))
for c, d, t, name, detail in gaps:
    print(f"- {c} `{d}:{t}` **{name}** — {detail}")
# 附：数值型观察
print("\n\n## 数值型观察\n")
print("| 镜像 | os-release | glibc | setuid 二进制数 | 带 file caps 的文件数 | default.target |")
print("|---|---|---|---|---|---|")
for (d, t) in cols:
    kv = data.get((d, t))
    if not kv: continue
    print(f"| {d}:{t} | {kv.get('os_id','?')} | {kv.get('glibc','?')} | {kv.get('setuid_bins','?')} | {kv.get('file_caps','?')} | {kv.get('default_target','') or '—'} |")
