# 从 ISO 为国产桌面操作系统构建分档容器镜像

> 基准日 **2026-08-30** ｜ 构建镜像 **9** 个（3 发行版 × 3 档位）｜ 构建路径 **3** 条 ｜ 能力矩阵 **711** 格 ｜ 验收断言 **365** 条 ｜ 变异用例 **12** 条 ｜ 厂商缺陷留档 **12** 条 ｜ 一手数据集 **5** 组 ｜ 图 **6** 张 ｜ 可复算表 **10** 张

## 1. 问题

一份编译好的软件要交付到客户的国产桌面系统上，交付前得先验证它在那个环境里跑不跑得起来。理想做法是拿一台装着目标系统的机器实跑，但机器数量和版本组合很快就不够用；退而求其次的做法是把目标系统做成容器镜像，让验证跑在 CI 里。

问题在于，能直接拿来用的镜像并不存在。厂商发布的是 ISO 安装介质，容器镜像要么没有，要么不是同一个东西。本项目要回答的是：能不能从桌面版 ISO 出发，自己构建出与真机高度一致的分档镜像，让它同时承担三类用途——验证编译产物能否运行、为需要现场编译的场景提供工具链、以及作为一个包管理可用的平台基座。

这里的"一致"有明确边界。容器共享宿主内核，所以内核态的东西（LSM、驱动、initramfs）一律不在一致性范围内；我们要的一致是用户态的一致：同一套 libc 与 libstdc++ 版本、同一套厂商补丁过的系统库、同一套软件源与包数据库、同一套 locale 与证书。这个边界决定了后面所有取舍。

## 2. 国产桌面 OS 的官方容器镜像现状

先确认一件事：这活儿有没有必要自己干。我们探测了 8 个候选镜像引用，6 个可以匿名拉取（表 [`t01`](derived/tables/t01_official_image_availability.csv)）。

![左：拉得到的官方镜像分别是什么产品线；右：桌面镜像存在性探测](figures/fig01_official_availability.png)

结论分两半。社区线是有镜像的：openKylin 在 Docker Hub 上有 `openkylin/openkylin`，2.0 与 latest（3.0）都能拉；deepin 有 `deepin/deepin-core` 与 `linuxdeepin/{beige,apricot}`。商业桌面线则完全没有：**麒麟桌面版的官方容器镜像 0 个，统信 UOS 的官方容器镜像 0 个**（`kylin_desktop_official_images=0`、`uos_official_images=0`，判据见表 [`t02`](derived/tables/t02_registry_existence_probes.csv)）。

### 2.1 麒麟"有官方镜像"是个误读：那是另一条产品线

`cr.kylinos.cn` 上确实有匿名可拉的官方镜像，容易让人以为麒麟桌面版的容器化问题已经解决。实测下来不是这么回事。

在 8 条存在性探测里，`cr.kylinos.cn` 上唯一拉得到的是 `kylin/kylin-server-minimal:v10sp1`；`kylin-desktop` 的 v10、v11、latest 三个 tag 全部不存在，`kylin-linux-desktop:v10` 不存在，连服务器线的 `kylin-server-minimal:v11` 也不存在。

而那个唯一拉得到的镜像，与桌面版不是一条产品线：

![麒麟官方镜像与桌面版的四维对照](figures/fig02_product_line.png)

| 维度 | `kylin-server-minimal:v10sp1`（厂商官方） | 本项目从桌面 ISO 构建 |
|---|---|---|
| `os-release` NAME | `Kylin Linux Advanced Server` | `Kylin` |
| `os-release` VERSION | `V10 (Tercel)` | `v10` / `v11` |
| 包格式 | **rpm**（217 个包） | **dpkg**（221 / 206 个包） |
| glibc | `2.28-36.1.p24.ky10` | `2.31-0kylin9.1k20.3` / `2.38-1ok6.9k0.5` |
| 软件源 | `update.cs2c.com.cn:8080`（中标软件血统） | `archive.kylinos.cn/kylin/KYLIN-ALL` |

