#!/bin/bash
# 从已有镜像派生更高档位。用法: derive.sh <base-image> <out-image> <"pkgs"> [pre-pkgs]
set -eu
ROOT="${ROOT:-/data/dosbuild}"
BASE=$1; OUT=$2; PKGS=$3; PRE=${4:-}
C="derive-$$"
docker rm -f "$C" >/dev/null 2>&1 || true
docker run -d --name "$C" --privileged --init \
  -e DEBIAN_FRONTEND=noninteractive -e http_proxy= -e https_proxy= -e HTTP_PROXY= -e HTTPS_PROXY= \
  -e PKGS="$PKGS" -e PRE_PKGS="$PRE" \
  -v "$ROOT/build/derive-inner.sh:/derive-inner.sh:ro" \
  "$BASE" sleep infinity >/dev/null
if docker exec "$C" /bin/bash /derive-inner.sh; then
  docker export "$C" | docker import -c 'CMD ["/bin/bash"]' -c 'ENV LANG=C.UTF-8' - "$OUT" >/dev/null
  docker rm -f "$C" >/dev/null 2>&1 || true
  echo "  派生 $OUT -> $(docker images "$OUT" --format '{{.Size}}')"
else
  docker rm -f "$C" >/dev/null 2>&1 || true
  echo "  !! 派生 $OUT 失败" >&2; exit 1
fi
