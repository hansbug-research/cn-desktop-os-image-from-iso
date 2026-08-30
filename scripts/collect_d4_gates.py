#!/usr/bin/env python3
"""D4：五道验收门禁的结果，以及构建产物的审计锚点。

五道门禁各自防的是不同一类事故，缺一不可：
  verify        365 项逐镜像检查（结构/完整性/基线对账/能力/ABI-gate/元数据）
  digest-chain  manifest 记的 sha256 = out/*.tar 实际字节 = 本地镜像，三者对账
  sbom          每镜像可生成 SPDX 且包数 ≥ dpkg 自报数
  mutation      故意破坏镜像，确认检查集**真的会失败**（防「检查永远为真」的假通过）
  repro         连构两次比 sha256

失败必须留在数据里：任何一道门禁的失败都是结论的一部分，不许只记成功。
"""
import json, pathlib, re, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "raw" / "d4_gates.json"
SRC = ROOT.parent / "dosbuild"

def tail(p, n=400):
    f = pathlib.Path(p)
    return "\n".join(f.read_text(errors="replace").splitlines()[-n:]) if f.exists() else ""

def main():
    data = {"collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "gates": {}}

    v = tail(SRC / "logs" / "f4-verify.log")
    m = re.search(r"通过 (\d+) / 失败 (\d+) / 警告 (\d+)", v)
    data["gates"]["verify"] = {
        "passed": int(m.group(1)) if m else None,
        "failed": int(m.group(2)) if m else None,
        "warned": int(m.group(3)) if m else None,
        "baseline": int(re.search(r"基线 (\d+)", v).group(1)) if re.search(r"基线 (\d+)", v) else None,
        "failures": re.findall(r"^\s*✗ (.+)$", v, re.M),
        "log_tail": "\n".join(v.splitlines()[-6:]),
    }
    dg = tail(SRC / "logs" / "f4-digest.log")
    m = re.search(r"通过 (\d+) / 失败 (\d+)", dg)
    data["gates"]["digest_chain"] = {"passed": int(m.group(1)) if m else None,
                                     "failed": int(m.group(2)) if m else None,
                                     "log_tail": "\n".join(dg.splitlines()[-3:])}
    sb = tail(SRC / "logs" / "f4-sbom.log")
    data["gates"]["sbom"] = {
        "rows": [l.split() for l in sb.splitlines() if "✅" in l or "❌" in l],
        "all_ok": "全部镜像可生成 SBOM" in sb, "log_tail": "\n".join(sb.splitlines()[-3:])}
    mu = tail(SRC / "logs" / "f4-mutation.log")
    data["gates"]["mutation"] = {
        "caught": len(re.findall(r"✅ .+ — 检查如期报警", mu)),
        "missed": len(re.findall(r"❌ .+ — 检查没抓到", mu)),
        "skipped": len(re.findall(r"⊘ ", mu)),
        "cases": re.findall(r"[✅❌⊘] (.+?) —", mu),
        "log_tail": "\n".join(mu.splitlines()[-2:])}
    rp = (SRC / "out" / "repro-evidence.txt")
    if rp.exists():
        txt = rp.read_text(errors="replace")
        data["gates"]["repro"] = {
            "identical": len(re.findall(r"一致\s+sha256=", txt)),
            "mismatched": len(re.findall(r"不一致", txt)),
            "evidence": txt}
    # 审计锚点：每个 tarball 的 sha256 与 manifest 记录
    data["manifests"] = {}
    for f in sorted((SRC / "out").glob("*.manifest")):
        t = f.read_text(errors="replace")
        data["manifests"][f.stem] = {
            "tarball_sha256": (re.search(r"# tarball sha256: ([0-9a-f]{64})", t) or [None, None])[1],
            "source_date_epoch": (re.search(r"# SOURCE_DATE_EPOCH: (\d+)", t) or [None, None])[1],
            "inrelease_sha256": (re.search(r"# InRelease sha256: ([0-9a-f]{64})", t) or [None, None])[1],
            "package_lines": sum(1 for l in t.splitlines() if l and not l.startswith("#")),
        }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    g = data["gates"]
    print(f"写入 {OUT}：verify {g['verify']['passed']}/{g['verify']['failed']}、"
          f"digest {g['digest_chain']['passed']}、mutation {g['mutation']['caught']} 抓到 "
          f"{g['mutation']['missed']} 漏、repro {g.get('repro',{}).get('identical')} 一致、"
          f"{len(data['manifests'])} 份 manifest")

if __name__ == "__main__":
    main()
