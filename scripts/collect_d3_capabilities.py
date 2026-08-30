#!/usr/bin/env python3
"""D3：九个镜像的能力探针结果与验收门禁结果。

能力探针（test/capabilities.sh）在镜像内**真跑**每一项：编译要真编真跑、
TLS 要真握手、apt 要真装真卸。不看包列表推断 —— 装了 gcc 不等于能编出可跑的二进制。

本脚本可以两种方式取数：
  --run   现场重跑 test/run-capabilities.sh（需要九个镜像已在本地 docker 里）
  默认    从 --from 指定目录读已落盘的 caps-*.txt（用于在没有镜像的机器上重算）
"""
import argparse, json, os, pathlib, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "raw" / "d3_capabilities.json"
DISTROS = ["kylin11", "kylin10", "uos25"]
TIERS = ["micro", "base", "devel"]

def parse_caps(text):
    """探针输出是 cap.<名字>=<值> 行。缺失的 key 不补默认值——
    缺失本身是信息（探针中途挂掉），由 probe_complete 哨兵标识。"""
    kv = {}
    for line in text.splitlines():
        if line.startswith("cap."):
            k, _, v = line[4:].partition("=")
            kv[k] = v
    return kv

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="现场重跑探针")
    ap.add_argument("--from", dest="src",
                    default=os.environ.get("DOSBUILD_OUT") or str(ROOT / "out"),
                    help="已落盘 caps-*.txt 的目录（默认仓库自身的 out/，可用 DOSBUILD_OUT 覆盖）")
    a = ap.parse_args()
    if a.run:
        subprocess.run([str(ROOT / "test" / "run-capabilities.sh")], check=True,
                       env={"ROOT": str(ROOT), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"})
        a.src = str(ROOT / "out")
    src = pathlib.Path(a.src)
    data = {"collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source_dir": str(src), "probes": {}}
    missing = []
    for d in DISTROS:
        for t in TIERS:
            f = src / f"caps-{d}-{t}.txt"
            if not f.exists():
                missing.append(f.name); continue
            kv = parse_caps(f.read_text(errors="replace"))
            # 哨兵：探针必须跑到最后一行，否则前面所有「通过」都不可信
            kv["_probe_complete"] = kv.get("probe_complete", "N")
            data["probes"][f"{d}:{t}"] = kv
    if missing:
        print(f"!! 缺少探针输出：{missing}", file=sys.stderr); sys.exit(1)
    bad = [k for k, v in data["probes"].items() if v["_probe_complete"] != "Y"]
    if bad:
        print(f"!! 这些探针没跑完，数据不可用：{bad}", file=sys.stderr); sys.exit(1)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    n = len(data["probes"]); m = len(next(iter(data["probes"].values())))
    print(f"写入 {OUT}（{n} 个镜像 × 约 {m} 项）")

if __name__ == "__main__":
    main()
