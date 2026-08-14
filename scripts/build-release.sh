#!/usr/bin/env bash
#
# Build a release archive for external distribution.
#
# The archive ships the .py sources as-is (no wheel/sdist build) plus the
# user-facing docs only. Developer material (CONTEXT.md, docs/adr, TODO.md,
# requirement.md, docs/development.md, docs/STYLE_GUIDE.md, tests) is excluded.
#
# Usage:
#   scripts/build-release.sh [output_dir]
#
# Output:
#   <output_dir>/dify2langgraph-<version>/        the staged release tree
#   <output_dir>/dify2langgraph-<version>.tar.gz  the archive
#
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out_dir="${1:-"${repo_root}/dist"}"

# Read the version from pyproject.toml ([project] version = "x.y.z").
version="$(
  awk -F'"' '/^\[project\]/{p=1} p && /^[[:space:]]*version[[:space:]]*=/{print $2; exit}' \
    "${repo_root}/pyproject.toml"
)"
if [[ -z "${version}" ]]; then
  echo "error: could not read version from pyproject.toml" >&2
  exit 1
fi

name="dify2langgraph-${version}"
stage="${out_dir}/${name}"

echo "Building release ${name}"
rm -rf "${stage}"
mkdir -p "${stage}"

# 1) Source code, as-is (exclude caches).
mkdir -p "${stage}/src"
cp -R "${repo_root}/src/dify2langgraph" "${stage}/src/dify2langgraph"
find "${stage}/src" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "${stage}/src" -type f \( -name '*.pyc' -o -name '.DS_Store' \) -delete

# 2) Packaging metadata so `pip install .` works without a build step.
cp "${repo_root}/pyproject.toml" "${stage}/pyproject.toml"

# 3) User-facing docs only. Drop README's trailing "開発者向け" (developer) section,
#    whose links point at excluded developer docs.
sed '/^## 開発者向け$/,$d' "${repo_root}/README.md" > "${stage}/README.md"
cp "${repo_root}/USAGE.md" "${stage}/USAGE.md"

# 4) Archive.
mkdir -p "${out_dir}"
tar -C "${out_dir}" -czf "${out_dir}/${name}.tar.gz" "${name}"

echo "Staged tree: ${stage}"
echo "Archive:     ${out_dir}/${name}.tar.gz"
