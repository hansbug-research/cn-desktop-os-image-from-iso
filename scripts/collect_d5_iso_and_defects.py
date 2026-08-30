#!/usr/bin/env python3
"""D5：三个 ISO 的事实，与采集过程中确证的厂商缺陷清单。

缺陷清单的每一条都必须可机器核对或可复现观察，且要写明：现象、根因、影响面、
本项目的处理方式、以及处理方式落在哪个文件。只写「有个 bug」不算证据。
"""
import json, os, pathlib, re, subprocess, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
# 构建产物目录。默认是仓库自身的 out/（`make` 就写在那儿）；
# 若产物在别处，用 DOSBUILD_OUT 指过去。不要硬编码开发机路径 —— 换台机器就跑不了。
OUTDIR = pathlib.Path(os.environ.get("DOSBUILD_OUT") or (ROOT / "out"))
OUT = ROOT / "raw" / "d5_iso_and_defects.json"
SRC = OUTDIR.parent

def sh(c, timeout=120):
    p = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=timeout)
    return p.stdout.strip()

# 每条缺陷：id / 发行版 / 现象 / 根因 / 影响 / 处理 / 落点 / 可核对的判据
DEFECTS = [
 dict(id="D01", distro="kylin11", title="base-files 不提供 usr-merge 符号链接",
      symptom="chroot 里无 /bin/sh，所有 #!/bin/sh 的 preinst 直接 ENOENT",
      root_cause="V11 的 base-files 把 ./bin ./lib ./sbin 作为真实目录发出，而包内容已 usr-merge",
      impact="mmdebstrap 路径完全无法起步（S0 阻断）",
      fix="mmdebstrap --hook-dir=.../merged-usr", where="build/build.sh",
      check="镜像内 /bin 是指向 usr/bin 的符号链接"),
 dict(id="D02", distro="kylin11", title="kysec2-package-plugins 让容器内 dpkg 必段错误",
      symptom="apt install 带 maintainer script 的包后永久卡在 half-configured，dpkg --configure -a 反复 SIGSEGV",
      root_cause="该包往 /var/lib/dpkg/plugins/ 装 ksaf_label.so 与 spro.so，麒麟给 dpkg 打了补丁去 dlopen 它们；"
                 "这两个插件依赖内核态 KYSEC LSM，容器里没有",
      impact="一次 apt install 就让包数据库永久报废",
      fix="PIN_NEVER 不装该包（其全部内容就是那两个 .so，且无任何包依赖它）",
      where="distros/kylin11.conf", check="镜像内 /var/lib/dpkg/plugins 不存在或为空"),
 dict(id="D03", distro="kylin11", title="libboundscheck 把编译器写成运行时依赖",
      symptom="装一个运行时库要拖进整个 gcc/g++",
      root_cause="Depends 里写了 g++, gcc（应为 Build-Depends）",
      impact="每档白背约 200MB", fix="重打包去掉该依赖，版本加 +nogccdep1 后缀便于审计",
      where="tools/mk-localrepo.sh", check="localrepo 里存在 +nogccdep1 版本的 deb"),
 dict(id="D04", distro="kylin11", title="deb-host-gnu-type-secure 的 preinst 缺 Pre-Depends",
      symptom="devel 档构建失败", root_cause="preinst 调 dpkg-architecture 却未 Pre-Depends: dpkg-dev",
      impact="devel 档无法构建", fix="该包内容只有 /usr/share/doc，用 container-stub 提供 + apt pin 到 -1",
      where="distros/kylin11.conf", check="镜像内不存在该包，且 container-stub 提供同名虚包"),
 dict(id="D05", distro="kylin11", title="gcc/g++ 包装脚本污染 stderr",
      symptom="每次编译往 stderr 吐 grep: /CurrentlyBuilding: No such file or directory",
      root_cause="厂商包装脚本无条件 grep 一个不存在的文件",
      impact="编译本身成功，但会坑用 stderr 非空判错的 CI",
      fix="不动厂商脚本（属等价环境底线内），仅记录：判错请用退出码",
      where="report.md", check="devel 档编译一个 hello.c，stderr 非空但退出码为 0"),
 dict(id="D06", distro="kylin10", title="bash 的 preinst 是 ELF 二进制",
      symptom="解包顺序里 libc 未就位则 ENOENT",
      root_cause="厂商把 preinst 编译成了 ELF 而非脚本",
      impact="mmdebstrap 路径不可用", fix="debootstrap --foreign 两阶段，第二阶段在目标容器内用麒麟自己的 dpkg 完成",
      where="build/build-selfhost.sh", check="file 该 preinst 得到 ELF"),
 dict(id="D07", distro="kylin10", title="宿主 dpkg 1.22 写的状态标记，目标 dpkg 1.19.7 读不懂",
      symptom="后续所有 dpkg 操作失败",
      root_cause="宿主 Debian 13 的 dpkg 往 status 写 Conffiles: ... newconffile 标记",
      impact="发行版工具链代差导致 mmdebstrap 路径不可用",
      fix="同 D06，用目标自带 dpkg 完成 configure", where="build/build-selfhost.sh",
      check="目标镜像内 dpkg --version 为 1.19.7"),
 dict(id="D08", distro="uos25", title="OS 分发不走 apt，且两个授权源未授权返回 401",
      symptom="apt-get update 整体退出非零，哪怕 appstore 源本身是通的",
      root_cause="sources.list.d 里 professional-security.chinauos.com 与 pro-driver-packages.uniontech.com 需订阅授权",
      impact="镜像自带一个必然失败的源清单",
      fix="默认注释掉并留重新启用说明（凭据写 /etc/apt/auth.conf.d/）",
      where="lib/common.sh", check="apt-get update 退出码为 0"),
 dict(id="D09", distro="uos25", title="dpkg admindir 被搬到 /usr/lib/dpkg/var",
      symptom="SBOM 扫描器扫出来只有 2 个包",
      root_cause="trivy 从镜像层 tar 里找 /var/lib/dpkg/status，且不跨归档跟随符号链接",
      impact="SBOM 静默失效（看起来成功，内容是空的）",
      fix="把 admindir 归位到 /var/lib/dpkg，原路径做符号链接指回",
      where="build/build.sh", check="SBOM 包数 ≥ dpkg 自报包数"),
 dict(id="D10", distro="uos25", title="info/format 漏拷导致 Multi-Arch 包集体报错",
      symptom="对一大片包报 missing the list control file",
      root_cause="info/format（内容为 1）决定 Multi-Arch: same 的包用 pkg:arch.list 命名，漏拷则 dpkg 去找不带 arch 的名字",
      impact="切片出的 dpkg 数据库不自洽",
      fix="切片时一并拷 info/format 及 admindir 顶层元文件",
      where="tools/slice.py", check="dpkg --audit 输出 0 行且 dpkg -L 抽查有内容"),
 dict(id="D11", distro="共通", title="iproute2 的 tc ATM 插件缺库",
      symptom="ldd 报 libatm.so.1 => not found",
      root_cause="libatm1t64（V10 上是 libatm1）只是 Recommends，--no-install-recommends 构建就缺",
      impact="tc 的 ATM 队列不可用（容器场景无实际影响），但属真实悬空依赖",
      fix="显式装入该库（约 50KB）", where="distros/kylin11.conf, distros/kylin10.conf",
      check="elf_broken 计数为 0"),
 dict(id="D12", distro="共通", title="桌面 ISO 出身的 systemd 默认目标是 graphical.target",
      symptom="base/devel 档启动 systemd 会去拉 display-manager，且零个 masked 单元",
      root_cause="被试是桌面版 ISO，默认目标与真机一致",
      impact="server 用途下会拉起跑不了的单元并刷错误",
      fix="default.target 改指 multi-user.target，并 mask 掉容器内确证不可用的 7 个单元",
      where="lib/common.sh", check="default.target 指向 multi-user.target 且 masked 单元 ≥5"),
]

