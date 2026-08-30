#!/bin/sh
# 银河麒麟桌面 V11 dpkg 缺陷绕过器（仅供 apt 调用，命令行 dpkg 不受影响）
#
# 现象：dpkg 1.22.6-ok3k1.9 在容器内执行 `--unpack` 时，**文件已正确解包**，
#       但收尾阶段 SIGSEGV（退出码 139）。apt 见非零退出即中止整个事务，
#       报 "E: Sub-process /usr/bin/dpkg received a segmentation fault"。
# 事实：紧接着 `dpkg --configure --pending` 能把包配置完，最终 dpkg --audit 与
#       apt-get check 均干净——崩溃发生在状态已落盘之后。
#
# ⚠️ 这个文件**会随镜像出厂**，改变的是运行时行为，不是只在构建期生效。
#    见 report.md §9.2（被推翻的判断）。关闭方法：删掉 /etc/apt/apt.conf.d/docker-dpkg-wrapper。
#
# 设计上刻意保留判别力：
#   · 只对 --unpack / --install 吸收 139，其它调用与其它退出码原样透传
#   · 补跑 configure **不加 --force-depends**（加了会无视未满足依赖照样返回 0，
#     兜底路径就再也分不出"崩了但没事"和"真的坏了"）
#   · 补跑之后做后置断言：仍有半配置状态就照实返回 139，不掩盖
REAL=/usr/bin/dpkg
"$REAL" "$@"
rc=$?
[ "$rc" -ne 139 ] && exit "$rc"
case " $* " in
  *" --unpack "*|*" --install "*) ;;
  *) exit "$rc" ;;
esac
echo "dpkg-segv-wrapper: 吸收 dpkg SIGSEGV（厂商缺陷），补跑 --configure --pending" >&2
"$REAL" --configure --pending
crc=$?
# 后置断言：不能有残留的 unpacked / half-* 状态
if grep -qE '^Status: install ok (unpacked|half-configured|half-installed)$' /var/lib/dpkg/status 2>/dev/null; then
  echo "dpkg-segv-wrapper: 补跑后仍有半配置状态，照实返回失败" >&2
  exit 139
fi
exit "$crc"
