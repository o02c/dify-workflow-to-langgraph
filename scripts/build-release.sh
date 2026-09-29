#!/usr/bin/env bash
#
# Build a release archive for external distribution.
#
# The archive ships the .py sources as-is (no wheel/sdist build) plus everything
# needed to build, verify and understand them: build materials, scripts, tests,
# README.md and USAGE.md.
#
# The copy list below is an allowlist. Anything not named stays out, so material
# that only makes sense inside this repository cannot leak into a release -- and
# nothing distributed may point at something that did not come along (checked by
# tests/test_translator.py::TestNoPointersOutsideTheDistribution).
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

# 2) Build materials. pyproject.toml makes `pip install .` work without a build
#    step; .python-version and .gitattributes matter on the destination host --
#    the latter keeps .sh and .py checked out with LF, without which the
#    verification scripts will not start under Git Bash on Windows.
cp "${repo_root}/pyproject.toml" "${stage}/pyproject.toml"
cp "${repo_root}/.python-version" "${stage}/.python-version"
cp "${repo_root}/.gitattributes" "${stage}/.gitattributes"
cp "${repo_root}/Makefile" "${stage}/Makefile"

# 3) Docker packaging. uv.lock is required: the image builds with `uv sync
#    --frozen`, so without the lock the archive cannot be built at all.
cp "${repo_root}/Dockerfile" "${stage}/Dockerfile"
cp "${repo_root}/.dockerignore" "${stage}/.dockerignore"
cp "${repo_root}/compose.yaml" "${stage}/compose.yaml"
cp "${repo_root}/uv.lock" "${stage}/uv.lock"

# 4) Scripts and tests. The recipient can re-run the verification scripts on their
#    own host and the test suite against their own workflows, which is the point of
#    shipping them.
cp -R "${repo_root}/scripts" "${stage}/scripts"
cp -R "${repo_root}/tests" "${stage}/tests"
find "${stage}/scripts" "${stage}/tests" -type d \( -name '__pycache__' -o -name '.pytest_cache' \) -prune -exec rm -rf {} +
find "${stage}/scripts" "${stage}/tests" -type f \( -name '*.pyc' -o -name '.DS_Store' \) -delete

# 5) Documentation. Both files are written to stand on their own; README.md carries
#    no developer section, so it is copied whole.
cp "${repo_root}/README.md" "${stage}/README.md"
cp "${repo_root}/USAGE.md" "${stage}/USAGE.md"

# 6) Archive.
mkdir -p "${out_dir}"
tar -C "${out_dir}" -czf "${out_dir}/${name}.tar.gz" "${name}"

echo "Staged tree: ${stage}"
echo "Archive:     ${out_dir}/${name}.tar.gz"
