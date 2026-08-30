#!/usr/bin/env python3
"""D7：通用漏洞扫描器对这三个发行版的覆盖情况。

为什么必须落盘：README 的十条主要结论里，只有「trivy 对这三家没有有效覆盖」这一条
原先全靠正文散文与 test/cve.sh 的注释背书，raw/ 里没有任何原始输出。它偏偏又是
唯一涉及安全判断的一条 —— 无凭据的安全结论比没有结论更危险。

采集的是**判定事实**而非漏洞明细：每个镜像的 os-release ID 与 trivy 判定的
Metadata.OS.Family / Name，以及 HIGH+CRITICAL 计数。两者不一致即「误判」，
trivy 判 none 即「未识别」。漏洞明细会随库更新而漂，判定事实不会。
"""
import json, os, pathlib, shlex, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "raw" / "d7_cve.json"
TRIVY = os.environ.get("TRIVY", "aquasec/trivy:0.70.0")
SOCK = os.environ.get("SOCK") or f"/run/user/{os.getuid()}/docker.sock"
IMAGES = [(d, f"{r}:{t}") for d, r in
          [("kylin11", "kylin-desktop-v11"), ("kylin10", "kylin-desktop-v10"),
           ("uos25", "uos-desktop-v25")] for t in ("micro", "base", "devel")]

def sh(c, timeout=420):
    return subprocess.run(c, shell=True, capture_output=True, text=True, timeout=timeout).stdout

def main():
    if subprocess.run(f"docker image inspect {TRIVY}", shell=True,
                      capture_output=True).returncode != 0:
        print(f"!! 本地无 {TRIVY} 镜像，无法采集 —— 不写盘", file=sys.stderr); sys.exit(1)
    data = {"collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "scanner": TRIVY, "images": []}
    for did, img in IMAGES:
        print(f"  扫描 {img}", file=sys.stderr)
        real = sh(f"docker run --rm --entrypoint sh {img} -c "
                  f"{shlex.quote('. /etc/os-release 2>/dev/null; echo ${ID:-?}')}").strip()
        j = sh(f"timeout 400 docker run --rm -e http_proxy= -e https_proxy= "
               f"-e DOCKER_HOST=unix:///ds.sock -v {SOCK}:/ds.sock {TRIVY} "
               f"image --quiet --scanners vuln --format json {img}")
        try:
            d = json.loads(j)
        except Exception:
            print(f"!! {img} 的 trivy 输出无法解析 —— 不写盘", file=sys.stderr); sys.exit(1)
        os_meta = (d.get("Metadata") or {}).get("OS", {}) or {}
        rs = d.get("Results") or []
        data["images"].append({
            "distro_id": did, "image": img, "real_os_id": real,
            "trivy_os_family": os_meta.get("Family") or "none",
            "trivy_os_name": os_meta.get("Name") or "",
            "results": len(rs),
            "vuln_entries": sum(len(r.get("Vulnerabilities") or []) for r in rs),
            "high_critical": sum(1 for r in rs for v in (r.get("Vulnerabilities") or [])
                                 if v.get("Severity") in ("HIGH", "CRITICAL")),
            # 判定：真实 ID 与 trivy 判定不一致 = 误判；trivy 判 none = 未识别
            "verdict": ("未识别" if (os_meta.get("Family") or "none") == "none"
                        else "有效覆盖" if os_meta.get("Family") == real else "误判"),
        })
    if len(data["images"]) != 9:
        print("!! 采集不足 9 个镜像 —— 不写盘", file=sys.stderr); sys.exit(1)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    from collections import Counter
    c = Counter(x["verdict"] for x in data["images"])
    print(f"写入 {OUT}：{dict(c)}")

if __name__ == "__main__":
    main()
