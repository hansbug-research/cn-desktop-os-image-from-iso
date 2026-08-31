# 探针夹具

## capprobe-1.0-1.noarch.rpm

**用途**：测「本地包直装」这项能力。探针装上它、确认 `rpm -q` 查得到、再卸干净，全过程失败任一步即判不支持。

**为什么需要夹具**：deb 侧的探针在镜像内用 `dpkg-deb --build` 现造一个包，三档都能造。rpm 侧造包要 `rpmbuild`，只有 devel 档预置了 `rpm-build`，micro 与 base 造不出来。若因此把 micro/base 判成「不支持本地包直装」，量的就不是被试的能力而是探针的构造手段。所以由 `test/run-capabilities.sh` 把这个包只读挂进 `/probe-fixtures`，三档同一口径。包不写进镜像，只在测量期间存在。

**出处**：在 `kylinsec-desktop-v6:devel` 内用该镜像自带的 `rpmbuild` 构建，spec 见下。内容是一个 `/usr/share/capprobe/marker` 文件，无脚本、无依赖。

```spec
Name: capprobe
Version: 1.0
Release: 1
BuildArch: noarch
License: MIT
%install
mkdir -p %{buildroot}/usr/share/capprobe
echo probe > %{buildroot}/usr/share/capprobe/marker
%files
/usr/share/capprobe/marker
```

**sha256**：`de7b94ed5e8b8475ba639b6d9627459e548e76c08fc5301799391ea293321dfd`

**局限**：rpmbuild 会把构建时间写进包头，因此重新构建这个夹具不会逐位复现。它不参与镜像构建，不影响镜像本身的可复现性。
