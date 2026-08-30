#!/bin/bash
# 全量验收：对每个镜像跑结构/完整性/能力/ABI-gate 检查，并与 distros/*.conf 的预期基线对账
set -u
ROOT=${ROOT:-/data/dosbuild}
GATE_BIN=$ROOT/gate/t_low          # manylinux2014 编的低地板产物（GLIBC_2.14/GLIBCXX_3.4.11）
GATE_HIGH=$ROOT/gate/t_high        # Debian13 编的高地板产物（GLIBC_2.34）
PASS=0; FAIL=0; WARN=0
declare -a PROBLEMS=()

check(){ # name expect actual [warn]
  local n=$1 e=$2 a=$3 lvl=${4:-fail}
  if [ "$a" = "$e" ]; then PASS=$((PASS+1)); return 0; fi
  if [ "$lvl" = warn ]; then WARN=$((WARN+1)); PROBLEMS+=("  ⚠ $IMG $n: 期望 $e 实际 $a"); else
    FAIL=$((FAIL+1)); PROBLEMS+=("  ✗ $IMG $n: 期望 $e 实际 $a"); fi
  return 1
}

# pass/fail：给那些**不是"期望值==实际值"形态**的判断用（阈值、子集、白名单）。
# ⚠️ 这两个函数一开始我忘了定义就直接用，结果 `fail: 未找到命令` ——
# 成功分支和失败分支都是命令未找到，既不计通过也不计失败，四个检查全程空转。
# 这就是本项目反复出现的那类"假通过"，所以变异测试是必需的而不是锦上添花。
pass(){ PASS=$((PASS+1)); }
fail(){ FAIL=$((FAIL+1)); PROBLEMS+=("  ✗ $IMG $*"); }

