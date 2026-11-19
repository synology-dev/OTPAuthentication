#!/usr/bin/env bash
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
cd "$ROOT"

VERSION="${VERSION:-1.0.0-001}"
TARGET="${TARGET:-x86_64}"
DIST="${ROOT}/dist"
STAGE="${DIST}/stage-${TARGET}"
PKG_INNER="${STAGE}/package"
SPK_DIR="${STAGE}/spk"

rm -rf "${STAGE}"
mkdir -p "${PKG_INNER}" "${SPK_DIR}/scripts" "${DIST}"

# Fetch/ensure deps for target
python3 "${ROOT}/build/fetch_deps.py" --target "${TARGET}" --dest "${ROOT}/package/deps"

# Copy package payload (deps limited to the build target)
mkdir -p "${PKG_INNER}"
rsync -a --exclude 'deps' "${ROOT}/package/" "${PKG_INNER}/"
mkdir -p "${PKG_INNER}/deps/${TARGET}"
if [ -d "${ROOT}/package/deps/${TARGET}" ]; then
  rsync -a "${ROOT}/package/deps/${TARGET}/" "${PKG_INNER}/deps/${TARGET}/"
fi
if [ -f "${ROOT}/package/deps/manifest.json" ]; then
  cp "${ROOT}/package/deps/manifest.json" "${PKG_INNER}/deps/manifest.json"
fi
# Drop host bytecode and leftover wheel archives from the SPK payload
find "${PKG_INNER}" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "${PKG_INNER}/deps" -type f \( -name '*.whl' -o -name '*.pyc' \) -delete 2>/dev/null || true
chmod 755 "${PKG_INNER}/bin/run-python"
find "${PKG_INNER}/ui/webapi" -name '*.cgi' -exec chmod 755 {} \;

# Generate INFO
ARCH="${TARGET}"
if [ "${TARGET}" = "aarch64" ]; then ARCH="aarch64"; fi
if [ "${TARGET}" = "armv7" ]; then ARCH="armv7"; fi
sed -e "s/@VERSION@/${VERSION}/g" -e "s/@ARCH@/${ARCH}/g" "${ROOT}/spk/INFO.in" > "${SPK_DIR}/INFO"
cp -a "${ROOT}/spk/PACKAGE_ICON.PNG" "${ROOT}/spk/PACKAGE_ICON_256.PNG" "${SPK_DIR}/"
cp -a "${ROOT}/spk/conf" "${SPK_DIR}/"
cp -a "${ROOT}/spk/scripts/." "${SPK_DIR}/scripts/"
chmod 755 "${SPK_DIR}/scripts/"*
if [ -d "${ROOT}/spk/WIZARD_UIFILES" ]; then
  cp -a "${ROOT}/spk/WIZARD_UIFILES" "${SPK_DIR}/"
fi

# Create package.tgz and spk
(
  cd "${PKG_INNER}"
  tar --owner=0 --group=0 -czf "${SPK_DIR}/package.tgz" .
)
(
  cd "${SPK_DIR}"
  tar --owner=0 --group=0 -cf "${DIST}/OTPAuthentication-${VERSION}-${TARGET}.spk" INFO PACKAGE_ICON.PNG PACKAGE_ICON_256.PNG package.tgz scripts conf
  if [ -d WIZARD_UIFILES ]; then
    tar --owner=0 --group=0 -rf "${DIST}/OTPAuthentication-${VERSION}-${TARGET}.spk" WIZARD_UIFILES || true
  fi
)

# Normalize to .spk (tar file)
SPK_PATH="${DIST}/OTPAuthentication-${VERSION}-${TARGET}.spk"
sha256sum "${SPK_PATH}" | tee "${SPK_PATH}.sha256"
python3 "${ROOT}/build/validate_spk.py" "${SPK_PATH}"
echo "Built ${SPK_PATH}"