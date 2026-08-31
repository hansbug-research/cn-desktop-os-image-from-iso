#!/bin/bash
# 能力探针：在被测镜像内**真跑**每一项，输出 cap.<名字>=<Y|N> 供外层汇总。
# 原则：不看包列表推断，一律实测 —— 装了 gcc 不等于能编出可跑的二进制
# （麒麟 V11 就有 gcc 包装脚本往 stderr 吐 grep 报错的情况）。
export LC_ALL=C
kv(){ printf 'cap.%s=%s\n' "$1" "$2"; }
has(){ command -v "$1" >/dev/null 2>&1; }
yn(){ [ "$1" = 0 ] && echo Y || echo N; }
T(){ local t=$1; shift; if has timeout; then timeout -k 3 "$t" "$@"; else "$@"; fi; }
A=""; [ -f /usr/lib/dpkg/var/status ] && A="--admindir=/usr/lib/dpkg/var"
W=$(mktemp -d); cd "$W" || exit 1

# ── L1 基础运行时 ────────────────────────────────────────────────
kv sh          "$(has sh && echo Y || echo N)"
kv bash        "$(has bash && echo Y || echo N)"
kv coreutils   "$( { has ls && has cp && has chmod && has df; } && echo Y || echo N)"
kv findutils   "$( { has find && has xargs; } && echo Y || echo N)"
kv textutils   "$( { has grep && has sed && has awk; } && echo Y || echo N)"
kv getent      "$(getent passwd root >/dev/null 2>&1; yn $?)"
kv locale_zh   "$(locale -a 2>/dev/null | grep -qi 'zh_CN.utf8\|zh_CN.UTF-8' && echo Y || echo N)"
kv localtime   "$( [ -e /etc/localtime ] && echo Y || echo N)"
# CA bundle 的路径按发行版族不同：Debian 系在 /etc/ssl/certs/ca-certificates.crt，
# RH 系在 /etc/pki/tls/certs/ca-bundle.crt（且是指向 ca-trust extracted 的符号链接）。
# 只查前者会让 rpm 系被试在「有证书且 TLS 握手成功」的情况下报没有证书。
kv ca_bundle   "$( { [ -s /etc/ssl/certs/ca-certificates.crt ] || [ -s /etc/pki/tls/certs/ca-bundle.crt ]; } && echo Y || echo N)"
kv dns         "$(getent hosts mirrors.aliyun.com >/dev/null 2>&1; yn $?)"
# TLS 真握手（不只是有没有证书）
tls=N
if has openssl; then
  T 25 openssl s_client -connect mirrors.aliyun.com:443 -servername mirrors.aliyun.com \
     -verify_return_error -brief </dev/null >/dev/null 2>&1 && tls=Y
fi
[ "$tls" = N ] && has curl && { T 25 curl -sS --max-time 20 -o /dev/null https://mirrors.aliyun.com/ 2>/dev/null && tls=Y; }
[ "$tls" = N ] && has wget && { T 25 wget -q -O /dev/null https://mirrors.aliyun.com/ 2>/dev/null && tls=Y; }
kv tls "$tls"

# ── L2 包管理 ────────────────────────────────────────────────────
# 口径是**能力**而不是**某个工具**：同一项能力在 deb 侧用 dpkg/apt 测，rpm 侧用
# rpm/dnf 测。早先这一段全是 dpkg 专用，rpm 系被试会在「dpkg 数据库可查」上一片
# 不支持 —— 那不是缺口，是拿错了尺子。包管理系由镜像自己判定，不从外部传入。
if has rpm && ! has dpkg; then PKGSYS=rpm; elif has dpkg; then PKGSYS=deb; else PKGSYS=none; fi
kv pkgsys "$PKGSYS"

case $PKGSYS in
deb) PKGDB_N=$(dpkg-query $A -f '${Package}\n' -W 2>/dev/null | wc -l) ;;
rpm) PKGDB_N=$(rpm -qa 2>/dev/null | wc -l) ;;
*)   PKGDB_N=0 ;;
esac
kv pkgdb_query "$( [ "$PKGDB_N" -gt 20 ] && echo Y || echo N)"
kv pkgdb_count "$PKGDB_N"

if   has apt-get; then PKGMGR=apt-get
elif has dnf;     then PKGMGR=dnf
elif has yum;     then PKGMGR=yum
else PKGMGR=""; fi
kv pkgmgr "$( [ -n "$PKGMGR" ] && echo Y || echo N)"
kv pkgmgr_name "${PKGMGR:-none}"

if [ "$PKGSYS" = rpm ]; then
  kv pkg_sources "$( ls /etc/yum.repos.d/*.repo >/dev/null 2>&1 && echo Y || echo N)"
  kv pkg_keyring "$( ls /etc/pki/rpm-gpg/* >/dev/null 2>&1 && echo Y || echo N)"
