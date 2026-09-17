# syntax=docker/dockerfile:1
#
# The converter (dify2langgraph CLI) as a container image.
#
# Build it yourself -- there is no registry to pull from:
#   docker build -t dify2langgraph .
#
# This packages the *converter* only. Generated LangGraph packages are plain
# Python sources meant to run in the destination's own environment (ADR-0007),
# so nothing here is emitted into the output directory.
#
# See docs/adr/0008-converter-ships-as-a-docker-image.md and USAGE.md section 9.

# --------------------------------------------------------------------------
# Builder: resolve nothing, install exactly what uv.lock pins.
# --------------------------------------------------------------------------
FROM python:3.13-slim AS builder

# Pinned to the uv that wrote uv.lock, so the lock format always matches.
COPY --from=ghcr.io/astral-sh/uv:0.6.10 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies first so this layer is reused until pyproject.toml/uv.lock change.
#
# --frozen: obey uv.lock exactly and never resolve during the build. Dependency
#   quarantine (`make lock`, --exclude-newer) happens once when the lock is
#   written; the build just replays it.
# --no-default-groups --group lint: skip pytest, but do install ruff and ty --
#   `--lint` / `--auto-fix` shell out to those binaries at runtime, so without
#   them those flags fail with FileNotFoundError inside the container.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-default-groups --group lint

# Then the project itself. --no-editable installs it into the venv rather than
# linking back to /app/src, so copying just the venv to the runtime stage works.
COPY src ./src
RUN uv sync --frozen --no-editable --no-default-groups --group lint

# --------------------------------------------------------------------------
# Runtime: the venv and nothing else.
# --------------------------------------------------------------------------
FROM python:3.13-slim AS runtime

# HOME: botocore hardcodes ~/.aws/sso/cache for SSO tokens with no env var to
#   redirect it. Running with `--user <uid>` leaves no /etc/passwd entry, HOME
#   falls back to "/", and ~ stops resolving -- so it must be set explicitly.
# PYTHONUTF8: bakes in the Windows console-codepage fix from USAGE.md 8.1 so it
#   cannot be forgotten.
# PYTHONDONTWRITEBYTECODE / RUFF_CACHE_DIR: keep __pycache__/ and .ruff_cache/
#   out of the bind-mounted working tree, where they would otherwise be left
#   behind owned by a uid the host user cannot delete.
ENV HOME=/home/app \
    PATH=/app/.venv/bin:$PATH \
    PYTHONUTF8=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    RUFF_CACHE_DIR=/tmp/ruff

COPY --from=builder /app/.venv /app/.venv

# 0777, not chown: Linux users must pass `--user "$(id -u):$(id -g)"` to keep
# generated files owned by themselves, and chowning to a fixed uid would leave
# every other uid unable to write to HOME or the working directory.
RUN mkdir -p /home/app /work && chmod 0777 /home/app /work

# No AWS CLI on purpose: `aws sso login` needs a browser and cannot run here.
# Log in on the host and mount ~/.aws (read-write) instead.

WORKDIR /work
USER 1000:1000
ENTRYPOINT ["dify2langgraph"]
