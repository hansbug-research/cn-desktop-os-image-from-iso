#!/usr/bin/env python3
"""D2：本项目从 ISO 构建出的九个镜像的事实，以及与麒麟官方 server 镜像的产品线对照。

采集与判断分离：这里只把事实抓下来，产品线是否「同一条」由 analyze.py 依据
包格式 / 软件源域名 / glibc / 代号四个字段判定，判据写在 report.md。
"""
import json, os, shlex, subprocess, sys, time, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
# 构建产物目录。默认是仓库自身的 out/（`make` 就写在那儿）；
# 若产物在别处，用 DOSBUILD_OUT 指过去。不要硬编码开发机路径 —— 换台机器就跑不了。
OUTDIR = pathlib.Path(os.environ.get("DOSBUILD_OUT") or (ROOT / "artifacts"))
OUT = ROOT / "raw" / "d2_our_images.json"

OURS = [(d, t, img) for d, img in
        [("kylin11", "kylin-desktop-v11"), ("kylin10", "kylin-desktop-v10"), ("uos25", "uos-desktop-v25")]
        for t in ("micro", "base", "devel")]
# 产品线对照组：厂商官方镜像（唯一匿名可拉的那个）
OFFICIAL = "cr.kylinos.cn/kylin/kylin-server-minimal:v10sp1"

def run(cmd, timeout=180):
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
    return p.stdout.strip()

def facts(img):
    """镜像的产品线指纹：os-release 原文、包格式与包数、glibc、软件源域名。"""
    # ⚠️ 必须用 shlex.quote（单引号）而不是 json.dumps（双引号）：
    # 双引号里的 ${Version} 会被**宿主 shell** 展开成空串，dpkg-query 拿到的
    # 格式串就没了变量 —— 采出来的 glibc 字段会静默变成空值（实际踩过）。
    sh = lambda c: run(f"docker run --rm --entrypoint sh {img} -c {shlex.quote(c)}", timeout=180)
    return {
        # 三个尺寸口径都记，别混用：
        #   content_bytes  docker inspect .Size —— containerd 存储里的**压缩**内容大小
        #   unpacked_human docker images SIZE  —— 解包后按块占用（含文件系统开销）
        #   tar_bytes（见下）rootfs tar 的字节流 —— 构建的直接产物，被 manifest 的 sha256 锚定
        # 正文一律以 tar_bytes 为准，因为只有它既可复现又有哈希锚点。
        "content_bytes": run(f"docker image inspect {img} --format '{{{{.Size}}}}'"),
        "unpacked_human": run(f"docker images {img} --format '{{{{.Size}}}}'"),
        "os_release": sh("cat /etc/os-release 2>/dev/null"),
        "pkg_format": sh("command -v rpm >/dev/null 2>&1 && echo rpm || "
                         "{ command -v dpkg >/dev/null 2>&1 && echo dpkg || echo none; }"),
        "pkg_count": sh("A=''; [ -f /usr/lib/dpkg/var/status ] && A='--admindir=/usr/lib/dpkg/var'; "
                        "rpm -qa 2>/dev/null | wc -l; dpkg-query $A -W 2>/dev/null | wc -l"),
        "glibc_banner": sh("ldd --version 2>&1 | head -1"),
        "glibc_pkg": sh("A=''; [ -f /usr/lib/dpkg/var/status ] && A='--admindir=/usr/lib/dpkg/var'; "
                        "dpkg-query $A -W -f='${Version}' libc6 2>/dev/null || "
                        "rpm -q --qf '%{VERSION}-%{RELEASE}' glibc 2>/dev/null"),
        "repo_urls": sh("grep -rhE '^baseurl|^deb ' /etc/yum.repos.d/ /etc/apt/sources.list "
                        "/etc/apt/sources.list.d/ 2>/dev/null | head -8"),
        "stopsignal": run(f"docker image inspect {img} --format '{{{{.Config.StopSignal}}}}'"),
        "labels": run(f"docker image inspect {img} --format '{{{{json .Config.Labels}}}}'"),
        # mask 掉的单元数随发行版而变（候选表按「镜像里存在该单元才 mask」筛选），
        # 所以必须实测而不是在正文写死一个数：麒麟 V10 镜像里有 udev 单元，多 mask 4 个。
        "masked_units": sh("find /etc/systemd/system -maxdepth 1 -lname /dev/null "
                           "-printf '%f\\n' 2>/dev/null | sort | tr '\\n' ' '"),
        "setuid_bins": sh("find / -xdev -perm -4000 -type f 2>/dev/null | sort | tr '\\n' ' '"),
        # 镜像里到底装了哪些 GPG keyring —— 信任面必须可审计。早先 adapt_container
        # 无条件把麒麟的 keyring 拷进每个 rootfs，连走切片路径的 UOS 也被塞了一把，
        # 而落盘证据里查不到这件事，门禁也只看仓库的 keys/ 不看镜像。
        "keyrings": sh("ls /usr/share/keyrings/*.gpg 2>/dev/null | xargs -r -n1 basename "
                       "| sort | tr '\\n' ' '"),
        # 属主决定性质：dpkg -S 查得到的是**厂商包自带**的（属发行版内容，动它就越过了
        # 「等价环境」的底线），查不到的才是我们注入的。麒麟 V10 的 micro 档带的那把
        # 就属 kylin-keyring 包，不能一刀切删掉。
        "keyrings_unowned": sh("for f in /usr/share/keyrings/*.gpg; do [ -e \"$f\" ] || continue; "
                               "dpkg -S \"$f\" >/dev/null 2>&1 || basename \"$f\"; done "
                               "| sort | tr '\\n' ' '"),
    }

def main():
    data = {"collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "ours": [], "official_reference": None}
    for did, tier, repo in OURS:
        img = f"{repo}:{tier}"
        print(f"  采集 {img}", file=sys.stderr)
        rec = {"distro_id": did, "tier": tier, "image": img}
        rec.update(facts(img))
        # tar 的字节数与 sha256 是 t04 体积列与摘要链的来源。仓库不含 tar（体积原因），
        # 所以优先从 artifacts/ 的 manifest 里读已记录的 sha256；两处都没有就报错，
        # 不静默跳过 —— 静默跳过会让 t04 的体积列变空而没人发现。
        tar = OUTDIR / f"{did}-{tier}.tar"
        man = OUTDIR / f"{did}-{tier}.manifest"
        if tar.exists():
            rec["tar_bytes"] = tar.stat().st_size
            rec["tar_sha256"] = run(f"sha256sum {tar}").split()[0]
            rec["tar_source"] = "本地 tar 实测"
        elif man.exists():
            import re as _re
            t = man.read_text(errors="replace")
            rec["tar_sha256"] = (_re.search(r"# tarball sha256: ([0-9a-f]{64})", t) or [None, ""])[1]
            rec["tar_bytes"] = int((_re.search(r"# tarball bytes: (\d+)", t) or [None, 0])[1] or 0)
            rec["tar_source"] = "manifest 记录"
        else:
            print(f"!! 既无 {tar.name} 也无 {man.name}，无法取得产物锚点", file=sys.stderr)
            sys.exit(1)
        data["ours"].append(rec)
    print(f"  采集官方对照 {OFFICIAL}", file=sys.stderr)
    off = {"image": OFFICIAL,
           "digest": run(f"docker image inspect {OFFICIAL} --format '{{{{index .RepoDigests 0}}}}'")}
    off.update(facts(OFFICIAL))
    data["official_reference"] = off
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"写入 {OUT}（{len(data['ours'])} 个自建镜像 + 1 个官方对照）")

if __name__ == "__main__":
    main()