else
  kv pkg_sources "$( { [ -s /etc/apt/sources.list ] || ls /etc/apt/sources.list.d/*.list >/dev/null 2>&1 || ls /etc/apt/sources.list.d/*.sources >/dev/null 2>&1; } && echo Y || echo N)"
  kv pkg_keyring "$( { ls /etc/apt/trusted.gpg.d/* >/dev/null 2>&1 || [ -s /etc/apt/trusted.gpg ] || ls /usr/share/keyrings/* >/dev/null 2>&1; } && echo Y || echo N)"
fi

# 元数据刷新 + 装卸往返。都挑一个带 maintainer script / scriptlet 的包，
# 无脚本的包会掩盖厂商包管理器自身的问题。
# 源清单为空时 `apt-get update` 会**成功**——没东西要取，退出码自然是 0。
# 记成「能更新」是错的：空集上的全称命题恒真，而能力一点没有。凝思出厂无源
# （厂商没有公开的在线仓库），必须与「有源且能更新」分开报。
if [ -z "$PKGMGR" ]; then
  kv pkg_update n/a; kv pkg_roundtrip n/a; kv pkg_check n/a
elif [ "$PKGSYS" = deb ] && ! { [ -s /etc/apt/sources.list ] && grep -qE '^[[:space:]]*deb[[:space:]]' /etc/apt/sources.list; } \
     && ! ls /etc/apt/sources.list.d/*.list >/dev/null 2>&1 \
     && ! ls /etc/apt/sources.list.d/*.sources >/dev/null 2>&1; then
  kv pkg_update nosrc; kv pkg_roundtrip nosrc
  T 30 apt-get check >/dev/null 2>&1; kv pkg_check "$(yn $?)"
elif [ "$PKGSYS" = rpm ] && ! ls /etc/yum.repos.d/*.repo >/dev/null 2>&1; then
  kv pkg_update nosrc; kv pkg_roundtrip nosrc
  T 120 rpm -Va --nofiles --nodigest --noscripts >/dev/null 2>&1; kv pkg_check "$(yn $?)"
elif [ "$PKGSYS" = rpm ]; then
  T 120 $PKGMGR -q makecache >/dev/null 2>&1; kv pkg_update "$(yn $?)"
  if T 180 $PKGMGR -y -q install nano >/dev/null 2>&1 && rpm -q nano >/dev/null 2>&1; then
    T 120 $PKGMGR -y -q remove nano >/dev/null 2>&1
    has nano && kv pkg_roundtrip PARTIAL || kv pkg_roundtrip Y
  else kv pkg_roundtrip N; fi
  # rpm 侧的「依赖自洽」对应 rpm -Va --nofiles --nodigest（只验依赖与元数据）
  T 120 rpm -Va --nofiles --nodigest --noscripts >/dev/null 2>&1; kv pkg_check "$(yn $?)"
else
  T 90 apt-get update -qq >/dev/null 2>&1; kv pkg_update "$(yn $?)"
  DEBIAN_FRONTEND=noninteractive T 120 apt-get install -y -qq --no-install-recommends nano >/dev/null 2>&1
  st=$(dpkg-query $A -W -f='${Status}' nano 2>/dev/null)
  if [ "$st" = "install ok installed" ]; then
    DEBIAN_FRONTEND=noninteractive T 90 apt-get purge -y -qq nano >/dev/null 2>&1
    has nano && kv pkg_roundtrip PARTIAL || kv pkg_roundtrip Y
  else kv pkg_roundtrip N; fi
  T 30 apt-get check >/dev/null 2>&1; kv pkg_check "$(yn $?)"
fi

# 本地包直装（离线分发场景）：装一个本机没有的包，再卸干净。
# deb 侧在镜像内现造；rpm 侧造包要 rpm-build（只有 devel 档有），所以由 runner
# 把一个最小 noarch 包只读挂到 /probe-fixtures，三档同样口径。
if [ "$PKGSYS" = rpm ]; then
  fx=$(ls /probe-fixtures/*.noarch.rpm 2>/dev/null | head -1)
  if [ -n "$fx" ]; then
    T 60 rpm -i --nodigest --nosignature "$fx" >/dev/null 2>&1 \
      && rpm -q capprobe >/dev/null 2>&1 && T 60 rpm -e capprobe >/dev/null 2>&1
    kv pkg_local_install "$(yn $?)"
  else kv pkg_local_install n/a; fi
elif has dpkg && has dpkg-deb; then
  mkdir -p d/DEBIAN d/usr/share/doc/capprobe
  printf 'Package: capprobe\nVersion: 1.0\nArchitecture: all\nMaintainer: t <t@t>\nDescription: probe\n' > d/DEBIAN/control
  echo x > d/usr/share/doc/capprobe/README
  dpkg-deb --build --root-owner-group d p.deb >/dev/null 2>&1 \
    && T 40 dpkg $A -i p.deb >/dev/null 2>&1 && T 40 dpkg $A -P capprobe >/dev/null 2>&1
  kv pkg_local_install "$(yn $?)"
else kv pkg_local_install N; fi

# ── L3 编译构建（真编真跑）──────────────────────────────────────
printf '#include <stdio.h>\nint main(){printf("c-ok\\n");return 0;}\n' > a.c
printf '#include <cstdio>\n#include <string>\n#include <vector>\n#include <thread>\n#include <mutex>\nint main(){std::vector<std::string> v{"a","bb"};std::mutex m;int n=0;std::thread t([&]{std::lock_guard<std::mutex> g(m);for(auto&s:v)n+=s.size();});t.join();std::printf("cxx-ok %%d\\n",n);return 0;}\n' > a.cpp
kv cc_present  "$(has gcc || has cc; yn $?)"
kv cxx_present "$( { has g++ || has c++; } && echo Y || echo N)"
kv make        "$(has make && echo Y || echo N)"
kv binutils    "$( { has ld && has ar && has strip && has objdump; } && echo Y || echo N)"
kv libc_headers "$( { [ -e /usr/include/stdio.h ] && [ -e /usr/include/x86_64-linux-gnu/sys/types.h ]; } && echo Y || echo N)"
kv pkgconfig   "$(has pkg-config && echo Y || echo N)"
kv cmake       "$(has cmake && echo Y || echo N)"
kv autotools   "$( { has autoconf && has automake; } && echo Y || echo N)"
if has gcc || has cc; then
  CC=$(has gcc && echo gcc || echo cc)
  T 60 $CC -O2 -o a a.c 2>/dev/null && ./a >/dev/null 2>&1; kv compile_c "$(yn $?)"
  T 60 $CC -O2 -static -o as a.c 2>/dev/null && ./as >/dev/null 2>&1; kv static_link "$(yn $?)"
  # 厂商 gcc 包装脚本是否污染 stderr（编译成功但 stderr 非空，会坑用 stderr 判错的 CI）
  err=$(T 60 $CC -O2 -o a2 a.c 2>&1 >/dev/null); kv cc_clean_stderr "$( [ -z "$err" ] && echo Y || echo N)"
else kv compile_c N; kv static_link N; kv cc_clean_stderr n/a; fi
if has g++ || has c++; then
  CXX=$(has g++ && echo g++ || echo c++)
  T 90 $CXX -O2 -pthread -o b a.cpp 2>/dev/null && ./b >/dev/null 2>&1; kv compile_cxx "$(yn $?)"
  T 90 $CXX -O2 -std=c++17 -pthread -o b17 a.cpp 2>/dev/null && ./b17 >/dev/null 2>&1; kv cxx17 "$(yn $?)"
  T 90 $CXX -O2 -std=c++20 -pthread -o b20 a.cpp 2>/dev/null && ./b20 >/dev/null 2>&1; kv cxx20 "$(yn $?)"
else kv compile_cxx N; kv cxx17 N; kv cxx20 N; fi
# make 能否真的驱动一次构建
if has make && { has gcc || has cc; }; then
  printf 'all: a3\na3: a.c\n\t$(CC) -o a3 a.c\n' > Makefile
  T 60 make -s >/dev/null 2>&1 && ./a3 >/dev/null 2>&1; kv make_build "$(yn $?)"
else kv make_build N; fi

# ── L4 语言与常用工具 ───────────────────────────────────────────
kv python3 "$(has python3 && echo Y || echo N)"
kv python3_run "$(has python3 && T 25 python3 -c 'import json,ssl,sys;json.dumps({})' >/dev/null 2>&1 && echo Y || echo N)"
kv python3_ssl "$(has python3 && T 25 python3 -c 'import ssl;ssl.create_default_context()' >/dev/null 2>&1 && echo Y || echo N)"
kv python3_dev "$( ls /usr/include/python3*/Python.h >/dev/null 2>&1 && echo Y || echo N)"
kv perl    "$(has perl && echo Y || echo N)"
kv openssl "$(has openssl && echo Y || echo N)"
kv curl    "$(has curl && echo Y || echo N)"
kv wget    "$(has wget && echo Y || echo N)"
kv git     "$(has git && echo Y || echo N)"
kv tar     "$(has tar && echo Y || echo N)"
kv gzip    "$(has gzip && echo Y || echo N)"
kv xz      "$(has xz && echo Y || echo N)"
kv zstd    "$(has zstd && echo Y || echo N)"
kv unzip   "$(has unzip && echo Y || echo N)"

