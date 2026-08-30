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
import json, os, pathlib, re, subprocess, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
# 构建产物目录。默认是仓库自身的 out/（`make` 就写在那儿）；
# 若产物在别处，用 DOSBUILD_OUT 指过去。不要硬编码开发机路径 —— 换台机器就跑不了。
OUTDIR = pathlib.Path(os.environ.get("DOSBUILD_OUT") or (ROOT / "out"))
OUT = ROOT / "raw" / "d4_gates.json"
# 门禁日志与 manifest 都在 artifacts/ 里（随仓库提交，这样别人能核对一手输出）。
# 产物在别处时用 DOSBUILD_OUT 指过去。
SRC = pathlib.Path(os.environ.get("DOSBUILD_OUT") or (ROOT / "artifacts"))

def tail(p, n=400):
    f = pathlib.Path(p)
    return "\n".join(f.read_text(errors="replace").splitlines()[-n:]) if f.exists() else ""

def main():
    data = {"collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "gates": {}}

    v = tail(SRC / "f4-verify.log")
    m = re.search(r"通过 (\d+) / 失败 (\d+) / 警告 (\d+)", v)
    data["gates"]["verify"] = {
        "passed": int(m.group(1)) if m else None,
        "failed": int(m.group(2)) if m else None,
        "warned": int(m.group(3)) if m else None,
        "baseline": int(re.search(r"基线 (\d+)", v).group(1)) if re.search(r"基线 (\d+)", v) else None,
        "failures": re.findall(r"^\s*✗ (.+)$", v, re.M),
        "log_tail": "\n".join(v.splitlines()[-6:]),
    }
    dg = tail(SRC / "f4-digest.log")
    m = re.search(r"通过 (\d+) / 失败 (\d+)", dg)
    # digest 日志里逐镜像记着 sha256 前缀，是一份独立见证 —— 此前只留 log_tail 末 3 行
    # 把前缀丢了，于是「全协同篡改」时它还在场外没人核。抽出来供 verify 对账。
    _pref = dict(re.findall(r"✅ (\S+)\s+manifest=tar=镜像\s+\(([0-9a-f]{12})", dg))
    data["gates"]["digest_prefixes"] = _pref
    data["gates"]["digest_chain"] = {"passed": int(m.group(1)) if m else None,
                                     "failed": int(m.group(2)) if m else None,
                                     "log_tail": "\n".join(dg.splitlines()[-3:])}
    sb = tail(SRC / "f4-sbom.log")
    data["gates"]["sbom"] = {
        "rows": [l.split() for l in sb.splitlines() if "✅" in l or "❌" in l],
        "all_ok": "全部镜像可生成 SBOM" in sb, "log_tail": "\n".join(sb.splitlines()[-3:])}
    mu = tail(SRC / "f4-mutation.log")
    data["gates"]["mutation"] = {
        "caught": len(re.findall(r"✅ .+ — 检查如期报警", mu)),
        "missed": len(re.findall(r"❌ .+ — 检查没抓到", mu)),
        "skipped": len(re.findall(r"⊘ ", mu)),
        "cases": re.findall(r"[✅❌⊘] (.+?) —", mu),
        "log_tail": "\n".join(mu.splitlines()[-2:])}
    rp = (SRC / "repro-evidence.txt")
    if rp.exists():
        txt = rp.read_text(errors="replace")
        data["gates"]["repro"] = {
            "identical": len(re.findall(r"一致\s+sha256=", txt)),
            "mismatched": len(re.findall(r"不一致", txt)),
            "evidence": txt}
    # 审计锚点：每个 tarball 的 sha256 与 manifest 记录
    data["manifests"] = {}
    for f in sorted(SRC.glob("*.manifest")):
        t = f.read_text(errors="replace")
        data["manifests"][f.stem] = {
            "tarball_sha256": (re.search(r"# tarball sha256: ([0-9a-f]{64})", t) or [None, None])[1],
            "source_date_epoch": (re.search(r"# SOURCE_DATE_EPOCH: (\d+)", t) or [None, None])[1],
            "inrelease_sha256": (re.search(r"# InRelease sha256: ([0-9a-f]{64})", t) or [None, None])[1],
            "image_id": (re.search(r"# image id: ([0-9a-f]{12})", t) or [None, None])[1],
            "package_lines": sum(1 for l in t.splitlines() if l and not l.startswith("#")),
        }
    # 失败即退出，绝不写盘。早先版本在源目录不存在时照样 exit 0 写出一份全是 null 的
    # raw/d4_gates.json，把 365/9/12/6 全变成空 —— 既违反「raw 只写不改」，
    # 又让下游一路带着 null 跑到 verify 才崩。
    g = data["gates"]
    missing = [k for k in ("verify", "digest_chain", "mutation") if g[k].get("passed") is None
               and g[k].get("caught") in (None, 0)]
    if g["verify"]["passed"] is None or not data["manifests"]:
        print(f"!! 从 {SRC} 解析不到门禁日志或 manifest —— 不写盘。"
              f"请确认 artifacts/ 完整，或用 DOSBUILD_OUT 指向产物目录。", file=sys.stderr)
        sys.exit(1)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"写入 {OUT}：verify {g['verify']['passed']}/{g['verify']['failed']}、"
          f"digest {g['digest_chain']['passed']}、mutation {g['mutation']['caught']} 抓到 "
          f"{g['mutation']['missed']} 漏、repro {g.get('repro',{}).get('identical')} 一致、"
          f"{len(data['manifests'])} 份 manifest")

if __name__ == "__main__":
    main()
