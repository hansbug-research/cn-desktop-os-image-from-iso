# 从 ISO 为国产桌面操作系统构建分档容器镜像

> 基准日 **2026-08-30** ｜ 国产桌面 OS 名录 **21** 个（商业 12 / 社区开源 9）｜ 构建镜像 **15** 个（5 发行版 × 3 档位）｜ 构建路径 **4** 条 ｜ 能力矩阵 **1080** 格逐格判定（支持 653 格、缺口 97 格、不适用 330 格）｜ 验收断言 **652** 条 ｜ 变异用例 **13**（镜像层）+ **15**（分析层）条 ｜ 机器核对断言 **566** 条（`python3 scripts/verify.py`）｜ 厂商缺陷留档 **20** 条 ｜ 一手数据集 **8** 组 ｜ 图 **6** 张（含机器无关的数据侧车 `figures/plotdata.json`）｜ 可复算表 **18** 张 ｜ 参考来源 **125** 条（GitHub 脚注，逐格 cite）

要把编译好的软件交付到客户的银河麒麟或统信 UOS 桌面上，交付前得先在那个环境里验一遍。厂商发的是 ISO，容器镜像要么没有、要么不是同一个东西。本仓库把「从桌面版 ISO 自己造分档镜像」这件事做通并留下完整证据：四条构建路径、15 个镜像、1080 格逐格判定的能力矩阵、五道验收门禁。

**完整报告：[`report.md`](report.md)**

![左：拉得到的官方镜像分别是什么产品线；右：桌面镜像存在性探测](figures/fig01_official_availability.png)

---

## 1. 主要结论