包格式、glibc 大版本、软件源基础设施三样全不同。银河麒麟高级服务器操作系统是 RHEL 血统的 RPM 系统，银河麒麟桌面操作系统是 Ubuntu 血统的 Debian 系统，二者共用"麒麟"品牌但不共用任何一层。拿服务器镜像验证桌面交付，等于拿 CentOS 验证 Ubuntu。

误读的根源在一个具体的技术细节上：**两者 `os-release` 的 `ID` 字段都是 `kylin`**（`os_id_collision=True`）。按 `ID` 判断发行版是常见做法，各类工具链和 CI 脚本也大多这么做，而这个字段在这里恰好不具备区分力，得看 `NAME` 或包格式才能分辨。

需要说清楚强度边界：以上是对 8 条探测的观察，证明的是"匿名不可获得"，不能证明厂商内部或授权渠道没有桌面镜像。同一 org 的前序研究[`cn-desktop-os-buildchain-study`](https://github.com/hansbug-research/cn-desktop-os-buildchain-study) 结论 7 指出厂商 server 镜像可以作为对应桌面版的**ABI 预检代理**（因为同厂同版本的 server 镜像 ABI 地板不高于桌面版），这与本节结论不冲突：符号地板的单向预检，和用户态环境的一致复现，是两个不同强度的需求。前者只要地板够低就行，后者要求包格式、系统库、软件源都对得上。

## 3. 分档：为什么是 micro / base / devel

容器镜像分档不是我们的发明，主流做法有稳定的模式。Red Hat 的 UBI 分 `micro`（无包管理器）、`minimal`（`microdnf`）、`standard`（完整 `dnf`）、`init`（带 systemd）；Debian 官方镜像有完整版与 `slim`；Ubuntu 有 Chisel 切片；Wolfi/apko 走的是逐包声明式组装。共同的分档轴只有两条：**装不装包管理器**，以及**装不装工具链**。

我们按用途定了三档，每一档都对应一类真实需求：

| 档位 | 定位 | 典型用途 | 不该有什么 |
|---|---|---|---|
| `micro` | 纯运行时 | 把在别处编好的产物拷进来跑一跑，看依赖齐不齐 | 包管理器、编译器、运维工具 |
| `base` | 平台可用 | 装几个包补齐依赖再跑；线上排查 | 工具链 |
| `devel` | 构建用 | 现场编译，或复现客户报的编译问题 | —— |

档位定位直接决定了能力矩阵里"不适用"格的判据（见 §6）。这一点必须先说定，否则"micro 档没有 gcc"到底算缺口还是算设计，会变成一笔糊涂账。

九个镜像的规模落在下表（表 [`t04`](derived/tables/t04_built_images.csv)）。尺寸一律以 rootfs tar 的字节流为准——只有它既可复现又有 sha256 锚点；`docker images` 显示的是解包后按块占用，两个口径差三到四成，不能混用。

![三档镜像的体积与包数](figures/fig04_tier_size.png)

## 4. 三条构建路径

从 ISO 到镜像，教科书做法是 `mmdebstrap` 或 `debootstrap` 拉起一个 chroot。三个被试里只有一个能这么走，另外两个各自撞上不同的墙，最后形成三条路径（表 [`t09`](derived/tables/t09_build_paths.csv)）。

### 4.1 mmdebstrap：银河麒麟桌面 V11

V11 的在线源可以直接 bootstrap，但起步就卡住：chroot 里没有 `/bin/sh`，所有 `#!/bin/sh` 的 preinst 全部 ENOENT。根因是 V11 的 `base-files` 把 `./bin`、`./lib`、`./sbin` 作为真实目录发出，而包内容已经 usr-merge 了。用 `mmdebstrap --hook-dir=/usr/share/mmdebstrap/hooks/merged-usr` 补上符号链接即可（缺陷 D01）。

### 4.2 selfhost 自举：银河麒麟桌面 V10 SP1

V10 上 `mmdebstrap` 不可用，两道墙叠在一起：apt 解析 essential 集时报 debconf 依赖环；就算绕过，宿主 Debian 13 的 dpkg 1.22 会往 status 里写 `Conffiles: ... newconffile` 标记，而 V10 自带的 dpkg 1.19.7 解析不了（缺陷 D07）。更麻烦的是 V10 把 `bash` 的 preinst 编译成了 ELF 二进制，需要 libc 先就位才能执行（缺陷 D06）。

解法是两阶段自举：`debootstrap --foreign` 只解包不跑脚本，导入容器后用**麒麟自己的 dpkg 1.19.7** 完成 `--second-stage`。这是发行版工具链代差的标准解法，代价是产物不逐位可复现（见 §8）。

### 4.3 slice 切片：统信 UOS V25

UOS V25 是 OSTree 不可变系统，`apt` 和 `dpkg` 被 `deepin-immutable-ctl` 接管，在线源也不承担 OS 分发。这条路径不做 bootstrap，而是直接从 ISO 的 squashfs 里按包依赖闭包切片：以一组种子包为起点解析依赖，把闭包内的文件、`dpkg` 元数据、`update-alternatives` 记录一并搬出来。

切片路径踩的坑最深，两条值得单列：`info/format`（内容为 `1`）决定了 `Multi-Arch: same` 的包用 `pkg:arch.list` 命名，漏拷这一个文件会让 dpkg 对一大片包报 "missing the list control file"（缺陷 D10）；`dpkg` 的 admindir 在 UOS 上被搬到了 `/usr/lib/dpkg/var`，而 SBOM 扫描器从镜像层 tar 里找 `/var/lib/dpkg/status` 且**不跨归档跟随符号链接**，放符号链接会让扫描结果静默变成空的（缺陷 D09）。

## 5. 精简与容器化改造

三条路径共用一套容器化改造（`lib/common.sh::adapt_container`），改造项分两类。

一类是标准的容器精简：`policy-rc.d` 返回 101 阻止装包时起服务、apt 配置去掉缓存与翻译文件、`/usr/share/doc` 按 `path-exclude` + `path-include copyright` 只保留版权声明（GPL 要求）、清空 `machine-id`、删除 ssh host key 与 `resolv.conf`、去掉内核与固件。

另一类是桌面 ISO 特有的、必须改的语义。三个发行版的 `default.target` 都是 `graphical.target`——它们本来就是桌面系统，真机上这么设是对的，但 server 用途下会去拉 display-manager，而且一个 masked 单元都没有，容器里跑不了的单元（udev、内核挂载、audit socket、厂商 LSM 守护）会一路报错。改造把默认目标改为 `multi-user.target`，并 mask 掉 7 个确证不可用的单元（缺陷 D12）。

还有一类是补齐，理由是"缺了会让语义不自洽"。麒麟 V11 的 micro 档原本没有 `/etc/shadow` 和 `/etc/gshadow`，却带着 setuid 的 `su` 和 `newgrp`——setuid 二进制拿不到影子文件，既不可用又是白送的攻击面；九个镜像里只有它这样。补齐时最后改动日期用 `SOURCE_DATE_EPOCH` 折算而不是"今天"，否则可复现性当场报废。

### 5.1 加包要看真实代价

补齐运维工具时我们加过头，用实测数据纠正了回来。原本想给三档 base 补上 `dig`，以及给 UOS base 补上 `perl`（麒麟两版 base 都有，UOS 没有，属于跨发行版不对称）。实测代价：

| 加什么 | 体积变化 | 真因 |
|---|---|---|
| `bind9-dnsutils`（`dig`） | 麒麟 V11 base 345 MB → 407 MB | 拖 `bind9-libs` → **`libicu74`（36 MB）** |
| UOS base 的 `perl` | UOS base 274 MB → 420 MB | `libperl5.36`（29 MB）+ `perl-modules-5.36`（18 MB）+ `libicu74`（36 MB） |

一个 `dig` 要 40 到 60 MB，与"小镜像"的目标直接冲突，两项都回退了。基础 DNS 解析用 `getent hosts` 就够（矩阵里九个镜像全部支持）；真要 `dig`，麒麟两版一条 `apt install` 就有，UOS 装不上（原因见 §6.2）。保留下来的运维集是 `iproute2` / `iputils-ping` / `lsof` / `zstd` / `unzip` / `vim-tiny`，合计约 13 MB。

## 6. 能力矩阵：测什么、怎么测、测出什么

### 6.1 测法

能力不能按包列表推断——装了 gcc 不等于能编出可跑的二进制。探针（`test/capabilities.sh`）在每个镜像内**真跑**每一项：编译要真编译真执行，TLS 要真握手（连 `mirrors.aliyun.com:443` 并校验证书链），apt 要真装真卸（用带 maintainer script 的包，无脚本的包会掩盖厂商 dpkg 的问题），本地 `.deb` 直装要真造一个 deb 装上再卸掉。

79 项 × 9 个镜像 = 711 格，全部实测（`capability_items=79`、`capability_cells=711`）。探针最后一行输出 `probe_complete=Y` 哨兵，采集脚本硬断言它——探针中途挂掉时缺失的 key 会被读成空值而不是失败，这类静默截断本项目踩过（见 §9.2）。

三态判据写死在 `scripts/analyze.py` 的 `NA_POLICY` 里，是矩阵表和热力图的唯一真源（两处各写一份必然漂移）：

- **支持**：实测通过
- **不支持**：该档位确实存在这一需求却不满足，是缺口
- **不适用**：该档位定位下这一需求不存在（依据 §3 的档位定位，不拿它掩盖缺口）

711 格的分布是支持 400、不支持 102、不适用 209。

![能力矩阵热力图](figures/fig03_capability_matrix.png)

### 6.2 结果

**基础运行时零缺口。** shell、coreutils、`getent`、影子文件、`zh_CN.UTF-8` locale、时区、CA 根证书、DNS 解析、TLS 真握手、`nsswitch.conf`、`/tmp` 与 `/var` 可写、信号 trap——九个镜像全部通过。这一层是"能不能跑起来"的地基，也是本项目的首要用途所在。

**编译能力：C 三家齐备，C++ 缺一家。** 三个 devel 档 C 全部真编真跑通过（`devel_c_ok=3`），C++ 只有两家（`devel_cxx_ok=2`）。缺的是 UOS V25——它的 ISO 里没有 g++。麒麟 V10 的 GCC 9 不支持 `-std=c++20`（`c++17` 可用）。

**麒麟 V11 的 gcc 会污染 stderr。** 每次编译往 stderr 吐 `grep: /CurrentlyBuilding: No such file or directory`，编译本身成功。这是厂商包装脚本的缺陷（D05），我们没改——改厂商脚本就越过了"等价环境"的底线。影响是：在这个镜像里判断编译是否失败，必须用退出码，不能用 stderr 非空。

**包管理：UOS 装不了 OS 包，但那是产品设计不是缺陷。** 麒麟两版 base/devel 的 `apt update` / `install` / `purge` 往返全部通过。UOS 的 `apt` 二进制在、源可达、`apt check` 干净，但装不了 OS 包——它的 apt 源里 4731 个包名全是应用商店的 GUI 应用，连 `nano` 都没有，OS 分发走 OSTree 加玲珑。

UOS 还有一个真缺陷已修：`sources.list.d` 里有两个需订阅授权的专业源（`professional-security.chinauos.com`、`pro-driver-packages.uniontech.com`），未授权返回 401，会让整个 `apt-get update` 退出非零，哪怕 appstore 源本身是通的。镜像里带一个必然失败的源清单没有意义，现在默认注释掉并留了重新启用说明（缺陷 D08）。

### 6.3 一个必须讲清的区别：麒麟的"没预装"与 UOS 的"硬缺口"

矩阵里 `cmake`、`autoconf/automake`、`git`、`strace`、`gdb`、`python3-dev`、`dig` 在三家的 devel 或 base 档都标着不支持，但性质完全不同。我们逐个测了这 14 个工具在各自软件源里的可装性：

| | 麒麟 V11 | 麒麟 V10 | UOS V25 |
|---|---|---|---|
| 源里可 `apt install` | **14 / 14** | **14 / 14** | **0 / 14** |

麒麟两版是"没预装"，一条命令就有，不预装是档位设计（保持 server 小镜像）。UOS 是"装不上"：它没有 apt 形式的 OS 软件源，能力面由 ISO 内容封顶。

我们进一步查了 UOS ISO（1636 个包）里到底有什么：`ip`、`lsof`、`zstd`、`unzip`、`perl`、`dig`、`curl` 在里面（前四个原先没切进来，已补进 base）；`g++`、`cmake`、`git`、`strace`、`gdb`、`autoconf`、`ping`、`vi`、python3 开发头文件**不在里面**。

由此得到一条对使用方直接有影响的结论：**UOS V25 镜像不能作为 C++ 构建环境**——没有 g++ 且装不上。需要在 UOS 上产出 C++ 制品时，只能自行 vendor 工具链，或者用麒麟镜像构建、UOS 镜像只做运行时验证。

## 7. 验收：五道门禁与变异测试

九个镜像要能拿出去用，得先证明它们是对的。五道门禁各自防不同一类事故（表 [`t07`](derived/tables/t07_gates.csv)）。

| 门禁 | 结果 | 防的是什么 |
|---|---|---|
| `verify` | **365 通过 / 0 失败**（基线 360） | 逐镜像的结构、完整性、基线对账、能力、ABI gate、元数据 |
| `digest-chain` | **9 / 9** | manifest 记的 sha256 = `out/*.tar` 实际字节 = 本地镜像，三者脱钩 |
| `sbom` | **9 / 9** | SBOM 静默失效（扫出来是空的却报成功） |
| `mutation` | **12 抓到 / 0 漏** | 检查集本身失效（"检查永远为真"的假通过） |
| `repro` | **6 / 6 逐位一致** | 构建不可复现 |

![五道门禁与能力矩阵格分布](figures/fig05_gates.png)

`digest-chain` 的最后一环需要说明：`docker import` 会把 tar 重新归一化，layer 的 `diff_id` 与源 tar 的 sha256 天然不同，所以不能直接比哈希。但归一化是确定的，把同一个 tar 再导一次比 `diff_id` 是等价且严格的做法。

变异测试是这套门禁里最不像"测试"的一环，也是最关键的一环：它故意破坏镜像，确认检查集**真的会失败**。12 个用例覆盖删 `nsswitch.conf`、植入 ssh host key、删 CA 证书、删 `zh_CN` locale、把 `/var/lib/dpkg/status` 换成断链、删 copyright（全部与单包两种）、删 `policy-rc.d`、植入依赖缺失的 `.so`、改时区、往 `machine-id` 写内容、植入清单外悬空软链。全部被抓到。

它值得单列，是因为本项目真的靠它发现了三次假通过（见 §9.2）。

## 8. 可复现性

`mmdebstrap` 与 `slice` 两条路径逐位可复现：同一 builder 内连构两次，六个产物 sha256 完全一致（`repro_identical=6`，凭据在 [`out/repro-evidence.txt`](artifacts/repro-evidence.txt)）。做到这一点靠三件事：`SOURCE_DATE_EPOCH` 取自仓库 `Release` 的 `Date` 且由 `lib/common.sh::derive_epoch` 在构建与本地源两处共用（两边各算一次会让哈希漂，实际踩过）；`tar --sort=name --mtime=@epoch --numeric-owner`；以及把 SONAME 修复的候选限定为真实文件而非符号链接，避免选取顺序依赖目录遍历。

`selfhost` 路径（麒麟 V10）**不逐位可复现**：它用 `docker export | docker import` 产出镜像，容器层的时间戳与 layer id 每次不同。包集与版本仍然可复现，凭据在九份 manifest 里（`manifests=9`，记录了每个包的精确版本、tarball sha256、`SOURCE_DATE_EPOCH` 与 `InRelease` sha256）。

换一台 Linux 机器复现的完整路径写在 [`README.md`](README.md#复现) 里。前提是能访问三个发行版的官方软件源，以及持有 UOS 的 ISO（切片路径需要 squashfs，仓库不含 ISO 与镜像）。

## 9. 局限与过程记录

### 9.1 局限

- **仅 amd64。** 三条路径都只在 x86_64 上执行过，arm64 与 loongarch64 未验证。
- **不覆盖内核态。** 容器共享宿主内核，厂商的 KYSEC、IMA/EVM 完整性度量、驱动都不在一致性范围内。麒麟的 `kysec2-package-plugins` 我们是直接不装的（见 D02）。
- **UOS 的 `security.*` 扩展属性未保留。** rootless docker 无 `CAP_SYS_ADMIN`，`unsquashfs -xattrs` 会 FATAL。其中 IMA/EVM 那部分丢了没有实际影响（容器不加载相关 LSM），但 `security.capability`（file capabilities）在容器里是真会用的——如果业务二进制依赖 file capability 才能跑，在 UOS 三档里会表现成权限不足。
- **漏洞跟踪没有做。** 通用扫描器对这三个发行版没有有效覆盖：麒麟 V11 被 trivy 判为 `none` 压根没扫，麒麟 V10 与 UOS 被**误判成 Debian**，拿厂商改过的版本号去比 Debian 的公告区间，比不出来就报 0。一个 161 个包的镜像报 0 个 HIGH/CRITICAL 是不可信的——那是"比不出来"，不是"没有漏洞"。`make cve` 因此强制区分这两种情况，把无有效覆盖的镜像明确标出、不计入通过。真实的漏洞跟踪需要接厂商安全公告（麒麟 KYSA、UOS 安全通告）比对包版本，不在本仓库范围内。
- **"官方"一词受限使用。** 只有能给出 registry 域名归属证据的才称官方。Docker Hub 上的 `kylin` 命名空间是无关第三方（内容是 Home Assistant 插件），不是厂商。

### 9.2 被推翻的判断与踩过的坑

这些留在文档里是可靠性的凭据，不是瑕疵。

**dpkg 段错误的三次误判。** 麒麟 V11 上 `apt install` 带 maintainer script 的包会让 dpkg 段错误，包数据库永久报废。我先后归因于 `libchkuid` 的 ldconfig 警告、`force-unsafe-io`、以及 `libdb5.3` 的 t64 迁移窗口，三次都错。其中第二次尤其值得记：我做了一个 A/B 对照并"确认"了结论，但对照组的包已经被实验组解包过——**受控实验里的状态污染**。真根因是 `kysec2-package-plugins` 往 `/var/lib/dpkg/plugins/` 装了两个依赖内核态 KYSEC LSM 的 `.so`，而麒麟给 dpkg 打了补丁去 dlopen 它们（D02）。不装那个包就干净根治，base 档还小了 36 MB。

**检查框架自己会假通过。** 三处：其一，我在 `verify.sh` 里用了未定义的 `pass`/`fail` 函数，`[ 条件 ] && pass ... || fail ...` 的**两条分支都返回"命令未找到"**，四项新检查全程空转而汇总照样全绿；补上函数定义的当次运行就抓出一个本来会发出去的真缺陷（麒麟 V10 三档的 `default.target` 是悬空软链——V10 不做 usr-merge，单元在 `/lib/systemd/system`，而我的守卫两处都判了却把软链目标写死成 `/usr/lib/...`）。其二，检查脚本会在坏镜像上挂死，外层只拿到截断输出，而缺失的 key 被读成空值而不是失败；现在凡是碰 dpkg/apt 的地方一律套超时，并在最后一行输出 `checks_complete` 哨兵由 verify 硬断言。其三，`gate_high` 的负向断言原先只判"输出不等于 `ok 14`"，可二进制不存在、exec 格式错、缺任意别的库都满足这条，等于永真；现在必须核对失败原因确实是 `GLIBC_2.34 not found`。

**`elf_broken` 检查的两次错。** 第一次是 `xargs sh -c '... "$0"' _` 里 `$0` 是占位符 `_`、文件名在 `$1`，于是这项检查恒为 0；改对后立刻报出真实发现。第二次是误报：systemd 的私有库目录里 `libsystemd-core-255.so` 依赖同目录的 `libsystemd-shared-255.so`，但该目录不在 `ld.so.conf` 且无 RPATH，靠调用方二进制的 RUNPATH 覆盖，单独 `ldd` 必报 not found；现在把文件自身目录加进搜索路径再判。

**`shutil.copy2` 丢 uid/gid。** 切片脚本用 `copy2` 拷文件，它不保留属主，于是 `chage`、`unix_chkpwd` 从 setgid shadow 变成了 **setgid root**——一个真实的提权面。修法是显式 `os.chown` + `os.chmod`。

**门禁不能与构建并发跑。** 有一轮 `tar_mtab` 报失败，查下来是 verify 正在读 `out/kylin11-base.tar` 时我同时启动了重建覆写同一文件。这是我自己造的假失败，现在门禁严格串行。

**采集脚本里的 shell 引用坑。** D2 采集用 `json.dumps` 包 shell 参数（双引号），`${Version}` 被**宿主 shell** 展开成空串，采出来的 glibc 字段静默变成空值。改用 `shlex.quote`（单引号）。同类的还有一个：存在性探测最初用字符串匹配判断 `docker pull` 是否成功，而报错信息里同样含镜像引用，把"不存在"判成了"存在"；改用退出码。

**加包加过头。** 见 §5.1，用实测体积数据回退了两项。

## 附录 A：图目录

| 图 | 内容 |
|---|---|
| [`fig01`](figures/fig01_official_availability.png) | 官方容器镜像可获得性与桌面镜像存在性探测 |
| [`fig02`](figures/fig02_product_line.png) | 麒麟官方镜像与桌面版的产品线对照 |
| [`fig03`](figures/fig03_capability_matrix.png) | 能力矩阵热力图（711 格） |
| [`fig04`](figures/fig04_tier_size.png) | 三档镜像的体积与包数 |
| [`fig05`](figures/fig05_gates.png) | 五道门禁与能力矩阵格分布 |
| [`fig06`](figures/fig06_defects.png) | 厂商缺陷分布 |

## 附录 B：表目录

| 表 | 内容 |
|---|---|
| [`t01`](derived/tables/t01_official_image_availability.csv) | 官方容器镜像可获得性 |
| [`t02`](derived/tables/t02_registry_existence_probes.csv) | registry 存在性探测 |
| [`t03`](derived/tables/t03_product_line_comparison.csv) | 产品线对照 |
| [`t04`](derived/tables/t04_built_images.csv) | 九个镜像的构建产物事实 |
| [`t05`](derived/tables/t05_capability_matrix.csv) | 能力矩阵（三态） |
| [`t05b`](derived/tables/t05b_capability_raw.csv) | 能力矩阵（探针原始值） |
| [`t06`](derived/tables/t06_build_capability.csv) | 编译能力明细 |
| [`t07`](derived/tables/t07_gates.csv) | 五道门禁结果 |
| [`t08`](derived/tables/t08_vendor_defects.csv) | 厂商缺陷清单 |
| [`t09`](derived/tables/t09_build_paths.csv) | 三条构建路径 |
