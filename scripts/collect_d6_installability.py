#!/usr/bin/env python3
"""D6：工具可装性、UOS apt 源规模、UOS ISO 包清单。

这三组数字原先只写在正文和配置注释里，raw/ 里没有一手记录 —— 审稿人无法复核。
它们支撑的是报告里两条强论断：
  「麒麟的『没预装』与 UOS 的『硬缺口』性质完全不同」（可装性 14/14 vs 0/14）
  「UOS V25 不能作为 C++ 构建环境」（ISO 里没有 g++，且源里装不上）
所以必须落盘。

被测工具清单显式写在这里，不许只在正文写个总数 —— 「14 个常见工具」不说是哪 14 个，
等于没有清单。
"""
import json, os, pathlib, shlex, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "raw" / "d6_installability.json"

# 14 个常见工具。选取标准：运维排查（前 6）、构建（中 6）、语言开发（后 2），
# 都是 devel/base 档使用者会实际去装的东西。
TOOLS = ["iproute2", "iputils-ping", "bind9-dnsutils", "lsof", "vim-tiny", "zstd",
         "unzip", "cmake", "autoconf", "automake", "git", "strace", "gdb", "python3-dev"]
# UOS 的包名有出入，同义名一并试
ALIASES = {"bind9-dnsutils": ["bind9-dnsutils", "dnsutils"], "vim-tiny": ["vim-tiny", "vim"]}
IMAGES = [("kylin11", "kylin-desktop-v11:base"), ("kylin10", "kylin-desktop-v10:base"),
          ("uos25", "uos-desktop-v25:base")]
# C++ 构建环境的判据包
CXX_TOOLS = ["g++", "gcc", "make", "cmake"]

def dsh(img, cmd, timeout=300):
    p = subprocess.run(
        f"docker run --rm -e http_proxy= -e https_proxy= --entrypoint sh {img} -c {shlex.quote(cmd)}",
        shell=True, capture_output=True, text=True, timeout=timeout)
    return p.stdout.strip()

def main():
    data = {"collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tools": TOOLS, "images": {}, "cxx_probe": {}, "uos_apt_scale": None,
            "uos_iso_inventory": None}
    for did, img in IMAGES:
        print(f"  可装性 {img}", file=sys.stderr)
        rec = {"image": img, "candidates": {}}
        # ⚠️ 判据用 `apt-cache madison`，不能用 `apt-cache policy` 的 Candidate：
        # policy 对**已安装但源里没有**的包同样会报 Candidate（值是已装版本），
        # 于是「已经装了」会被误计成「装得上」。UOS 上这个差别很关键 —— 我们主动切进去的
        # iproute2/lsof/zstd/unzip 就会把 0/14 虚报成 4/14。madison 只列源提供的版本。
        names = " ".join(" ".join(ALIASES.get(t, [t])) for t in TOOLS)
        script = (
            "apt-get update -qq >/dev/null 2>&1\n"
            f"for n in {names}; do\n"
            "  m=$(apt-cache madison \"$n\" 2>/dev/null | head -1 | tr -s ' ')\n"
            "  i=$(dpkg-query -W -f='${Status}' \"$n\" 2>/dev/null | grep -c 'install ok installed')\n"
            # 分隔符不能用 |：madison 的输出本身就是 `pkg | version | origin` 形式，
            # 用 | 分段会让每行都解析失败（三家全报 0/14，而实测麒麟是 14/14）。
            "  echo \"$n@@${m:-NOREPO}@@installed=$i\"\n"
            "done\n")
        out = dsh(img, script)
        raw = {}
        for line in out.splitlines():
            parts = line.split("@@")
            if len(parts) == 3:
                raw[parts[0].strip()] = {"madison": parts[1].strip(),
                                         "installed": parts[2].strip().endswith("1")}
        rec["raw"] = raw
        for t in TOOLS:
            hit = "NOREPO"
            for n in ALIASES.get(t, [t]):
                v = raw.get(n, {})
                if v.get("madison") and v["madison"] != "NOREPO":
                    hit = f"{n}: {v['madison']}"; break
            rec["candidates"][t] = hit
        rec["installable"] = sum(1 for v in rec["candidates"].values() if v != "NOREPO")
        rec["total"] = len(TOOLS)
        rec["preinstalled"] = sorted(n for n, v in raw.items() if v.get("installed"))
        data["images"][did] = rec
        # C++ 构建判据：present 用 command -v，可装性同样用 madison
        cxx_script = ("apt-get update -qq >/dev/null 2>&1\n"
                      f"for t in {' '.join(CXX_TOOLS)}; do\n"
                      "  p=$(command -v \"$t\" >/dev/null 2>&1 && echo Y || echo N)\n"
                      "  m=$(apt-cache madison \"$t\" 2>/dev/null | head -1 | tr -s ' ')\n"
                      "  echo \"$t present=$p repo=${m:-NOREPO}\"\n"
                      "done\n")
        data["cxx_probe"][did] = dsh(img, cxx_script)

    print("  UOS apt 源规模", file=sys.stderr)
    data["uos_apt_scale"] = dsh("uos-desktop-v25:base",
        "apt-get update -qq >/dev/null 2>&1; apt-cache stats 2>/dev/null | head -6; "
        "echo '---pkgnames---'; apt-cache pkgnames 2>/dev/null | sort -u | wc -l; "
        "echo '---nano---'; apt-cache policy nano 2>/dev/null | head -3")

    # UOS ISO 内的包清单：从切片源的 dpkg info 目录数 .list 文件
    src = os.environ.get("UOS_SLICE_SRC", "/w/build/uos25r")
    print(f"  UOS ISO 包清单（切片源 {src}）", file=sys.stderr)
    inv = subprocess.run(
        f"docker exec dosb sh -c {shlex.quote(f'ls {src}/var/lib/dpkg/info/*.list {src}/usr/lib/dpkg/var/info/*.list 2>/dev/null | xargs -r -n1 basename | sed s/[.]list$// | sort -u')}",
        shell=True, capture_output=True, text=True, timeout=180).stdout.split()
    if inv:
        data["uos_iso_inventory"] = {
            "package_count": len(inv),
            "source": src,
            "has": {t: (t in inv) for t in
                    ["g++", "cmake", "git", "strace", "gdb", "autoconf", "iputils-ping",
                     "vim-tiny", "iproute2", "lsof", "zstd", "unzip", "perl", "gcc", "make"]},
            "packages": inv,
        }
    else:
        print("!! 取不到 UOS 切片源的包清单（需要 builder 容器 dosb 在跑）", file=sys.stderr)

    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    s = " ".join(f"{d}={data['images'][d]['installable']}/{len(TOOLS)}" for d, _ in IMAGES)
    n = data["uos_iso_inventory"]["package_count"] if data["uos_iso_inventory"] else "?"
    print(f"写入 {OUT}：可装性 {s}，UOS ISO {n} 个包")

if __name__ == "__main__":
    main()
