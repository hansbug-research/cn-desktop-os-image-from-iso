#!/usr/bin/env python3
"""D1：国产桌面 OS 的官方容器镜像可获得性调查。

只采集事实，不做判断（判断留给 analyze.py）。每条记录都带证据来源：
registry 域名、Docker Hub API 返回、以及（能拉到时）镜像内 /etc/os-release 原文。

「官方」的判据（沿用本 org 既有约定）：只有能给出 registry 域名归属或厂商页面
链接证据的才算官方，其余一律记为第三方转发。本脚本只记录域名与探测结果，
official 字段由 config/vendors.json 人工标注并在 report.md 写明依据。
"""
import json, subprocess, sys, time, urllib.request, urllib.error, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "raw" / "d1_official_images.json"

HUB_NAMESPACES = ["openkylin", "deepin", "uniontech", "kylin", "linuxdeepin", "nfschina", "iSoftStone"]

# 直接探测的候选镜像：(厂商, 产品, registry 引用)
CANDIDATES = [
    ("麒麟软件", "银河麒麟高级服务器操作系统 V10 SP1", "cr.kylinos.cn/kylin/kylin-server-minimal:v10sp1"),
    ("麒麟软件", "银河麒麟高级服务器操作系统 V10", "cr.kylinos.cn/kylin/kylin-server:v10"),
    ("openKylin 社区", "openKylin 2.0", "docker.io/openkylin/openkylin:2.0"),
    ("openKylin 社区", "openKylin latest", "docker.io/openkylin/openkylin:latest"),
    ("deepin 社区", "deepin-core", "docker.io/deepin/deepin-core:latest"),
    ("deepin 社区", "deepin beige (23)", "docker.io/linuxdeepin/beige:latest"),
    ("deepin 社区", "deepin apricot (20)", "docker.io/linuxdeepin/apricot:latest"),
    ("统信软件", "UOS（探测是否存在官方镜像）", "docker.io/uniontech/uos:latest"),
]

def run(cmd, timeout=180):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return {"rc": p.returncode, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()[:2000]}
    except subprocess.TimeoutExpired:
        return {"rc": -1, "stdout": "", "stderr": "timeout"}

def hub_namespace(ns):
    url = f"https://hub.docker.com/v2/repositories/{ns}/?page_size=100"
    try:
        with urllib.request.urlopen(url, timeout=30) as r:
            d = json.loads(r.read().decode())
        return {"ok": True, "count": d.get("count", 0),
                "repos": sorted(x["name"] for x in d.get("results", []))}
    except Exception as e:
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}

def probe_image(ref):
    """拉取并读出镜像事实。拉不到也是结论的一部分，原样记录。"""
    rec = {"ref": ref}
    pull = run(f"docker pull {ref}", timeout=600)
    rec["pull"] = pull
    if pull["rc"] != 0:
        rec["available"] = False
        return rec
    rec["available"] = True
    rec["digest"] = run(
        f"docker image inspect {ref} --format '{{{{index .RepoDigests 0}}}}'")["stdout"]
    rec["size_bytes"] = run(f"docker image inspect {ref} --format '{{{{.Size}}}}'")["stdout"]
    # /etc/os-release 逐字保存，不做解析——解析放 analyze.py
    rec["os_release"] = run(
        f"docker run --rm --entrypoint sh {ref} -c 'cat /etc/os-release'")["stdout"]
    rec["pkg_format"] = run(
        f"docker run --rm --entrypoint sh {ref} -c "
        f"'if command -v rpm >/dev/null 2>&1; then echo rpm; "
        f"elif command -v dpkg >/dev/null 2>&1; then echo dpkg; else echo none; fi'")["stdout"]
    rec["pkg_count"] = run(
        f"docker run --rm --entrypoint sh {ref} -c "
        f"'rpm -qa 2>/dev/null | wc -l; dpkg-query -W 2>/dev/null | wc -l'")["stdout"]
    rec["glibc"] = run(
        f"docker run --rm --entrypoint sh {ref} -c 'ldd --version 2>&1 | head -1'")["stdout"]
    rec["repos"] = run(
        f"docker run --rm --entrypoint sh {ref} -c "
        f"'grep -rhE \"^baseurl|^deb \" /etc/yum.repos.d/ /etc/apt/sources.list "
        f"/etc/apt/sources.list.d/ 2>/dev/null | head -8'")["stdout"]
    return rec

# 存在性探测：判据必须是 docker pull 的**退出码**，不能匹配输出里是否含镜像引用 ——
# 报错信息 `failed to resolve reference "cr.kylinos.cn/..."` 里同样含有引用，
# 用字符串匹配会把「不存在」判成「存在」（本脚本作者实际踩过这个假阳性）。
EXISTENCE_PROBES = [
    "cr.kylinos.cn/kylin/kylin-server-minimal:v10sp1",
    "cr.kylinos.cn/kylin/kylin-server-minimal:v11",
    "cr.kylinos.cn/kylin/kylin-desktop:v10",
    "cr.kylinos.cn/kylin/kylin-desktop:v11",
    "cr.kylinos.cn/kylin/kylin-desktop:latest",
    "cr.kylinos.cn/kylin/kylin-linux-desktop:v10",
    "docker.io/uniontech/uos:latest",
    "docker.io/uniontech/uos-desktop:latest",
]

def probe_existence(ref):
    pull = run(f"docker pull {ref}", timeout=300)
    exists = pull["rc"] == 0 and run(f"docker image inspect {ref}")["rc"] == 0
    return {"ref": ref, "exists": exists, "rc": pull["rc"],
            "stderr_tail": pull["stderr"].splitlines()[-1][:300] if pull["stderr"] else ""}

def main():
    data = {"collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "vantage_note": "采集主机出口在中国大陆，境外站点经本地代理；探测失败需区分网络位置与策略拒绝",
            "hub_namespaces": {}, "images": []}
    for ns in HUB_NAMESPACES:
        print(f"  探测 Docker Hub 命名空间 {ns}", file=sys.stderr)
        data["hub_namespaces"][ns] = hub_namespace(ns)
    data["existence_probes"] = []
    for ref in EXISTENCE_PROBES:
        print(f"  存在性探测 {ref}", file=sys.stderr)
        data["existence_probes"].append(probe_existence(ref))
    for vendor, product, ref in CANDIDATES:
        print(f"  探测镜像 {ref}", file=sys.stderr)
        rec = probe_image(ref)
        rec["vendor"], rec["product"] = vendor, product
        data["images"].append(rec)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"写入 {OUT}（{len(data['images'])} 个镜像探测）")

if __name__ == "__main__":
    main()
