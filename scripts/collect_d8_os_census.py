#!/usr/bin/env python3
"""D8：国产桌面 OS 全名录 + 官方容器镜像实测。

这份数据刻意分成两半，因为它们的证据强度完全不同：

  文献事实（`config/os_census.json`，人工维护）
      产品名、厂商、血统、版本、发布时间、桌面环境、是否活跃。
      这些拿不到一手测量，只能引官网/公告/镜像站目录页，**每条都必须带 source URL**。
      本脚本原样读入、不加工，只校验每条都有出处。

  我们的实测（本脚本产出）
      每个候选镜像引用能不能匿名拉到，判据是 `docker pull` 的**退出码**。
      不能用字符串匹配 —— 报错信息里同样含镜像引用，会把「不存在」判成「存在」
      （d1 的作者实际踩过这个假阳性）。

两半在 report 里也分开呈现：文献那半标注「据厂商/社区公开信息」，
实测那半标注「本项目实测」。把二者混成一张无区分的表，读者就无法判断哪句可复核。
"""
import json, subprocess, sys, time, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
CENSUS = ROOT / "config" / "os_census.json"
OUT = ROOT / "raw" / "d8_os_census.json"


def run(cmd, timeout=300):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return {"rc": p.returncode, "stdout": p.stdout.strip(), "stderr": p.stderr.strip()[:1500]}
    except subprocess.TimeoutExpired:
        return {"rc": -1, "stdout": "", "stderr": "timeout"}


def probe(ref, identify=False):
    """存在性探测。

    用 `docker manifest inspect` 而不是 `docker pull`：名录要探几十个引用，
    pull 会把层真下下来，代价与探测目的不成比例。manifest inspect 只问 registry
    「这个引用在不在」，rc=0 存在、rc!=0 不存在，实测两种情况都判得准。

    判据是**退出码**。不能匹配输出里是否含镜像引用 —— 报错信息里同样含引用，
    字符串匹配会把「不存在」判成「存在」（d1 的作者实际踩过）。

    identify=True 时才真 pull 并读 os-release：因为「拉得到」不等于「是那个产品」，
    这正是本项目最核心发现（麒麟官方镜像是另一条产品线）的由来。只对需要验身份的
    引用开这一档，避免为了一个存在性结论下载几百 MB。
    """
    m = run(f"docker manifest inspect {ref}", timeout=90)
    exists = m["rc"] == 0
    rec = {"ref": ref, "exists": exists, "probe_method": "docker manifest inspect",
           "rc": m["rc"],
           "stderr_tail": m["stderr"].splitlines()[-1][:400] if m["stderr"] else ""}
    if not (exists and identify):
        return rec
    pull = run(f"docker pull {ref}", timeout=900)
    rec["pull_rc"] = pull["rc"]
    if pull["rc"] != 0:
        rec["identify_note"] = "manifest 在但 pull 失败"
        return rec
    rec["os_release"] = run(
        f"docker run --rm --entrypoint sh {ref} -c 'cat /etc/os-release'")["stdout"]
    rec["pkg_format"] = run(
        f"docker run --rm --entrypoint sh {ref} -c "
        "'if command -v rpm >/dev/null 2>&1; then echo rpm; "
        "elif command -v dpkg >/dev/null 2>&1; then echo dpkg; else echo none; fi'")["stdout"]
    rec["glibc"] = run(
        f"docker run --rm --entrypoint sh {ref} -c 'ldd --version 2>&1 | head -1'")["stdout"]
    rec["size_bytes"] = run(
        f"docker image inspect {ref} --format '{{{{.Size}}}}'")["stdout"]
    return rec


def main():
    if not CENSUS.exists():
        sys.exit(f"缺 {CENSUS} —— 名录是人工维护的文献部分，不能由本脚本生成")
    census = json.loads(CENSUS.read_text())

    # 名录自身的完整性校验：每个条目、每条关键字段都必须有出处，否则不许进报告。
    bad = []
    for e in census["entries"]:
        if not e.get("sources"):
            bad.append(f'{e["name"]}: 无 sources')
        for k in ("vendor", "lineage", "latest_version", "desktop", "maintained"):
            if k not in e:
                bad.append(f'{e["name"]}: 缺字段 {k}')
    if bad:
        sys.exit("名录不合格：\n  " + "\n  ".join(bad))

    data = {"collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "vantage_note": census.get("vantage_note", ""),
            "census_revision": census.get("revision", ""),
            "entries": census["entries"],
            "probes": []}

    seen = set()
    for e in census["entries"]:
        for ref in e.get("image_candidates", []):
            if ref in seen:
                continue
            seen.add(ref)
            print(f"  探测 {ref}", file=sys.stderr)
            r = probe(ref, identify=ref in e.get("identify", []))
            r["for_os"] = e["name"]
            data["probes"].append(r)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"写入 {OUT}（名录 {len(data['entries'])} 个 OS，实测 {len(data['probes'])} 个镜像引用）")


if __name__ == "__main__":
    main()