# ── L5 运维排查 ─────────────────────────────────────────────────
kv ps      "$(has ps && echo Y || echo N)"
kv top     "$( { has top || has htop; } && echo Y || echo N)"
kv sock_tools "$( { has ss || has netstat; } && echo Y || echo N)"
kv ip_tools "$( { has ip || has ifconfig; } && echo Y || echo N)"
kv ping    "$(has ping && echo Y || echo N)"
kv dnsutil "$( { has dig || has nslookup || has host; } && echo Y || echo N)"
kv strace  "$(has strace && echo Y || echo N)"
kv gdb     "$(has gdb && echo Y || echo N)"
kv file    "$(has file && echo Y || echo N)"
kv pager   "$( { has less || has more; } && echo Y || echo N)"
kv editor  "$( { has vi || has vim || has nano; } && echo Y || echo N)"
kv lsof    "$(has lsof && echo Y || echo N)"

# ── L6 容器语义 ─────────────────────────────────────────────────
kv useradd "$(has useradd && echo Y || echo N)"
if has useradd; then
  T 25 useradd -m -s /bin/sh probeu >/dev/null 2>&1; r=$?
  kv useradd_works "$(yn $r)"
  if [ $r = 0 ]; then
    T 25 su -s /bin/sh probeu -c 'id -u' >/dev/null 2>&1; kv su_to_user "$(yn $?)"
    T 25 userdel -r probeu >/dev/null 2>&1
  else kv su_to_user N; fi
