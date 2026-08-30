#!/bin/bash
# 在被测镜像内运行的检查集。输出 key=value 行，由外层汇总。
export LC_ALL=C
A=""; [ -f /usr/lib/dpkg/var/status ] && A="--admindir=/usr/lib/dpkg/var"
kv(){ printf '%s=%s\n' "$1" "$2"; }
# 被破坏的镜像上 apt/dpkg 会挂死（实测：status 断链时 apt-get 永久等待），
# 检查集若跟着卡住，外层就只能拿到截断的输出 —— 而缺失的 key 会被读成"空值"
# 而不是失败。所以凡是碰 dpkg/apt 的地方一律套超时。
T(){ local t=$1; shift; if command -v timeout >/dev/null 2>&1; then timeout -k 5 "$t" "$@"; else "$@"; fi; }
has(){ [ -x "/usr/bin/$1" ] || [ -x "/bin/$1" ] || [ -x "/usr/sbin/$1" ] || [ -x "/sbin/$1" ]; }

# ── L0 结构
kv os_release "$( [ -f /etc/os-release ] && echo Y || echo N )"
kv os_name    "$(. /etc/os-release 2>/dev/null; echo "${NAME:-?}")"
kv nsswitch   "$( [ -f /etc/nsswitch.conf ] && echo Y || echo N )"
# 注意：/etc/mtab 由容器运行时（runc）自动建成 -> /proc/mounts，镜像里有没有都一样，
# 所以在**运行时**查它永远为真、毫无意义。真正的检查在 verify.sh 里对 tarball 做（见 tar_mtab）。
kv mtab_link_runtime "$( [ -L /etc/mtab ] && echo Y || echo N )"
kv machine_id_empty "$( [ -f /etc/machine-id ] && [ ! -s /etc/machine-id ] && echo Y || echo N )"
kv no_sshkey  "$( ls /etc/ssh/ssh_host_* >/dev/null 2>&1 && echo N || echo Y )"
kv no_firmware "$( [ -d /lib/firmware ] || [ -d /usr/lib/firmware ] && echo N || echo Y )"
kv no_kernel  "$( ls /boot/vmlinuz* >/dev/null 2>&1 && echo N || echo Y )"
kv copyright_kept "$( ls /usr/share/doc/*/copyright >/dev/null 2>&1 && echo Y || echo N )"
# 逐包查 copyright。原先只判"存在任意一个"，等于几乎永真：
# 精简策略（path-exclude /usr/share/doc + path-include copyright）一旦写错，
# 只要还剩一个包有 copyright 就能过。
kv copyright_missing "$(for p in $(dpkg-query $A -f '${Package}\n' -W 2>/dev/null | LC_ALL=C sort -u); do
    [ -e "/usr/share/doc/$p/copyright" ] || printf '%s,' "$p"; done)"
kv policy_rcd "$( [ -x /usr/sbin/policy-rc.d ] && echo Y || echo N )"

# ── L1 完整性
kv pkgs   "$(dpkg-query $A -f '${binary:Package}\n' -W 2>/dev/null | wc -l)"
kv audit  "$(T 30 dpkg --audit 2>&1 | wc -l)"
if [ -x /usr/bin/apt-get ]; then
  /usr/bin/apt-get check >/dev/null 2>&1 && kv apt_check OK || kv apt_check BAD