def main():
    data = {"collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "isos": [], "defects": DEFECTS}
    for conf in sorted((ROOT / "distros").glob("*.conf")):
        txt = conf.read_text()
        # 取值要剥掉行尾注释：conf 里写的是 METHOD=mmdebstrap  # 在线源可 bootstrap
        def g(k):
            m = re.search(rf'^{k}=(.*)$', txt, re.M)
            if not m: return None
            v = m.group(1).split('#', 1)[0].strip()
            return v.strip('"').strip("'") or None
        data["isos"].append({
            "distro_id": conf.stem, "method": g("METHOD"), "suite": g("SUITE"),
            "mirror": g("MIRROR"), "expect_glibc": g("EXPECT_GLIBC"),
            "expect_libstdcpp": g("EXPECT_LIBSTDCPP"), "expect_glibcxx": g("EXPECT_GLIBCXX"),
            "squashfs_sha256": g("SQUASHFS_SHA256"), "source_date_epoch": g("SOURCE_DATE_EPOCH"),
            "usrmerge": g("USRMERGE"), "immutable": g("IMMUTABLE"), "admindir": g("ADMINDIR"),
        })
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(f"写入 {OUT}（{len(data['isos'])} 个发行版配置 + {len(DEFECTS)} 条厂商缺陷）")

if __name__ == "__main__":
    main()