else kv useradd_works N; kv su_to_user N; fi
kv shadow_files "$( { [ -f /etc/shadow ] && [ -f /etc/gshadow ]; } && echo Y || echo N)"
kv sudo    "$(has sudo && echo Y || echo N)"
kv systemd "$( { has systemctl && [ -x /lib/systemd/systemd -o -x /usr/lib/systemd/systemd ]; } && echo Y || echo N)"
kv default_target "$(readlink /etc/systemd/system/default.target 2>/dev/null | sed 's|.*/||')"
kv tmp_writable "$(touch /tmp/.probe 2>/dev/null && rm -f /tmp/.probe && echo Y || echo N)"
kv var_writable "$(touch /var/.probe 2>/dev/null && rm -f /var/.probe && echo Y || echo N)"
kv nsswitch "$( [ -f /etc/nsswitch.conf ] && echo Y || echo N)"
kv policy_rcd "$( [ -x /usr/sbin/policy-rc.d ] && echo Y || echo N)"
# 信号处理：能不能 trap 并正常收 TERM（HEALTHCHECK / 优雅退出的基础）
kv signal_trap "$(sh -c 'trap "exit 0" TERM; (sleep 0.2; kill -TERM $$) & wait' >/dev/null 2>&1 && echo Y || echo N)"

# ── L7 安全与合规相关 ───────────────────────────────────────────
kv setuid_bins "$(find / -xdev -perm -4000 -type f 2>/dev/null | wc -l)"
kv file_caps   "$(has getcap && getcap -r / 2>/dev/null | wc -l || echo n/a)"
# rpm 系不装 copyright 到 /usr/share/doc/*/copyright，许可证在 /usr/share/licenses/。
if [ "$PKGSYS" = rpm ]; then
  kv copyright "$(ls -d /usr/share/licenses/*/ >/dev/null 2>&1 && echo Y || echo N)"
else
  kv copyright "$(ls /usr/share/doc/*/copyright >/dev/null 2>&1 && echo Y || echo N)"
fi
kv os_id       "$(. /etc/os-release 2>/dev/null; echo "${ID:-?}-${VERSION_ID:-?}")"
# glibc 版本与架构：包数据库问出来的更可信（ldd --version 会被包装脚本影响），
# 但要按包管理系取 —— rpm 系没有 libc6 这个包名。
if [ "$PKGSYS" = rpm ]; then
  kv glibc "$(rpm -q --qf '%{VERSION}' glibc 2>/dev/null | head -c 12)"
  kv arch  "$(rpm -q --qf '%{ARCH}' glibc 2>/dev/null)"
else
  kv glibc "$(dpkg-query $A -W -f='${Version}' libc6 2>/dev/null | head -c 12)"
  kv arch  "$(dpkg-query $A -W -f='${Architecture}' libc6 2>/dev/null)"
fi
cd /; rm -rf "$W"
# 探针自身的版本指纹。矩阵横向对比的前提是 15 份输出出自同一版探针；
# 改了探针只重跑一部分镜像，混着的矩阵看不出任何异常。有了它，
# verify.py 能断言 15 份指纹全同。
kv probe_sha "$(sha256sum /cap.sh 2>/dev/null | cut -c1-12)"
kv probe_complete Y