# 发行版清单从 distros/*.conf 自动发现，避免与 Makefile / sbom.sh 三处各写一遍而漂移
[ -n "${DISTROS:-}" ] && DISTROS_OVERRIDDEN=1
DISTROS=${DISTROS:-$(ls "$ROOT"/distros/*.conf 2>/dev/null | xargs -r -n1 basename | sed 's/\.conf$//' | tr '\n' ' ')}
for DID in $DISTROS; do
  # conf 里的变量会跨发行版泄漏（IMMUTABLE 泄漏会把 apt_check/compile_cxx 静默降级成跳过），
  # 每轮开头必须清掉
  # EXPECT_* 必须一起清：漏了它们，某个 conf 少写一项就会静默沿用上一个发行版的基线
  # （DISTROS 是字典序 kylin10→kylin11→uos25），而 check 对"期望空、实际空"判 PASS。
  unset IMMUTABLE PIN_NEVER REPACK_DEBS STUB_PROVIDES DPKG_SEGV_WRAPPER ADMINDIR \
        MICRO_INCLUDE BASE_INCLUDE DEVEL_INCLUDE STAGE_INCLUDE SLICE_MICRO \
        SLICE_BASE_EXTRA SLICE_DEVEL_EXTRA SOURCE_DATE_EPOCH MIRROR SUITE COMPONENTS \
        EXPECT_GLIBC EXPECT_LIBSTDCPP EXPECT_GLIBCXX IMAGE METHOD USRMERGE DISPLAY_NAME \
        SRC_ROOTFS ISO_URL ISO_SQUASHFS_PATH SQUASHFS_SHA256 DEBOOTSTRAP_SCRIPT
  . "$ROOT/distros/$DID.conf"
  for TIER in micro base devel; do
    IMG="$IMAGE:$TIER"
    docker image inspect "$IMG" >/dev/null 2>&1 || { echo "  ✗ $IMG 不存在"; FAIL=$((FAIL+1)); continue; }
    out=$(docker run --rm -e http_proxy= -e https_proxy= -e HTTP_PROXY= -e HTTPS_PROXY= \
            -v "$ROOT/test/inner-checks.sh:/checks.sh:ro" "$IMG" /bin/bash /checks.sh 2>/dev/null)
    g(){ printf '%s' "$out" | awk -F= -v k="$1" '$1==k{print $2; exit}'; }
    echo "── $IMG  ($(docker images "$IMG" --format '{{.Size}}'))  $(g os_name)  包=$(g pkgs)"

    # L0 结构（所有档都必须过）
    check os_release Y "$(g os_release)"
    check nsswitch   Y "$(g nsswitch)"
    # /etc/mtab 必须在**镜像里**就是符号链接（运行时那层会兜底，所以只能查 tarball）
    if [ -f "$ROOT/out/$DID-$TIER.tar" ]; then
      mt=$(tar tvf "$ROOT/out/$DID-$TIER.tar" 2>/dev/null | awk '$NF=="/proc/self/mounts" && /etc\/mtab/{print "Y"; exit}')
      check tar_mtab Y "${mt:-N}"
    fi
    check no_sshkey  Y "$(g no_sshkey)"
    check no_firmware Y "$(g no_firmware)"
    check no_kernel  Y "$(g no_kernel)"
    check copyright_kept Y "$(g copyright_kept)"
    # 逐包 copyright：厂商本来就没打的（麒麟 V11 的 libboundscheck/libcryptsetup12/openssl，
    # 已核对过原始 deb 里也没有）列入白名单；白名单外缺失即失败 —— 精简策略写错时
    # 只要还剩一个包有 copyright，旧的 copyright_kept 就永真，抓不住。
    cpmiss=$(printf '%s' "$(g copyright_missing)" | tr ',' '\n' | grep -v '^$' \
      | grep -vxE 'libboundscheck|libcryptsetup12|openssl' | tr '\n' ' ')
    [ -z "$cpmiss" ] && pass "copyright 逐包（白名单外无缺失）" \
      || fail "copyright 白名单外缺失: $cpmiss"
    check policy_rcd Y "$(g policy_rcd)"
    # L1 完整性
    check audit 0 "$(g audit)"
    check elf_broken 0 "$(g elf_broken)"
    check getent_passwd Y "$(g getent_passwd)"
    check getent_group  Y "$(g getent_group)"
    check ldconfig_clean 0 "$(g ldconfig_clean)" warn
    check tz UTC "$(g tz)"
    check localtime Etc/UTC "$(g localtime)" warn
    # machine-id 必须存在且为空（systemd 的 first-boot 语义）——README §8 列了却一直没接线
    check machine_id_empty Y "$(g machine_id_empty)"
    check dpkg_list_ok Y "$(g dpkg_list_ok)"
    # 哨兵：检查集必须跑到最后一行，否则前面所有"通过"都不可信
    check checks_complete Y "$(g checks_complete)"
    # 悬空软链：厂商自带/切片残留的几条是已知且惰性的，不删（删了就动了"等价环境"）；
    # 但清单之外的一律失败 —— 我自己就往 micro 档造过一条 default.target 悬空链，
    # 当时没有任何检查能发现它。
    unexpected=$(printf '%s' "$(g dangling_etc_list)" | tr ',' '\n' | grep -v '^$' \
      | grep -vxE '99-sysctl\.conf|modules\.conf|vconsole\.conf|99apt-download-hook' | tr '\n' ' ')
    [ -z "$unexpected" ] && pass "dangling_etc 仅已知项" \
      || fail "dangling_etc 出现清单外悬空软链: $unexpected"
    # 包数下限：status 断链时 dpkg-query 输出 0 行且退出码 0（历史假通过的机制本身）
    [ "$(g pkgs)" -ge 40 ] 2>/dev/null \
      && pass "pkgs $(g pkgs)" || fail "pkgs: 期望 >=40 实际 $(g pkgs)"
    # os-release 必须有 ID/VERSION_ID（不能是 ?/?）
    oid=$(g os_id)
    if [ "$oid" = "?/?" ] || [ -z "$oid" ]; then
      FAIL=$((FAIL+1)); PROBLEMS+=("  ✗ $IMG os_id 为空或异常: ${oid:-空}")
    else PASS=$((PASS+1)); fi
    # 非 root 用户可运行（很多生产环境强制 runAsNonRoot）
    nr=$(docker run --rm -u 65534:65534 "$IMG" /bin/sh -c 'id -u' 2>/dev/null)
    check nonroot_run 65534 "${nr:-失败}"
    # 基线对账
    check glibc_prefix "$EXPECT_GLIBC" "$(printf '%s' "$(g glibc)" | grep -oE '^[0-9]+\.[0-9]+')"
    check libstdcpp "$EXPECT_LIBSTDCPP" "$(g libstdcpp)"
    check glibcxx   "$EXPECT_GLIBCXX"   "$(g glibcxx)"
    # L2 能力（按档位期望）
    check locale_zh 1 "$(g locale_zh)"
    if [ "$(g ca_bytes)" -gt 100000 ]; then PASS=$((PASS+1))
    else FAIL=$((FAIL+1)); PROBLEMS+=("  ✗ $IMG ca_bytes: $(g ca_bytes) 过小"); fi
    case $TIER in
      micro) check has_apt N "$(g has_apt)"; check apt_check n/a "$(g apt_check)" ;;
      base)  check has_apt Y "$(g has_apt)"; check has_python3 Y "$(g has_python3)"; check tls Y "$(g tls)"
             if [ "${IMMUTABLE:-no}" = yes ]; then
               # UOS V25 的 OS 分发走 OSTree + 玲珑，apt 源里只有应用商店的 GUI 应用
               # （实测 4731 个包名，不含 nano 这类 OS 包）。所以：
               #   · apt update 必须成功（两个需授权的 401 源已默认注释掉，见 lib/common.sh）
               #   · 但装 OS 包必然失败，往返结果是 N(...not-installed) —— 这是产品设计，不是缺陷
               # 断言写成"必须是这个失败形态"，而不是笼统放过：若哪天 update 又坏了，
               # 值会变成 NOUPDATE，这条就会失败。
               case "$(g apt_roundtrip)" in
                 NOUPDATE) fail "apt_roundtrip: apt-get update 失败了（UOS 的 401 授权源是否又启用了？）" ;;
                 N*not-installed*) pass "apt_roundtrip 如期无 OS 包可装（OSTree+玲珑分发）" ;;
                 Y) pass "apt_roundtrip 竟然可装 OS 包（源内容变了，需复核期望）" ;;
                 *) fail "apt_roundtrip 形态未预期: $(g apt_roundtrip)" ;;
               esac
               check apt_check_after OK "$(g apt_check_after)"
               check audit_after 0 "$(g audit_after)"
             else
               check apt_check OK "$(g apt_check)"; check apt_roundtrip Y "$(g apt_roundtrip)"
               # 往返之后 dpkg 状态必须仍然干净——这是"能装包"的真正含义
               check audit_after 0 "$(g audit_after)"
               check apt_check_after OK "$(g apt_check_after)"
             fi ;;
      devel) check has_apt Y "$(g has_apt)"
             [ "${IMMUTABLE:-no}" = yes ] || check apt_check OK "$(g apt_check)"
             check has_cc Y "$(g has_cc)"; check has_make Y "$(g has_make)"
             check compile_c Y "$(g compile_c)"
             if [ "${IMMUTABLE:-no}" = yes ]; then
               check has_cxx N "$(g has_cxx)" warn   # UOS 桌面自身无 g++，已在 conf 注明
             else
               check has_cxx Y "$(g has_cxx)"; check compile_cxx Y "$(g compile_cxx)"
             fi ;;
    esac
    # L3 ABI gate：低地板产物必须能跑；高地板产物按 glibc 判定
    r=$(docker run --rm -v "$ROOT/gate:/g:ro" "$IMG" /g/t_low 2>&1 | tail -1)
    check gate_low "ok 14" "$r"
    if [ -f "$GATE_HIGH" ]; then
      r2=$(docker run --rm -v "$ROOT/gate:/g:ro" "$IMG" /g/t_high 2>&1 | tail -1)
      major=$(printf '%s' "$EXPECT_GLIBC" | cut -d. -f2)
      if [ "$major" -ge 34 ]; then check gate_high "ok 14" "$r2"
      else
        # 负向断言不能只判"没输出 ok 14"：二进制不存在、exec 格式错、缺任意一个
        # 别的库，都会让它"如期失败"，于是这条断言变成永真。必须核对**失败原因**
        # 就是符号天花板本身。
        if [ "$r2" = "ok 14" ]; then
          FAIL=$((FAIL+1)); PROBLEMS+=("  ✗ $IMG gate_high 本应被 GLIBC_2.34 天花板拦住却通过了")
        elif printf '%s' "$r2" | grep -q "GLIBC_2.34. not found"; then
          PASS=$((PASS+1))
        else
          FAIL=$((FAIL+1)); PROBLEMS+=("  ✗ $IMG gate_high 失败了但原因不是 GLIBC_2.34 天花板: $r2")
        fi
      fi
    fi
    # L3b C++ ABI 高地板：t_high_cxx 需要较高的 GLIBCXX（用 std::to_chars 浮点重载）。
    # 原先只有 GLIBC 的高低地板，GLIBCXX 方向压根没有负向门禁 —— t_high 只需要
    # GLIBCXX_3.4.22，三个发行版都满足，等于没测。
    if [ -f "$ROOT/gate/t_high_cxx" ] && [ "$(g compile_cxx)" != n/a ]; then
      r3=$(docker run --rm -v "$ROOT/gate:/g:ro" "$IMG" /g/t_high_cxx 2>&1 | tail -1)
      cxxneed=$(objdump -T "$ROOT/gate/t_high_cxx" 2>/dev/null \
                | grep -oE 'GLIBCXX_[0-9.]+' | sort -V | tail -1 | sed 's/GLIBCXX_//')
      have=${EXPECT_GLIBCXX:-0}
      # 版本比较用 sort -V，别用字符串比较（3.4.9 vs 3.4.28）
      lower=$(printf '%s\n%s\n' "$cxxneed" "$have" | sort -V | head -1)
      if [ "$lower" = "$cxxneed" ]; then
        # 镜像的 GLIBCXX 够高 → 必须能跑
        case $r3 in cxxok*) pass "gate_high_cxx 可运行" ;;
          *) fail "gate_high_cxx: GLIBCXX $have 够用（需 $cxxneed）却跑不起来: $r3" ;; esac
      else
        # 镜像的 GLIBCXX 不够 → 必须被拦住，且原因就是 GLIBCXX 天花板
        # ⚠️ 局限：t_high_cxx 是 Debian 13 编的，GLIBC 和 GLIBCXX 两个地板都高，
        # 在麒麟 V10 上先撞哪一个取决于动态链接器的检查顺序（实测先报 GLIBC_2.34）。
        # 要把 C++ ABI 维度单独隔离出来，需要"低 glibc + 高 libstdc++"的工具链，
        # 本机没有。所以这里接受任一天花板作为拦截原因，但仍然拒绝"原因不明的失败"。
        case $r3 in
          cxxok*) fail "gate_high_cxx 本应被符号天花板拦住却通过了（镜像 GLIBCXX $have < 需要 $cxxneed）" ;;
          *GLIBCXX*|*GLIBC_2.34*) pass "gate_high_cxx 如期被符号天花板拦住" ;;
          *) fail "gate_high_cxx 失败了但原因不是符号天花板: $r3" ;;
        esac
      fi
    fi
    # L4 元数据
    lbl=$(docker inspect "$IMG" --format '{{index .Config.Labels "cn.internal.tier"}}' 2>/dev/null)
    check label_tier "$TIER" "$lbl"
    ss=$(docker inspect "$IMG" --format '{{.Config.StopSignal}}' 2>/dev/null)
    # 条件按"有没有 systemd"判，而不是按档位名：kylin10:micro 带 systemd 却因为
    # 档位叫 micro 而从这条缝里漏掉过。
    if [ "$(g has_systemd)" = Y ]; then
      check stopsignal "SIGRTMIN+3" "${ss:-空}"
      # 桌面 ISO 默认 graphical.target，会去拉 display-manager
      check default_target multi-user.target "$(g default_target)"
      # 至少 mask 掉 udev/内核挂载那批，0 说明改造没生效
      [ "$(g masked_units)" -ge 5 ] 2>/dev/null \
        && pass "masked_units $(g masked_units)" \
        || fail "masked_units: 期望 >=5 实际 $(g masked_units)"
    fi
    # 9 个镜像统一要求：影子文件存在且 root:shadow 0640
    check shadow  "0:42/640" "$(g shadow)"
    check gshadow "0:42/640" "$(g gshadow)"
  done
done
echo
echo "══ 汇总: 通过 $PASS / 失败 $FAIL / 警告 $WARN"
[ ${#PROBLEMS[@]} -gt 0 ] && printf '%s\n' "${PROBLEMS[@]}"

# ── 检查数量基线 ────────────────────────────────────────────────────────────────
# 「失败 0」还不够：检查项被**静默跳过**时汇总同样是全绿。本项目已经踩过好几种
# 跳过方式 —— conf 变量跨发行版泄漏把 apt_check/compile_cxx 降级成 n/a、
# g() 取不到值、helper 函数名拼错导致两条分支都是"命令未找到"。
# 所以数量本身必须是断言：只允许涨，掉下来就是有检查消失了。
BASELINE=${BASELINE:-360}
TOTAL_RUN=$((PASS+FAIL+WARN))
# 只在**全量**跑时校基线：显式指定 DISTROS 是子集调试，撞基线没有意义
if [ -n "${DISTROS_OVERRIDDEN:-}" ]; then
  echo "   检查总数 $TOTAL_RUN（子集运行，跳过基线校验）"
elif [ "$TOTAL_RUN" -lt "$BASELINE" ]; then
  echo "❌ 检查总数 $TOTAL_RUN 低于基线 $BASELINE —— 有检查被静默跳过了"
  echo "   （若确为有意缩减，请同步调整 test/verify.sh 里的 BASELINE 并在 commit 里说明）"
  exit 1
else
  echo "   检查总数 $TOTAL_RUN（基线 $BASELINE）"
fi

[ "$FAIL" -eq 0 ] && echo "✅ 全部必过项通过" || echo "❌ 有 $FAIL 项未过"
exit $([ "$FAIL" -eq 0 ] && echo 0 || echo 1)
