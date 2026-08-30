#!/bin/bash
# 变异测试：故意破坏镜像，确认检查集**真的会失败**。
# 目的是防止"检查永远为真"的假通过——本项目就真踩过一次：
# /var/lib/dpkg/status 是断链时 `dpkg --audit` 输出 0 行，被当成健康。
set -u
ROOT=${ROOT:-/data/dosbuild}
# 基准换成 base：micro 无 apt 无 systemd，很多检查在它上面不适用
BASE=${BASE:-kylin-desktop-v11:base}
CHK="$ROOT/test/inner-checks.sh"
FAIL=0

TOTAL=0
run_mut() { # $1=名字 $2=破坏命令 $3..=期望变化的 key=值
  local name=$1 cmd=$2; shift 2
  TOTAL=$((TOTAL+1))
  local c="mut-$$" img="mutant:$$"
  docker rm -f "$c" >/dev/null 2>&1
  docker run -d --name "$c" --privileged "$BASE" sleep infinity >/dev/null
  docker exec "$c" sh -c "$cmd" >/dev/null 2>&1
  docker export "$c" | docker import -c 'CMD ["/bin/bash"]' - "$img" >/dev/null 2>&1
  docker rm -f "$c" >/dev/null 2>&1
  local out; out=$(docker run --rm -v "$CHK:/c.sh:ro" "$img" /bin/bash /c.sh 2>/dev/null)
  docker rmi "$img" >/dev/null 2>&1
  local ok=1 kv k v got
  for kv in "$@"; do
    # 支持 key=值（相等）、key<N / key>N（阈值）、key~子串（包含）。用阈值是为了让变异断言
    # 直接对应 verify 里的门禁阈值，而不是写死某个易变的具体数字。
    case $kv in
      *'~'*) k=${kv%%~*}; v=${kv#*~}; op='~' ;;
      *'<'*) k=${kv%%<*}; v=${kv#*<}; op='<' ;;
      *'>'*) k=${kv%%>*}; v=${kv#*>}; op='>' ;;
      *)     k=${kv%%=*}; v=${kv#*=};  op='=' ;;
    esac
    got=$(printf '%s' "$out" | awk -F= -v key="$k" '$1==key{print $2; exit}')
    case $op in
      '=') [ "$got" = "$v" ] || { ok=0; echo "    ✗ $k 期望变成 $v，实际 ${got:-空}"; } ;;
      '<') [ "${got:-0}" -lt "$v" ] 2>/dev/null || { ok=0; echo "    ✗ $k 期望 <$v，实际 ${got:-空}"; } ;;
      '>') [ "${got:-0}" -gt "$v" ] 2>/dev/null || { ok=0; echo "    ✗ $k 期望 >$v，实际 ${got:-空}"; } ;;
      '~') case $got in *"$v"*) ;; *) ok=0; echo "    ✗ $k 期望包含 $v，实际 ${got:-空}";; esac ;;
    esac
  done
  if [ "$ok" = 1 ]; then echo "  ✅ $name — 检查如期报警"; else echo "  ❌ $name — 检查没抓到"; FAIL=$((FAIL+1)); fi
}

echo "变异测试基准镜像: $BASE"
run_mut "删 nsswitch.conf"      'rm -f /etc/nsswitch.conf'                                    nsswitch=N
run_mut "植入 ssh host key"     'mkdir -p /etc/ssh && touch /etc/ssh/ssh_host_rsa_key'        no_sshkey=N
run_mut "删 CA 证书"            'rm -f /etc/ssl/certs/ca-certificates.crt'                    ca_bytes=0
run_mut "删 zh_CN locale"       'rm -f /usr/lib/locale/locale-archive; localedef --delete-from-archive zh_CN.UTF-8 2>/dev/null; true' locale_zh=0
run_mut "status 断链(历史假通过)" 'rm -f /var/lib/dpkg/status; ln -s /nonexistent /var/lib/dpkg/status' 'pkgs<40' 'audit_after>0' checks_complete=Y
# /etc/mtab 不做变异测试：容器运行时（runc）会自动建 /etc/mtab -> /proc/mounts，
# 镜像里删掉也观测不到。它的检查放在 verify.sh 的 tar_mtab（对 tarball 查），不在运行时。
echo "  ⊘ mtab — 跳过（运行时会自动补，运行时不可观测；已改为 tarball 层检查）"
run_mut "删 copyright(全部)"     'find /usr/share/doc -name copyright -delete'                 copyright_kept=N
# 只删一个包的 copyright：旧的 copyright_kept 检查在这种情况下永远为 Y，抓不到
run_mut "只删 bash 的 copyright" 'rm -f /usr/share/doc/bash/copyright'                         'copyright_missing~bash,' 
run_mut "删 policy-rc.d"        'rm -f /usr/sbin/policy-rc.d'                                 policy_rcd=N
# 以下三条补的是 L1/L2/L3 层。之前 7 个用例全打在 L0"文件在不在"上，
# 结果 elf_broken 恒为 0、tz 恒为 UTC 这两个 bug 一直活着——正是因为没有对应变异。
# 把 systemd 私有目录里的 .so 拷到普通库目录：它依赖的 libsystemd-shared 只在私有目录里，
# 换了位置就真的找不到了 —— 这正是 elf_broken 该抓的情形（而不是误报那种）。
run_mut "植入依赖缺失的 .so" \
  'cp /usr/lib/x86_64-linux-gnu/systemd/libsystemd-core-*.so /usr/lib/x86_64-linux-gnu/_broken.so 2>/dev/null || \
   cp /lib/x86_64-linux-gnu/systemd/libsystemd-core-*.so /usr/lib/x86_64-linux-gnu/_broken.so 2>/dev/null; true' \
  elf_broken=1
run_mut "改 /etc/localtime 到上海" \
  'ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime'                    tz=CST
run_mut "machine-id 写入内容"    'echo deadbeef > /etc/machine-id'             machine_id_empty=N
run_mut "植入清单外悬空软链"     'ln -sfn /nonexistent/x /etc/_dangling'      'dangling_etc_list~_dangling,'
echo
[ "$FAIL" -eq 0 ] && echo "✅ $TOTAL 项变异全部被检查抓到（检查集有效）" \
                 || echo "❌ $TOTAL 项变异里有 $FAIL 项未被抓到"
exit $([ "$FAIL" -eq 0 ] && echo 0 || echo 1)