else kv apt_check n/a; fi
# ELF 依赖闭环（抽样 200 个可执行文件，避免过慢）
# ⚠️ `xargs sh -c 'script' _` 里 $0 是占位的 `_`，**文件名在 $1**。
#    之前写成 ldd "$0" 等于一直在 ldd 那个下划线，这条检查恒为 0（9 个镜像白送 9 项）。
#    抽样上限也从 200 提到 1200 并按名排序，让抽样确定且覆盖更广。
broken=$(find /usr/bin /usr/sbin /bin /sbin /usr/lib -maxdepth 4 -type f \( -perm -u+x -o -name '*.so*' \) 2>/dev/null \
  | LC_ALL=C sort | head -1200 \
  | xargs -r -n1 -P4 sh -c '
      # 私有库目录（如 /usr/lib/x86_64-linux-gnu/systemd/）不在 ld.so.conf 里，
      # 由调用方二进制的 RUNPATH 覆盖。单独 ldd 这类 .so 会报 not found，是已知误报，
      # 所以把文件自身所在目录也加进搜索路径再判。
      LD_LIBRARY_PATH="$(dirname "$1")${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
        ldd "$1" 2>/dev/null | grep -q "not found" && echo x' _ 2>/dev/null | wc -l)
kv elf_broken "$broken"
kv getent_passwd "$(getent passwd root >/dev/null 2>&1 && echo Y || echo N)"
kv getent_group  "$(getent group root  >/dev/null 2>&1 && echo Y || echo N)"

# ── L2 能力
kv glibc "$(dpkg-query $A -W -f='${Version}' libc6 2>/dev/null)"
so=$(readlink /usr/lib/x86_64-linux-gnu/libstdc++.so.6 2>/dev/null || readlink /lib/x86_64-linux-gnu/libstdc++.so.6 2>/dev/null)
kv libstdcpp "${so#libstdc++.so.}"
lib=/usr/lib/x86_64-linux-gnu/libstdc++.so.6; [ -e "$lib" ] || lib=/lib/x86_64-linux-gnu/libstdc++.so.6
kv glibcxx "$(grep -aoE 'GLIBCXX_3\.4\.[0-9]+' "$lib" 2>/dev/null | sort -uV | tail -1 | sed 's/GLIBCXX_//')"
kv locale_zh "$(locale -a 2>/dev/null | grep -c '^zh_CN')"
kv ca_bytes  "$(stat -c%s /etc/ssl/certs/ca-certificates.crt 2>/dev/null || echo 0)"
kv has_apt   "$(has apt-get && echo Y || echo N)"
# 悬空软链：镜像里指向不存在目标的软链。我自己就造过一条（micro 档的
# default.target 指向不存在的 multi-user.target），当时没有任何检查能发现。
kv dangling_etc_list "$(find /etc -maxdepth 3 -type l ! -lname /dev/null 2>/dev/null \
  | while read -r l; do [ -e "$l" ] || basename "$l"; done | LC_ALL=C sort -u | tr '\n' ',')"
kv has_systemd "$(has systemctl && echo Y || echo N)"
# 桌面 ISO 出身的 default.target 是 graphical.target，server 镜像必须是 multi-user
kv default_target "$(readlink /etc/systemd/system/default.target 2>/dev/null | sed 's|.*/||')"
kv masked_units "$(find /etc/systemd/system -maxdepth 1 -lname /dev/null 2>/dev/null | wc -l)"
# setuid 的 su/newgrp 没有影子文件就是白送的攻击面
kv shadow "$([ -f /etc/shadow ] && stat -c '%u:%g/%a' /etc/shadow 2>/dev/null || echo 缺)"
kv gshadow "$([ -f /etc/gshadow ] && stat -c '%u:%g/%a' /etc/gshadow 2>/dev/null || echo 缺)"
kv has_python3 "$(has python3 && echo Y || echo N)"
kv has_cc    "$(has cc || has gcc && echo Y || echo N)"
kv has_cxx   "$(has g++ && echo Y || echo N)"
kv has_make  "$(has make && echo Y || echo N)"
kv has_useradd "$(has useradd && echo Y || echo N)"
kv ldconfig_clean "$(ldconfig 2>&1 | wc -l)"

# 编译自检（devel 档）
if has cc || has gcc; then
  printf '#include <stdio.h>\nint main(){puts("cok");return 0;}\n' > /tmp/_c.c
  cc -O2 -o /tmp/_c /tmp/_c.c 2>/dev/null || gcc -O2 -o /tmp/_c /tmp/_c.c 2>/dev/null
  kv compile_c "$( [ -x /tmp/_c ] && [ "$(/tmp/_c 2>/dev/null)" = cok ] && echo Y || echo N )"
else kv compile_c n/a; fi
if has g++; then
  printf '#include <string>\n#include <cstdio>\n#include <thread>\nint main(){std::string s="xok";std::thread t([]{});t.join();printf("%%s\\n",s.c_str());return 0;}\n' > /tmp/_x.cpp
  g++ -O2 -std=c++17 -pthread -o /tmp/_x /tmp/_x.cpp 2>/dev/null
  kv compile_cxx "$( [ -x /tmp/_x ] && [ "$(/tmp/_x 2>/dev/null)" = xok ] && echo Y || echo N )"
else kv compile_cxx n/a; fi

# apt 往返（有 apt 的档）
# ⚠️ 必须用**带 maintainer script** 的包。之前用 tree（控制包里只有 control+md5sums）
#    恰好避开了唯一会失败的类别：厂商 dpkg 在 configure 阶段也会 segv，
#    而无脚本的包 configure 是空操作，所以 tree 永远能过。
if [ -x /usr/bin/apt-get ]; then
  if T 60 /usr/bin/apt-get update -qq >/dev/null 2>&1; then
    DEBIAN_FRONTEND=noninteractive T 90 /usr/bin/apt-get install -y -qq --no-install-recommends nano >/dev/null 2>&1
    st=$(dpkg-query $A -W -f='${Status}' nano 2>/dev/null)
    if [ "$st" = "install ok installed" ]; then
      DEBIAN_FRONTEND=noninteractive T 60 /usr/bin/apt-get purge -y -qq nano >/dev/null 2>&1
      if has nano; then kv apt_roundtrip PARTIAL; else kv apt_roundtrip Y; fi
    else
      kv apt_roundtrip "N(${st:-未装})"
    fi
  else kv apt_roundtrip NOUPDATE; fi
else kv apt_roundtrip n/a; fi
# 往返**之后**再采一次状态：之前 audit 在往返前采样，往返后的损坏从未被审计
kv audit_after "$(T 30 dpkg --audit 2>&1 | wc -l)"
if [ -x /usr/bin/apt-get ]; then
  T 30 /usr/bin/apt-get check >/dev/null 2>&1 && kv apt_check_after OK || kv apt_check_after BAD
else kv apt_check_after n/a; fi

# 时区必须是 UTC（容器约定；官方 official-images 的通用测试也查这一项）
# ⚠️ `date -u +%Z` 强制 UTC，与 /etc/localtime 无关，恒为 UTC（又是 9 项白送）。
#    要查镜像自身的时区就得用不带 -u 的 date，或直接看 /etc/localtime 指向。
kv tz "$(date +%Z 2>/dev/null)"
kv localtime "$(readlink -f /etc/localtime 2>/dev/null | sed 's|.*/zoneinfo/||')"
# os-release 的 ID / VERSION_ID 必须有值（扫描器与运维靠它识别系统）
kv os_id "$(. /etc/os-release 2>/dev/null; echo "${ID:-?}/${VERSION_ID:-?}")"
# dpkg 抽查：随便挑一个已装包，能列出文件才说明 info 库是完整的
#   （专防"status 是断链 -> audit 输出 0 行 -> 被当成通过"这类静默失效）
# 不用 awk：被测镜像本身可能没装（micro 档就没有），测试工具不该引入额外依赖
_p=$(dpkg-query $A -W 2>/dev/null | head -1 | cut -f1)
kv dpkg_list_ok "$( [ -n "$_p" ] && [ "$(dpkg-query $A -L "$_p" 2>/dev/null | wc -l)" -gt 0 ] && echo Y || echo N )"

# TLS（有 curl 的档）
if has curl; then
  curl -fsSI --max-time 15 https://mirrors.aliyun.com >/dev/null 2>&1 && kv tls Y || kv tls N
else kv tls n/a; fi

# ── 完成哨兵 ────────────────────────────────────────────────────────────────
# 必须是最后一行。verify 硬断言它为 Y，这样"检查集中途挂掉/被杀"就一定是失败，
# 而不是「那几个 key 恰好为空所以没人管」。这类静默截断本项目已经踩过一次。
kv checks_complete Y
