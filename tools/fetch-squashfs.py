#!/usr/bin/env python3
"""从远端 ISO 里用 HTTP Range 只抽 squashfs（不下整盘），并按 conf 里的 sha256 校验。

用法: fetch-squashfs.py <distro-id> [ROOT]
参数全部来自 distros/<id>.conf：ISO_URL / ISO_SQUASHFS_PATH / SQUASHFS_SHA256
校验不通过直接非零退出——之前这个脚本只 print 期望值、从不比对，等于没校验。
"""
import os, re, sys, subprocess, hashlib, importlib.util

did = sys.argv[1]
ROOT = sys.argv[2] if len(sys.argv) > 2 else os.environ.get('ROOT', '/w')
conf = os.path.join(ROOT, 'distros', f'{did}.conf')
cfg = {}
for line in open(conf, encoding='utf-8'):
    m = re.match(r'^(\w+)=(.*)$', line.strip())
    if m:
        cfg[m.group(1)] = m.group(2).strip().strip('"').strip("'")

url  = cfg.get('ISO_URL') or sys.exit('conf 里缺 ISO_URL')
path = cfg.get('ISO_SQUASHFS_PATH') or sys.exit('conf 里缺 ISO_SQUASHFS_PATH')
want = cfg.get('SQUASHFS_SHA256', '')
out  = os.path.join(ROOT, 'iso', f'{did}-filesystem.squashfs')
os.makedirs(os.path.dirname(out), exist_ok=True)

spec = importlib.util.spec_from_file_location('i9', os.path.join(ROOT, 'tools', 'iso9660.py'))
m9 = importlib.util.module_from_spec(spec); spec.loader.exec_module(m9)

iso = m9.ISO(url)
e = iso.find(path) or sys.exit(f'ISO 里找不到 {path}')
off, size = e['lba'] * 2048, e['size']
print(f'{did}: offset={off} size={size} ({size/2**30:.2f} GiB) -> {out}', flush=True)

if not (os.path.exists(out) and os.path.getsize(out) == size):
    rc = subprocess.call(['curl', '-fsS', '--no-alpn', '-L', '--max-time', '7200',
                          '-r', f'{off}-{off+size-1}', '-o', out, url])
    if rc != 0:
        sys.exit(f'curl 抽取失败 rc={rc}')
else:
    print('  已存在且大小一致，跳过下载', flush=True)

h = hashlib.sha256()
with open(out, 'rb') as f:
    for blk in iter(lambda: f.read(1 << 22), b''):
        h.update(blk)
got = h.hexdigest()
if want:
    if got != want:
        sys.exit(f'!! sha256 不符\n   期望 {want}\n   实际 {got}')
    print(f'  sha256 校验通过 {got[:16]}…', flush=True)
else:
    print(f'  conf 里没有 SQUASHFS_SHA256，实测值为 {got}（请写回 conf 以便后续校验）', flush=True)
