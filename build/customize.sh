#!/bin/bash
# mmdebstrap --customize-hook：$1 = rootfs 路径（宿主侧）
# 环境: ROOT DID TIER
set -eu
ROOT="${ROOT:-/w}"; . "$ROOT/lib/common.sh"
R=$1; DID="${DID:?}"; TIER="${TIER:?}"
. "$ROOT/distros/$DID.conf"
ADM="${ADMINDIR:-var/lib/dpkg}"

# ══ 阶段 1：还需要网络的操作（必须在 adapt_container 删掉 resolv.conf 之前做）
# 保证 chroot 内 DNS 可用
cp -f /etc/resolv.conf "$R/etc/resolv.conf" 2>/dev/null || \
  printf 'nameserver 223.5.5.5\nnameserver 119.29.29.29\n' > "$R/etc/resolv.conf"

# devel 档的工具链由 --include 一次装到位；这里只做厂商缺陷兜底
if [ "$TIER" = devel ]; then
  fix_unconfigured_noscript_pkgs "$R" "$ADM"
  chroot "$R" /bin/bash -c 'export DEBIAN_FRONTEND=noninteractive; dpkg --configure -a >/dev/null 2>&1; true' || true
  fix_unconfigured_noscript_pkgs "$R" "$ADM"
  log "[$DID/$TIER] 工具链: $(chroot "$R" /bin/sh -c 'echo "gcc=$(command -v gcc||echo -) g++=$(command -v g++||echo -) make=$(command -v make||echo -)"' 2>/dev/null)"
fi

# CA 证书（postinst 可能没跑成，显式重跑）
chroot "$R" /bin/sh -c 'command -v update-ca-certificates >/dev/null 2>&1 && update-ca-certificates >/dev/null 2>&1; true' || true

# locale：只生成 zh_CN.UTF-8 / en_US.UTF-8
chroot "$R" /bin/sh -c '
  if [ -d /usr/share/i18n/locales ] && command -v localedef >/dev/null 2>&1; then
    localedef -i zh_CN -c -f UTF-8 zh_CN.UTF-8 2>/dev/null || true
    localedef -i en_US -c -f UTF-8 en_US.UTF-8 2>/dev/null || true
  fi; true' || true

# micro 档：拔掉 apt（保留 dpkg 与包数据库，比麒麟官方 micro 更可审计）
if [ "$TIER" = micro ]; then
  ADM="$ADM" chroot "$R" /bin/sh -c '
    for p in apt apt-utils; do
      if dpkg-query -W "$p" >/dev/null 2>&1; then
        rm -f "/$ADM/info/$p".pre* "/$ADM/info/$p".post*
        dpkg --purge --force-all "$p" >/dev/null 2>&1 || true
      fi
    done; true' || true
fi

# ══ 阶段 2：不需要网络的收尾
fix_unconfigured_noscript_pkgs "$R" "$ADM"
chroot "$R" /bin/sh -c 'dpkg --configure -a >/dev/null 2>&1; true' || true

SRCLIST="deb [signed-by=/usr/share/keyrings/kylin-combined.gpg] $MIRROR $SUITE $COMPONENTS"
adapt_container "$R" "$SRCLIST" "$DID"
slim_locales "$R"
[ "$TIER" = micro ] && rm -rf "$R/var/lib/apt" "$R/var/cache/apt" 2>/dev/null || true

# 最终自检（写进构建日志，便于审计）
log "[$DID/$TIER] 自检: $(chroot "$R" /bin/sh -c 'echo -n "apt-check=$([ -x /usr/bin/apt-get ] && (/usr/bin/apt-get check >/dev/null 2>&1 && echo OK || echo BAD) || echo n/a) audit=$(dpkg --audit 2>&1|wc -l) locale=$(locale -a 2>/dev/null|grep -c zh_CN) ca=$(stat -c%s /etc/ssl/certs/ca-certificates.crt 2>/dev/null||echo 0)"' 2>/dev/null)"
