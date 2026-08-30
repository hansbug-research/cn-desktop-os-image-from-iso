#!/bin/bash
# 在麒麟 V10 的 stage 容器内执行：自举 configure -> 装档位包 -> 容器化适配 -> 自检
export DEBIAN_FRONTEND=noninteractive
set -u
say(){ printf '    %s\n' "$*"; }

mkdir -p /run/lock /var/lib/dpkg/updates
# ① 真正的自举：用**目标系统自己的 dpkg 1.19.7** 跑 debootstrap 第二阶段
#    （宿主 Debian13 的 dpkg 1.22 写出的 status 麒麟读不了，所以注册+配置必须在这里做）
if [ -x /debootstrap/debootstrap ]; then
  /debootstrap/debootstrap --second-stage 2>&1 | tail -3
  say "第二阶段 rc=$?"
fi
dpkg --configure -a --force-depends >/dev/null 2>&1
say "自举结果: installed=$(grep -c '^Status: install ok installed' /var/lib/dpkg/status 2>/dev/null) unpacked=$(grep -c '^Status: install ok unpacked' /var/lib/dpkg/status 2>/dev/null) dpkg=$(dpkg --version 2>/dev/null|head -1|grep -oE '[0-9]+\.[0-9]+\.[0-9]+')"

# ①b debootstrap 第二阶段只装 required 集；--include 下来的 base 集（apt 等）
#     还躺在 /var/cache/apt/archives。用这些**已通过 GPG 校验**的 deb 补装。
if ! command -v apt-get >/dev/null 2>&1; then
  n=$(ls /var/cache/apt/archives/*.deb 2>/dev/null | wc -l)
  say "apt 不在，从 stage 缓存补装 $n 个 deb"
  dpkg -i --force-depends --force-confold /var/cache/apt/archives/*.deb >/dev/null 2>&1 || true
  dpkg --configure -a --force-depends >/dev/null 2>&1 || true
  say "补装后: installed=$(grep -c '^Status: install ok installed' /var/lib/dpkg/status) apt=$(command -v apt-get||echo 仍无)"
fi

# ② base-files 在 --foreign 解包后常处于损坏态，重装修好
mkdir -p /etc/apt/preferences.d /usr/share/keyrings
cp /keys/kylin-archive-keyring.gpg /usr/share/keyrings/ 2>/dev/null || true
printf 'deb [signed-by=/usr/share/keyrings/kylin-archive-keyring.gpg] %s %s %s\n' "$MIRROR" "$SUITE" "$COMPONENTS" > /etc/apt/sources.list
printf 'APT::Key::gpgvcommand "gpgv";\n' > /etc/apt/apt.conf.d/docker-gpgv
if [ -n "${PIN_NEVER:-}" ]; then
  { for p in $PIN_NEVER; do printf 'Package: %s\nPin: release *\nPin-Priority: -1\n\n' "$p"; done; } \
    > /etc/apt/preferences.d/99-container-never-install
fi
apt-get update -qq 2>&1 | tail -1
apt-get install -y -qq --reinstall base-files >/dev/null 2>&1 || true
dpkg --configure -a >/dev/null 2>&1 || true

# ③ 装档位包（逐包，规避大事务里的厂商 dpkg 缺陷）
# 注意：apt-get 的退出码不能被管道丢掉，且 `apt-get check` **只验已装包之间的依赖一致性**，
# 对"某个包压根没装上"一无所知。所以装完必须逐包断言 Status 为 install ok installed。
MISSING=""
if [ -n "${PKGS:-}" ]; then
  for p in $PKGS; do
    out=$(apt-get install -y -qq --no-install-recommends "$p" 2>&1); rc=$?
    printf '%s' "$out" | grep -iE '^E:|segmentation' | head -1
    [ "$rc" -ne 0 ] && say "  ⚠ apt install $p 退出码 $rc"
    dpkg --configure -a >/dev/null 2>&1 || true
  done
  for p in $PKGS; do
    st=$(dpkg-query -W -f='${Status}' "$p" 2>/dev/null)
    [ "$st" = "install ok installed" ] || MISSING="$MISSING $p"
  done
fi

# ④ micro 档拔掉 apt
if [ "$TIER" = micro ]; then
  for p in apt apt-utils; do
    if dpkg-query -W "$p" >/dev/null 2>&1; then
      rm -f /var/lib/dpkg/info/$p.pre* /var/lib/dpkg/info/$p.post*
      dpkg --purge --force-all "$p" >/dev/null 2>&1 || true
    fi
  done
fi

# ⑤ 证书 + locale
command -v update-ca-certificates >/dev/null 2>&1 && update-ca-certificates >/dev/null 2>&1
if [ -d /usr/share/i18n/locales ] && command -v localedef >/dev/null 2>&1; then
  localedef -i zh_CN -c -f UTF-8 zh_CN.UTF-8 2>/dev/null || true
  localedef -i en_US -c -f UTF-8 en_US.UTF-8 2>/dev/null || true
fi

# ⑥ 容器化适配 —— 直接复用 lib/common.sh 的 adapt_container，不再手写复刻。
#    之前这里是一份手抄版，注释写着"与 adapt_container 保持一致"却没有任何机制保障，
#    结果 kylin10 静默缺了 apt 调优、/tmp 权限、nsswitch 兜底、SONAME 冗余文件修复等一整批。
if [ -f /dosbuild-lib/common.sh ]; then
  # 仓库是挂载进来的，路径与构建容器不同，所以显式指定 ASSETS_DIR / KEYRING
  ASSETS_DIR=/dosbuild-assets
  KEYRING=/keys/kylin-archive-keyring.gpg
  . /dosbuild-lib/common.sh
  SRCLIST="deb [signed-by=/usr/share/keyrings/kylin-archive-keyring.gpg] $MIRROR $SUITE $COMPONENTS"
  adapt_container / "$SRCLIST" "${DID:-}"
  slim_locales /
  say "容器化适配: 复用 lib/common.sh::adapt_container"
else
  say "!! 找不到 /dosbuild-lib/common.sh，无法做容器化适配"; exit 1
fi

# ⑦ 自检
hash -r 2>/dev/null || true
AC=n/a
if [ -x /usr/bin/apt-get ]; then /usr/bin/apt-get check >/dev/null 2>&1 && AC=OK || AC=BAD; fi
say "自检: apt-check=$AC audit=$(dpkg --audit 2>&1|wc -l) locale=$(locale -a 2>/dev/null|grep -c zh_CN) ca=$(stat -c%s /etc/ssl/certs/ca-certificates.crt 2>/dev/null||echo 0)"
if [ "$AC" = BAD ]; then say '!! apt 依赖状态不健康'; apt-get check 2>&1 | head -12 | sed 's/^/      /'; exit 1; fi
if [ -n "${MISSING# }" ]; then say "!! 以下档位包没装上:$MISSING"; exit 1; fi
exit 0
