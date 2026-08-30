# 国产桌面 OS 容器镜像构建 —— 统一入口
ROOT    := $(shell pwd)
BUILDER := dosb
DISTROS := $(patsubst distros/%.conf,%,$(wildcard distros/*.conf))
TIERS   := micro base devel
DEXEC   := docker exec -e http_proxy= -e https_proxy= $(BUILDER) bash -c

.PHONY: digest-chain cve repro help all builder builder-image localrepo kylin11 kylin10 uos25 import manifest verify sbom mutation clean-tags distclean
# 这台机器有过资源耗尽历史；并行构建会抢同一个 builder 容器与 out/ 目录
.NOTPARALLEL:

help:
	@echo "make builder     — 起 builder 容器（debian:13 + mmdebstrap/debootstrap）"
	@echo "make localrepo   — 造本地源（重打包厂商坏包 + 容器假包）"
	@echo "make kylin11     — 构建银河麒麟桌面 V11 三档"
	@echo "make kylin10     — 构建银河麒麟桌面 V10 SP1 三档（自举路径）"
	@echo "make uos25       — 构建统信 UOS V25 三档（切片路径，自动校验 squashfs 指纹）"
	@echo "make import      — 全部导入 docker 并打 LABEL"
	@echo "make manifest    — 生成产物清单（审计用）"
	@echo "make builder-image — 从 Dockerfile.builder 构建 builder 镜像"
	@echo "make verify      — 全量验收（动态计数，当前约 380 项，含总数基线断言）"
	@echo "make sbom        — SBOM 可生成性门禁"
	@echo "make mutation    — 变异测试：确认检查集真的会失败"
	@echo "make digest-chain — 摘要链：manifest = tar = 镜像 三者对账"
	@echo "make cve         — CVE 扫描（注意：trivy 无国产发行版漏洞库，见 README §8）"
	@echo "make repro       — 连构两次比对 sha256，写 out/repro-evidence.txt"
	@echo "make all         — localrepo + 三个发行版 + import + manifest + verify"

builder-image:
	docker build --build-arg http_proxy= --build-arg https_proxy= \
	  --build-arg HTTP_PROXY= --build-arg HTTPS_PROXY= \
	  -f Dockerfile.builder -t dosbuild-cache:latest .

builder:
	@docker image inspect dosbuild-cache:latest >/dev/null 2>&1 || $(MAKE) builder-image
	@docker inspect $(BUILDER) >/dev/null 2>&1 || \
	  docker run -d --name $(BUILDER) --privileged --init -v $(ROOT):/w \
	    -e DEBIAN_FRONTEND=noninteractive -e http_proxy= -e https_proxy= \
	    dosbuild-cache:latest sleep infinity
	@docker start $(BUILDER) >/dev/null 2>&1 || true

localrepo: builder
	@$(DEXEC) 'umask 022; ROOT=/w /w/tools/mk-localrepo.sh kylin11'
	@$(DEXEC) 'umask 022; ROOT=/w /w/tools/mk-localrepo.sh kylin10'

kylin11: builder
	@$(DEXEC) 'umask 022; ROOT=/w /w/build/build.sh kylin11 $(TIERS)'
uos25-src: builder
	@$(DEXEC) 'umask 022; ROOT=/w /w/tools/prepare-slice-src.sh uos25'

uos25: builder uos25-src
	@$(DEXEC) 'umask 022; ROOT=/w /w/build/build.sh uos25 $(TIERS)'
kylin10: builder
	@ROOT_HOST=$(ROOT) ./build/build-selfhost.sh $(TIERS)

import:
	@for d in $(DISTROS); do \
	  for t in $(TIERS); do \
	    [ -f out/$$d-$$t.tar ] && ROOT=$(ROOT) ./build/import.sh $$d $$t || true; \
	  done; done

manifest:
	@set -e; for d in $(DISTROS); do for t in $(TIERS); do ROOT=$(ROOT) ./tools/gen-manifest.sh $$d $$t; done; done

cve:
	@ROOT=$(ROOT) ./test/cve.sh

repro:
	@ROOT=$(ROOT) ./test/repro.sh

digest-chain:
	@ROOT=$(ROOT) ./test/digest-chain.sh

mutation:
	@ROOT=$(ROOT) ./test/mutation.sh

sbom:
	@ROOT=$(ROOT) ./test/sbom.sh

verify:
	@ROOT=$(ROOT) ./test/verify.sh

all: localrepo kylin11 uos25 kylin10 import manifest verify sbom

clean-tags:
	@for i in kylin-desktop-v11 kylin-desktop-v10 uos-desktop-v25; do \
	  for t in minimal platform init _stage; do docker rmi $$i:$$t 2>/dev/null || true; done; done

distclean: clean-tags
	@rm -rf build/kylin1*-* build/uos25-* out/*.tar out/*.manifest