| # | 结论 | 证据 |
|---|---|---|
| 1 | **麒麟「有官方容器镜像」是个误读。** `cr.kylinos.cn` 上匿名可拉的唯一镜像是 `kylin-server-minimal:v10sp1`，它是 **rpm** 包格式、glibc `2.28-36.1.p24.ky10`、软件源在 `update.cs2c.com.cn`；而桌面 V10/V11 是 **dpkg**、glibc `2.31-0kylin9.1k20.3` / `2.38-1ok6.9k0.5`、源在 `archive.kylinos.cn`。包格式、glibc、软件源三样全不同 | [§2.3](report.md#23-麒麟有官方镜像是个误读那是另一条产品线)、`fig02`、[`t03`](derived/tables/t03_product_line_comparison.csv) |
| 2 | **误读的技术根源是一个字段：两者 `os-release` 的 `ID` 都是 `kylin`。** 按 `ID` 判发行版是常见做法，而这个字段在这里不具备区分力，得看 `NAME` 或包格式 | [§2.3](report.md#23-麒麟有官方镜像是个误读那是另一条产品线)、`os_id_collision=True` |
| 3 | **国产桌面 OS 里没有一个有桌面版官方容器镜像。** 名录 21 个 OS（商业 12 / 社区开源 9）、42 个候选引用实测 18 个存在，但带 `desktop`/`ukui`/`dde` 字样的 **13 条跨 5 家 registry 一条都不存在**。更强的一格：直接枚举厂商自己的 registry——`cr.kylinos.cn` 的 `kylin` 项目 27 个仓库全列出、含 desktop 或 ukui 的 **0 个**；`registry.uniontech.com` **18 个公开项目、0 个桌面相关**，基础镜像项目名就叫 `uos-server-base`。唯一例外是 openEuler DevStation 的 1.92 GiB rootfs，而它不在任何 registry、只有一个版本 | [§2](report.md#2-国产桌面-os-的分布与官方容器镜像现状)、[`t02`](derived/tables/t02_registry_existence_probes.csv) |
| 4 | **一条 ISO 一条路。** 五个被试没有一条通用路径，形成四条：V11 走 `mmdebstrap`；V10 因 debconf 依赖环 + 宿主 dpkg 1.22 与目标 1.19.7 的代差只能两阶段自举；UOS V25 是 OSTree 不可变系统只能从 squashfs 按包依赖闭包切片；麒麟信安是 rpm 系，解析介质 `repodata` 求闭包再 `rpm --root`；凝思与 V10 撞同一堵墙但表现更靠前——`mmdebstrap` 直接死锁而不报错，最后共用两阶段自举 | [§4](report.md#4-四条构建路径)、[`t09`](derived/tables/t09_build_paths.csv) |
| 5 | **UOS V25 不能作为 C++ 构建环境。** 它的 ISO（1636 个包）里没有 g++，而它没有 apt 形式的 OS 软件源（源索引只有 2500 个条目、全来自应用商店，连 `nano` 都查不到候选），所以装不上。五个 devel 档 C 全通过，C++ 是四家——UOS 是唯一的例外 | [§6.3](report.md#63-一个必须讲清的区别麒麟的没预装与-uos-的硬缺口) |
| 6 | **同一个「装不上」有三种成因，不能合并。** 14 个常见工具的源内可装性：麒麟 V11 **14 / 14**、麒麟 V10 **14 / 14**、UOS V25 **0 / 14**、麒麟信安 **14 / 14**、凝思 **0 / 14**。麒麟两版与麒麟信安都是「没预装」（一条命令就有，且跨包格式同样成立）；UOS 是「源里没有 OS 包」（源通、`apt check` 干净，但 OS 分发走 OSTree 与玲珑）；凝思是「根本没有源」（厂商未提供公开在线仓库）。两个 0 含义相反：UOS 换源也装不到，凝思拿到内部源就能装 | [§6.3](report.md#63-一个必须讲清的区别麒麟的没预装与-uos-的硬缺口) |
| 6b | **这套做法跨得过包格式，但探针跨不过——尺子必须先中立化。** 加入 rpm 系被试后，分档轴、五道门禁与变异测试直接复用；能力探针原先写死 dpkg，量 rpm 系会在「包数据库可查」「包管理器存在」「本地包直装」三行一片不支持，而那量的是尺子不是被试。改为按包管理系分支后，五格「不支持」里没有一格是发行版缺陷——两格来自我的构建（rpm 数据库后端是 ndb、`--noscripts` 跳过 CA 的 `%post`），三格来自命名差异 | [§6.1](report.md#61-测法)、缺陷 D13/D14 |
| 7 | **dpkg 段错误的真根因是厂商的安全插件，不是 IO 选项。** 麒麟 V11 的 `kysec2-package-plugins` 往 `/var/lib/dpkg/plugins/` 装两个依赖内核态 KYSEC LSM 的 `.so`，而麒麟给 dpkg 打了补丁去 dlopen 它们。此前三次归因均错，其中一次是受控实验里的状态污染 | [§9.2](report.md#92-被推翻的判断与踩过的坑)、缺陷 D02 |
| 8 | **ISO 可得性不是商业与社区的分界线，而且我们最初判反了。** 21 个 OS 逐个直连实测：**直接下载 15 家**（含凝思 7138705408 B、openKylin 8068329472 B、麒麟信安 4508876800 B、中标麒麟 3482347520 B、统信 UOS 7282405376 B）、需申请授权 **0 家**。这一列的判定推翻过一整轮，四类误判来源：代理把大陆主机打成 000、目录索引 401 被当成文件受限、ISO 仓库路径找错（`openkylin/` 是 apt 源，ISO 在 `openkylin-cdimage/`）、UI 看着像门槛但提取码明文写在页面里 | [§2.1](report.md#21-名录主要的国产桌面-os) |
| 9 | **加包要看真实代价。** 为补一个 `dig` 会经 `bind9-libs` 拖进 `libicu74`（36 MB），麒麟 V11 base 从 345 MB 涨到 407 MB；UOS base 补 `perl` 从约 281 MB 涨到 420 MB。两项都已回退。这四个数用 `docker images` 解包口径，与本仓库其余处的 rootfs tar 口径不同；只有起点 345 MB 有现存锚点，其余是回退前的一次性观察 | [§5.1](report.md#51-加包要看真实代价) |
| 10 | **检查框架自己会假通过，所以门禁本身也要被门禁。** 本项目实测到三类：helper 函数未定义导致两条分支都是「命令未找到」、检查脚本挂死导致输出截断而缺失 key 被读成空值、负向断言不核对失败原因等于永真 | [§9.2](report.md#92-被推翻的判断与踩过的坑) |
| 11 | **通用漏洞扫描器对这五家没有有效覆盖：15 个镜像有效覆盖 0 个。** trivy 0.70.0 扫全部 15 个镜像：麒麟 V11 与麒麟信安共 6 档判 `Family: none` 根本没扫；麒麟 V10、UOS、凝思共 9 档被**误判成 Debian**。前六档报 0 个 HIGH+CRITICAL（拿厂商改过的版本号比 Debian 公告区间，比不出来就报 0）；凝思三档是唯一非零的（`debian 10.6` + `EOSL`，165/418/831），但它的包版本号带 `linx`，同属误判。**「没有数据」与「没有漏洞」是两件事，「有数据」也不等于「数字可直接用」** | [§9.1](report.md#91-局限)、[`t13`](derived/tables/t13_cve_coverage.csv) |

> 五个被试怎么选出来的、这套做法对名录里其他 OS 的借鉴程度，见 [report §2.4](report.md#24-被试怎么选出来的以及这套做法对其他-os-意味着什么)；其余 OS 逐条套「已淘汰／官方已有满足需求的形态／ISO 拿不到」三条标准后的候选梯度见 [§2.5](report.md#25-候选梯度哪些还值得做哪些不必做)，TODO 见 [§2.6](report.md#26-后续-todo)——梯度里排最前的麒麟信安与凝思已在第二轮做完，Loongnix 仍待定。

## 2. 15 个镜像

| 发行版 | 构建路径 | micro | base | devel |
|---|---|---|---|---|
| 银河麒麟桌面 V11 | `mmdebstrap`| 88 MB / 71 包 | 248 MB / 206 包 | 498 MB / 255 包 |
| 银河麒麟桌面 V10 SP1 | `selfhost` 两阶段自举| 213 MB / 154 包 | 270 MB / 221 包 | 503 MB / 263 包 |
| 统信 UOS V25 | `slice` squashfs 切片| 98 MB / 67 包 | 191 MB / 164 包 | 448 MB / 208 包 |
| 麒麟信安桌面 V6 | `rpmmedia` 介质闭包 | 389 MB / 112 包 | 510 MB / 165 包 | 794 MB / 194 包 |
| 凝思安全操作系统 V6.0.100 | `selfhost` 两阶段自举 | 179 MB / 176 包 | 222 MB / 211 包 | 437 MB / 249 包 |

尺寸为 rootfs tar 的字节流（构建的直接产物，被 manifest 的 sha256 锚定）。`docker images` 显示的是解包后按块占用，比它大四成上下（15 个镜像实测 36.3%–48.6%，分母用 tar 精确字节、分子取 `docker images` 报的 MB），两个口径不能混用。

档位定位：`micro` 纯运行时（把别处编好的产物拷进来跑）、`base` 平台可用（有包管理、能排查）、`devel` 构建用（工具链齐备）。

![三档镜像的体积与包数](figures/fig04_tier_size.png)

## 3. 能力矩阵

72 项 × 15 镜像 = 1080 格，全部由镜像内探针逐格判定：编译要真编译真执行，TLS 要真握手，装卸往返要真装真卸。支持 653 格、缺口 97 格、不适用 330 格（其中 25 格是「前置条件不存在」：15 格是包管理三项（5 个 micro 档没有包管理器）、10 格是 `cc_clean_stderr`（micro 与 base 两档无编译器）；另有 4 格取值 `nosrc`——有包管理器但出厂无可用软件源，见 report §6.1）。判据按包管理系分支：同一项能力 deb 侧用 dpkg/apt 测、rpm 侧用 rpm/dnf 测。

![能力矩阵热力图](figures/fig03_capability_matrix.png)

三态判据（`scripts/analyze.py` 的 `NA_POLICY`）是矩阵表与热力图的唯一真源：**不适用**只在档位定位下确实不存在该需求时才用，不拿它掩盖缺口。

## 4. 验收

| 门禁 | 结果 | 防的是什么 |
|---|---|---|
| `make verify` | 652 通过 / 0 失败（基线 620） | 逐镜像结构、完整性、基线对账、能力、ABI gate、元数据 |
| `make digest-chain` | 15 / 15 | manifest 记的 sha256 与 tar、镜像三者脱钩 |
| `make sbom` | 15 / 15 | SBOM 静默失效（扫出来是空的却报成功） |
| `make mutation` | 13 抓到 / 0 漏 / 1 跳过 | 检查集本身失效（「检查永远为真」的假通过） |
| `make repro` | 9 / 9 逐位一致 | 构建不可复现 |

## 5. 复现

> 本地 `make verify` 只做镜像层验收，**不重新导出** `raw/d3_capabilities.json` 与 `raw/d4_gates.json`——这两份是从 `artifacts/` 里的探针输出与门禁日志导出的，改了日志而不重导不会有任何东西报警。CI（`.github/workflows/verify.yml`）会重导这两份并比对漂移，所以本地改完请一并跑 `python3 scripts/collect_d3_capabilities.py` 与 `collect_d4_gates.py`，或直接依赖 CI 兜住。

仓库不含镜像与 ISO（体积原因），但含完整构建链路。换一台 Linux 机器：

```bash
# 0) 前提：docker（rootless 亦可）、python3、能访问三个发行版的官方软件源。
#    UOS 走切片路径，需要它的 squashfs：默认由 tools/fetch-squashfs.py 用 HTTP Range
#    从 distros/uos25.conf 里的 ISO_URL 远程抽取（不下整个 ISO）；离线环境请自备 ISO
#    并把 squashfs 放到 conf 指定位置，其 sha256 必须与 SQUASHFS_SHA256 相符。
#    只重算分析与图表的话还需要：pip install -r requirements.txt，以及 CJK 字体
#    （Debian/Ubuntu：apt install fonts-noto-cjk），否则图上中文会变成方框。

# 1) 构建 builder 镜像（Debian 13 + mmdebstrap/debootstrap/squashfs-tools/gpgv）
make builder-image

# 2) 本地源：重打 libboundscheck（去掉误写成 Depends 的编译器依赖）+ 生成容器假包
make localrepo

# 3) 四条路径分别构建（各自的选择依据见 report.md §4）
make kylin11        # mmdebstrap
make kylin10        # selfhost 两阶段自举，跑在宿主上
make uos25          # slice；该目标已包含 uos25-src（在 builder 里备好切片源）
make kylinsec6      # rpmmedia：解析介质 repodata 求闭包 + rpm --root
make linx6          # selfhost；与 kylin10 同路径，但介质无签名（NO_CHECK_GPG）

# 4) 导入 docker 并打 LABEL / STOPSIGNAL
make import

# 5) 审计与验收
make manifest verify digest-chain sbom mutation mutation-docs
```

只重算分析与图表（不需要镜像，CI 走的就是这条）：

```bash
python3 scripts/analyze.py && python3 scripts/plot.py && python3 scripts/verify.py
```

重跑采集（需要全部 15 个镜像已在本地 docker 里）。采集脚本默认从仓库自身的 `out/` 读构建产物；产物在别处就用 `DOSBUILD_OUT` 指过去：

```bash
export DOSBUILD_OUT=/path/to/out          # 存放 *.tar / *.manifest / caps-*.txt 的目录
python3 scripts/collect_d1_official_images.py   # 需要访问 registry
python3 scripts/collect_d2_our_images.py
python3 scripts/collect_d3_capabilities.py      # 加 --run 可现场重跑探针
python3 scripts/collect_d4_gates.py
python3 scripts/collect_d5_iso_and_defects.py
python3 scripts/collect_d6_installability.py    # 需要全部镜像 + builder 容器
python3 scripts/collect_d7_cve.py               # 需要本地有 aquasec/trivy 镜像
python3 scripts/collect_d8_os_census.py         # 名录的镜像实测，需要访问各厂商 registry
```

六个在容器内跑的脚本（`lib/common.sh`、`build/{build,customize,setup}.sh`、`tools/{mk-localrepo,prepare-slice-src}.sh`）的 `ROOT` 默认是 `/w`（builder 里的挂载点），宿主侧直接单跑会找不到文件；宿主上跑的脚本 `ROOT` 默认取仓库根（由脚本自身位置推出），不需要按开发机路径改动。

## 6. 目录结构

```
report.md                     学术正文（问题 → 官方镜像现状 → 分档 → 四条构建路径 →
                              精简与改造 → 能力矩阵 → 验收 → 可复现性 → 局限与过程记录）
config/subjects.json          被试清单的唯一真源：5 个发行版 × 3 档位，采集/测试/分析脚本都从这里读
config/os_census.json         国产桌面 OS 名录（人工维护的文献部分，每条带 sources）
config/references.json        全局引用表（125 条，report 里每处 [^Rn] 指向它）
distros/                      五个发行版的构建参数：源、套件、期望 ABI 基线、档位包集、
  kylin11.conf                  以及每个厂商缺陷的绕法与理由
  kylin10.conf
  uos25.conf
  kylinsec6.conf                rpm 系，含 RPM_DB_BACKEND（目标 rpm 的数据库后端是 ndb）
  linx6.conf                    主线 deb 系，含 NO_CHECK_GPG（介质无签名，完整性锚点是 ISO 校验值）
build/                        构建入口
  build.sh                      mmdebstrap、slice、rpmmedia 三条路径
  build-selfhost.sh             两阶段自举（跑在宿主上），麒麟 V10 与凝思共用
  selfhost-inner.sh             自举第二阶段，在目标容器内用目标自己的 dpkg 完成
  customize.sh                  mmdebstrap 的 customize hook
  import.sh                     导入 docker 并打元数据
lib/common.sh                 各路径共用的容器化改造：policy-rc.d、apt 精简、
                              systemd 桌面语义改 server、影子文件补齐、时区、可复现打包
lib/subjects.sh               被试清单的 shell 侧读取入口（Python 侧是 scripts/_subjects.py）
tools/
  slice.py                      按包依赖闭包从 squashfs 切片（UOS 路径核心）
  rpmmedia.py                   解析介质 repodata 求 rpm 依赖闭包，再 rpm --root 装（麒麟信安路径核心）
  rpmslice.py                   给「介质自带预装 rootfs」的 rpm 系写的切片器，当前无被试使用
  restore-alternatives.py       补回 update-alternatives 符号链接（不属于任何包，切片必漏）
  mk-localrepo.sh               重打包 + 生成容器假包
  gen-manifest.sh               产物清单：精确包版本 + tarball/InRelease sha256 + epoch
  render-capabilities.py        把探针输出渲染成能力矩阵
test/
  verify.sh                     全量验收（365 项，含检查总数基线断言）
  inner-checks.sh               在被测镜像内运行的检查集，结尾有完成哨兵
  capabilities.sh               能力探针，全部真跑；按包管理系分支，同一项能力 deb 侧用 dpkg/apt 测、rpm 侧用 rpm/dnf 测
  run-capabilities.sh           把探针跑遍全部被试镜像，并挂载 fixtures
  fixtures/                     探针夹具：最小 noarch rpm，供 rpm 系测「本地包直装」（出处与 sha256 见其 README）
  mutation.sh                   变异测试（镜像层）：故意破坏镜像，确认检查集真的会失败
  mutation-docs.sh              变异测试（分析层）：改坏 stats/正文/凭据，确认 verify.py 真的会失败
  digest-chain.sh               manifest = tar = 镜像 三者对账
  sbom.sh / cve.sh / repro.sh   SBOM 门禁 / CVE（含覆盖度诚实性判据）/ 可复现性凭据
gate/                         ABI 门禁二进制与其构建记录（build-gates.sh）
keys/                         麒麟 archive GPG keyring（来源与指纹见 report.md）
raw/                          一手数据，采集脚本的原始输出逐字保存
  d1_official_images.json       官方镜像可获得性与存在性探测
  d2_our_images.json            全部自建镜像的事实 + 官方镜像产品线对照
  d3_capabilities.json          能力探针原始输出（每镜像约 86 个 key；三态矩阵取 72 项 = 1080 格，其余是环境指纹与哨兵）
  d4_gates.json                 五道门禁结果与九份 manifest 的审计锚点
  d5_iso_and_defects.json       各条路径的配置事实 + 20 条厂商缺陷与移植性陷阱
  d6_installability.json        14 个工具在各自源里的可装性、UOS 源规模与 ISO 包清单
  d7_cve.json                   漏洞扫描器对全部镜像的覆盖判定（四种失效形态，见 report §9.1）
  d8_os_census.json             国产桌面 OS 全名录（21 个）+ 官方镜像存在性实测（42 个引用）
derived/                      从 raw/ 重算，不手写
  stats.json                    正文引用的全部统计量
  tables/*.csv                  18 张可复算表（含 t14 国产桌面 OS 名录、t14b 名录完整原文、t15 镜像实测、t16 参考来源）
figures/*.png                 6 张图
figures/plotdata.json         每张图实际画进去的数值与文字（机器无关，CI 拿它防「图画着旧数据」）
artifacts/                    审计凭据：九份 manifest、可复现性凭据、九份探针原始输出、
                              四份门禁日志（f4-verify/digest/sbom/mutation.log，一手输出可核对）
scripts/                      collect_d*.py 只采集不判断；analyze.py 只读 raw 只写 derived；
                              plot.py 只读 derived；verify.py 机器核对正文里的每个声明
```

## 7. 相关工作

同 org 的 [`cn-desktop-os-buildchain-study`](https://github.com/hansbug-research/cn-desktop-os-buildchain-study) 研究的是「用哪个基座编、能落到哪些国产桌面上」的 ABI 选型，被试是既有镜像；本仓库研究的是「目标环境本身怎么造出来」。两者结论互补：前者结论 7 指出厂商 server 镜像可作为对应桌面版的 **ABI 预检代理**，本仓库 §2.3 指出它**不是**桌面版的等价环境——符号地板的单向预检与用户态环境的一致复现是两个不同强度的需求。

## 8. 许可

代码 MIT，文档与数据 CC BY 4.0。三个发行版的 ISO、软件包与 GPG keyring 版权归各厂商所有，本仓库不分发它们。
