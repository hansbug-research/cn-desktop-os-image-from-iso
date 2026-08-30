#!/bin/bash
# 在目标镜像容器内执行：按可控顺序安装包，处理厂商 dpkg 缺陷，最后自检
# 环境变量: PRE_PKGS（前置，可空）  PKGS（目标）
export DEBIAN_FRONTEND=noninteractive
set -u

apt_ok() { apt-get check >/dev/null 2>&1; }

# 麒麟已知缺陷：部分包（如 bzip2）用硬链接，配合 usr-merge 的 /bin -> usr/bin，
# dpkg 处理时会段错误。文件实际已解包，`dpkg --configure -a` 可恢复。
# 因此最多重试 4 轮，每轮先恢复中断状态；最终以 apt-get check 通过为验收标准。
install_with_retry() {
  local pkgs="$1" i out
  [ -n "$pkgs" ] || return 0
  for i in 1 2 3 4; do
    dpkg --configure -a >/dev/null 2>&1 || true
    out=$(apt-get install -y -qq --no-install-recommends $pkgs 2>&1)
    if printf '%s' "$out" | grep -q 'segmentation fault'; then
      echo "    [重试 $i] dpkg 段错误（厂商包硬链接缺陷），恢复后再试"
      continue
    fi
    dpkg --configure -a >/dev/null 2>&1 || true
    if apt_ok; then return 0; fi
    echo "    [重试 $i] apt check 未过，继续"
  done
  dpkg --configure -a >/dev/null 2>&1 || true
  apt_ok
}

apt-get update -qq || { echo "    !! apt update 失败"; exit 1; }
if ! install_with_retry "${PRE_PKGS:-}"; then echo "    !! 前置包安装失败"; exit 1; fi
if ! install_with_retry "${PKGS:-}";     then echo "    !! 目标包安装失败"; exit 1; fi

echo "    验收: apt check $(apt-get check 2>&1 | grep -c '^E:') 错误 / dpkg audit $(dpkg --audit 2>&1 | wc -l) 行"

# 清理
rm -rf /var/lib/apt/lists/* /var/cache/apt/archives/*.deb /var/cache/apt/*.bin \
       /boot/* /lib/modules/* /usr/lib/modules/* /lib/firmware /usr/lib/firmware \
       /var/lib/initramfs-tools/* 2>/dev/null || true
find /usr/share/doc /usr/share/man /usr/share/info -type f -delete 2>/dev/null || true
find /var/log -type f -exec sh -c ': > "$1"' _ {} \; 2>/dev/null || true
exit 0
