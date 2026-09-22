#!/usr/bin/env bash
#
# Verify the documented Git Bash behaviour of dify2langgraph.
#
# Git Bash is a real execution path in client environments, and it is not the
# same as PowerShell: it runs on the MSYS2 runtime, which rewrites arguments that
# look like Unix paths before handing them to a native Windows process. That
# rewriting helps in some places and breaks things in others, and USAGE.md makes
# claims about it (sections 8.2 and 9.2) that nothing checked until now.
#
# Companion to scripts/verify-windows.ps1, which covers the PowerShell-specific
# claims. Both delegate the substantive work to the same two Python helpers
# (scripts/output_digest.py, scripts/run_generated.py) so the two shells cannot
# disagree about what the output should be.
#
# Runs on macOS/Linux too, where the MSYS group reports SKIP -- that is how this
# script gets exercised before being handed to a Windows host.
#
# Usage:
#   scripts/verify-gitbash.sh [--expected-digest <hex>] [--with-llm] [--skip-docker]
#
# Prerequisite: uv. Installing uv alone is enough; it downloads CPython itself.
#   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
#   export PATH="$USERPROFILE/.local/bin:$PATH"

set -u

REPO_ROOT=""
EXPECTED_DIGEST=""
WITH_LLM=0
SKIP_DOCKER=0

while [ $# -gt 0 ]; do
  case "$1" in
    --repo-root) REPO_ROOT="$2"; shift 2 ;;
    --expected-digest) EXPECTED_DIGEST="$2"; shift 2 ;;
    --with-llm) WITH_LLM=1; shift ;;
    --skip-docker) SKIP_DOCKER=1; shift ;;
    -h|--help) sed -n '2,28p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

if [ -z "$REPO_ROOT" ]; then
  REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fi

# ---------------------------------------------------------------------------
# Result table
# ---------------------------------------------------------------------------
PASS_COUNT=0
FAIL_COUNT=0
SKIP_COUNT=0
RESULTS=""

if [ -t 1 ]; then
  C_PASS=$'\033[32m'; C_FAIL=$'\033[31m'; C_SKIP=$'\033[33m'
  C_DIM=$'\033[90m'; C_HEAD=$'\033[36m'; C_OFF=$'\033[0m'
else
  C_PASS=""; C_FAIL=""; C_SKIP=""; C_DIM=""; C_HEAD=""; C_OFF=""
fi

add_result() {
  # add_result <id> <status> <claim> [detail]
  _id="$1"; _status="$2"; _claim="$3"; _detail="${4:-}"
  case "$_status" in
    PASS) PASS_COUNT=$((PASS_COUNT + 1)); _c="$C_PASS" ;;
    FAIL) FAIL_COUNT=$((FAIL_COUNT + 1)); _c="$C_FAIL" ;;
    SKIP) SKIP_COUNT=$((SKIP_COUNT + 1)); _c="$C_SKIP" ;;
  esac
  printf '  %s[%s]%s %s - %s\n' "$_c" "$_status" "$C_OFF" "$_id" "$_claim"
  if [ -n "$_detail" ]; then
    printf '%s         %s%s\n' "$C_DIM" "$_detail" "$C_OFF"
  fi
  RESULTS="${RESULTS}${_id}|${_status}|${_claim}
"
}

section() { printf '\n%s=== %s ===%s\n' "$C_HEAD" "$1" "$C_OFF"; }

# Keep only the interesting part of a failed run: the CLI logs progress at INFO,
# so a raw dump buries the one line that says what went wrong.
error_detail() {
  _out="$(grep -E 'ERROR|Traceback|Error code|error:' 2>/dev/null | tail -3)"
  if [ -z "$_out" ]; then _out="$(tail -4)"; fi
  printf '%s' "$_out"
}

# ---------------------------------------------------------------------------
# Working copy: native processes cannot have a UNC current directory
# ---------------------------------------------------------------------------
case "$REPO_ROOT" in
  //*|\\\\*)
    LOCAL_ROOT="${TMPDIR:-/tmp}/d2l-repo-gitbash"
    printf '%sRepoRoot is on a network share:%s\n  %s\n' "$C_SKIP" "$C_OFF" "$REPO_ROOT"
    printf 'Windows cannot give a native process a UNC working directory, so\n'
    printf 'copying to local disk first: %s\n' "$LOCAL_ROOT"
    mkdir -p "$LOCAL_ROOT"
    # -a would try to preserve ownership across the share and fail noisily.
    (cd "$REPO_ROOT" && tar cf - \
        --exclude='.git' --exclude='.venv' --exclude='__pycache__' .) \
      | (cd "$LOCAL_ROOT" && tar xf -)
    if [ -f "$REPO_ROOT/.env" ]; then
      cp "$REPO_ROOT/.env" "$LOCAL_ROOT/.env"
      printf 'Carried .env across.\n'
    fi
    REPO_ROOT="$LOCAL_ROOT"
    printf 'Copied.\n'
    ;;
esac

FIXTURES="$REPO_ROOT/tests/fixtures"
DIGEST_PY="$REPO_ROOT/scripts/output_digest.py"
RUN_PY="$REPO_ROOT/scripts/run_generated.py"

for required in "$FIXTURES/guardduty_handler.yml" "$FIXTURES/simple_workflow.yml" \
                "$DIGEST_PY" "$RUN_PY"; do
  if [ ! -f "$required" ]; then
    printf '%sMissing: %s -- is --repo-root correct?%s\n' "$C_FAIL" "$required" "$C_OFF" >&2
    exit 2
  fi
done

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
section "Environment"

# MSYS2 (Git Bash) identifies itself in uname; a native Linux or macOS bash does not.
UNAME_S="$(uname -s 2>/dev/null || echo unknown)"
case "$UNAME_S" in
  MINGW*|MSYS*|CYGWIN*) ON_MSYS=1 ;;
  *) ON_MSYS=0 ;;
esac

if command -v uv >/dev/null 2>&1; then UV_VERSION="$(uv --version 2>&1)"; else UV_VERSION="(not found)"; fi
# On Windows a bare `python` may be the Microsoft Store stub, which prints an
# advert and exits non-zero rather than running; probe instead of trusting PATH.
PY_VERSION="(not found)"
if command -v python >/dev/null 2>&1; then
  _probe="$(python --version 2>&1 || true)"
  case "$_probe" in Python\ 3*) PY_VERSION="$_probe" ;; esac
fi
CODEPAGE="(n/a)"
if [ "$ON_MSYS" -eq 1 ] && command -v chcp.com >/dev/null 2>&1; then
  CODEPAGE="$(chcp.com 2>/dev/null | tr -dc '0-9')"
fi

# Stamped by `git archive` via export-subst (.gitattributes); stays the literal
# placeholder in a working checkout. See verify-windows.ps1 for the same trick.
SOURCE_COMMIT='$Format:%H$'
PLACEHOLDER='$'"Format:%H"'$'
if [ "$SOURCE_COMMIT" = "$PLACEHOLDER" ]; then
  SCRIPT_COMMIT="(working checkout, not a git archive export)"
else
  SCRIPT_COMMIT="$(printf '%s' "$SOURCE_COMMIT" | cut -c1-12)"
fi

printf 'Shell         : %s\n' "${BASH_VERSION:-unknown}"
printf 'uname         : %s %s\n' "$UNAME_S" "$(uname -r 2>/dev/null || echo '')"
printf 'MSYS runtime  : %s\n' "$([ "$ON_MSYS" -eq 1 ] && echo yes || echo 'no (not Git Bash)')"
printf 'ConsoleCP     : %s\n' "$CODEPAGE"
printf 'LANG          : %s\n' "${LANG:-(unset)}"
printf 'Python        : %s\n' "$PY_VERSION"
printf 'uv            : %s\n' "$UV_VERSION"
printf 'RepoRoot      : %s\n' "$REPO_ROOT"
printf 'PYTHONUTF8    : %s\n' "${PYTHONUTF8:-(unset)}"
printf 'ScriptCommit  : %s\n' "$SCRIPT_COMMIT"

if [ "$UV_VERSION" = "(not found)" ] && [ "$PY_VERSION" = "(not found)" ]; then
  printf '\n%sNeither uv nor a working python is on PATH.%s\n' "$C_FAIL" "$C_OFF" >&2
  printf 'Installing uv alone is enough -- it downloads CPython itself:\n' >&2
  printf '  powershell -c "irm https://astral.sh/uv/install.ps1 | iex"\n' >&2
  printf '  export PATH="$USERPROFILE/.local/bin:$PATH"\n' >&2
  exit 2
fi

USE_UV=0
if [ "$UV_VERSION" != "(not found)" ]; then USE_UV=1; fi

# Run the CLI, through uv when available so the pinned dependency set is used.
run_cli() {
  if [ "$USE_UV" -eq 1 ]; then
    uv run --project "$REPO_ROOT" dify2langgraph "$@" 2>&1
  else
    PYTHONPATH="$REPO_ROOT/src" python -m dify2langgraph.cli "$@" 2>&1
  fi
}

run_py() {
  if [ "$USE_UV" -eq 1 ]; then
    uv run --project "$REPO_ROOT" python "$@" 2>&1
  else
    python "$@" 2>&1
  fi
}

# Force the environment to exist before judging any behaviour: uv builds the
# venv on first use and needs PyPI for it. Letting that happen inside the first
# check reports a network timeout as "conversion failed".
printf '\n%sPreparing the Python environment (first run downloads dependencies)...%s\n' "$C_HEAD" "$C_OFF"
if ! PREFLIGHT="$(cd "$REPO_ROOT" && run_py --version)"; then
  printf '%sCould not prepare the environment:%s\n%s\n' "$C_FAIL" "$C_OFF" "$PREFLIGHT" >&2
  printf 'This is an environment problem, not a product failure -- usually no route\n' >&2
  printf 'to pypi.org, or a proxy needing HTTPS_PROXY. Stopping here.\n' >&2
  exit 2
fi
printf '%sReady: %s%s\n' "$C_DIM" "$(printf '%s' "$PREFLIGHT" | tail -1)" "$C_OFF"

WORK="$(mktemp -d "${TMPDIR:-/tmp}/d2l-gitbash-XXXXXX")"
cp "$FIXTURES/guardduty_handler.yml" "$FIXTURES/simple_workflow.yml" "$WORK/"
GEN_ROOT="$WORK/out/guardduty_handler"

# ---------------------------------------------------------------------------
# B. The converter runs
# ---------------------------------------------------------------------------
section "B. Converter (via Git Bash)"

B1_OUT="$(cd "$WORK" && run_cli guardduty_handler.yml -o out --skip-implement)"
if [ -d "$GEN_ROOT" ]; then
  add_result B1 PASS "Converting a DSL with Japanese text succeeds"
else
  add_result B1 FAIL "Converting a DSL with Japanese text succeeds" \
    "$(printf '%s' "$B1_OUT" | error_detail)"
fi

if [ -f "$GEN_ROOT/state.py" ] && grep -q "質問分類器" "$GEN_ROOT/state.py" 2>/dev/null; then
  add_result B2 PASS "Japanese survives the round trip into generated sources"
else
  add_result B2 FAIL "Japanese survives the round trip into generated sources" \
    "expected node titles not found in state.py"
fi

CRLF_FILES=""
if [ -d "$GEN_ROOT" ]; then
  # Read NUL-delimited: a Windows path routinely contains spaces
  # (C:\Program Files\...), which word-splitting would tear apart.
  while IFS= read -r -d '' f; do
    if LC_ALL=C grep -q $'\r' "$f" 2>/dev/null; then
      CRLF_FILES="$CRLF_FILES $(basename "$f")"
    fi
  done < <(find "$GEN_ROOT" -name '*.py' -print0 2>/dev/null)
fi
if [ -d "$GEN_ROOT" ] && [ -z "$CRLF_FILES" ]; then
  add_result B3 PASS "Generated files use LF, not CRLF (cross-platform determinism)"
else
  add_result B3 FAIL "Generated files use LF, not CRLF (cross-platform determinism)" \
    "CRLF in:${CRLF_FILES:- (no output to check)}"
fi

DIGEST="(unavailable)"
if [ -d "$GEN_ROOT" ]; then
  DIGEST="$(run_py "$DIGEST_PY" --dir "$GEN_ROOT" | tail -1 | tr -d '\r')"
fi
if [ -z "$EXPECTED_DIGEST" ]; then
  add_result B5 SKIP "Output is byte-identical to the macOS/container run" \
    "no --expected-digest given; this host produced $DIGEST"
elif [ "$DIGEST" = "$EXPECTED_DIGEST" ]; then
  add_result B5 PASS "Output is byte-identical to the macOS/container run" "$DIGEST"
else
  add_result B5 FAIL "Output is byte-identical to the macOS/container run" \
    "expected $EXPECTED_DIGEST, got $DIGEST"
fi

# ---------------------------------------------------------------------------
# M. MSYS2 path handling -- the reason this script exists
# ---------------------------------------------------------------------------
section "M. MSYS2 path translation (Git Bash)"

if [ "$ON_MSYS" -eq 0 ]; then
  add_result M0 SKIP "MSYS2 path translation" "not running under Git Bash ($UNAME_S)"
else
  # MSYS rewrites arguments that look like Unix paths into Windows form before
  # launching a native process. /c/Users/... should therefore reach the CLI as
  # C:\Users\..., which is the only form Windows Python can open.
  M1_OUT="$(cd "$WORK" && run_cli "$(pwd)/guardduty_handler.yml" -o msys --skip-implement)"
  if [ -f "$WORK/msys/guardduty_handler/state.py" ]; then
    add_result M1 PASS "An MSYS-style path (/c/...) reaches the CLI usable" \
      "argument conversion turned it into a Windows path"
  else
    add_result M1 FAIL "An MSYS-style path (/c/...) reaches the CLI usable" \
      "$(printf '%s' "$M1_OUT" | error_detail)"
  fi

  # pwd -W is the MSYS-only way to get the Windows form, which USAGE 9.2 tells
  # Docker users to pass as the bind-mount source.
  if WIN_PWD="$(pwd -W 2>/dev/null)" && [ -n "$WIN_PWD" ]; then
    case "$WIN_PWD" in
      ?:/*) add_result M2 PASS 'pwd -W returns a Windows-form path (USAGE 9.2)' "$WIN_PWD" ;;
      *) add_result M2 FAIL 'pwd -W returns a Windows-form path (USAGE 9.2)' "got $WIN_PWD" ;;
    esac
  else
    add_result M2 FAIL 'pwd -W returns a Windows-form path (USAGE 9.2)' "pwd -W failed"
  fi

  # A Windows-form path must work too: users copy paths out of Explorer.
  M3_OUT="$(cd "$WORK" && run_cli "$(pwd -W 2>/dev/null)/guardduty_handler.yml" -o winform --skip-implement)"
  if [ -f "$WORK/winform/guardduty_handler/state.py" ]; then
    add_result M3 PASS "A Windows-form path (C:/...) also reaches the CLI usable"
  else
    add_result M3 FAIL "A Windows-form path (C:/...) also reaches the CLI usable" \
      "$(printf '%s' "$M3_OUT" | error_detail)"
  fi
fi

# ---------------------------------------------------------------------------
# D. bash environment-variable syntax (USAGE 8.2)
# ---------------------------------------------------------------------------
section "D. bash environment variables (USAGE 8.2)"

VERBOSE_OUT="$(cd "$WORK" && LOG_LEVEL=DEBUG run_cli guardduty_handler.yml -o dbg1 --skip-implement)"
QUIET_OUT="$(cd "$WORK" && LOG_LEVEL=ERROR run_cli guardduty_handler.yml -o dbg2 --skip-implement)"
if [ "${#VERBOSE_OUT}" -gt "${#QUIET_OUT}" ]; then
  add_result D1 PASS 'The inline VAR=value form reaches the CLI (USAGE 8.2)' \
    "LOG_LEVEL honoured (DEBUG more verbose than ERROR)"
else
  add_result D1 FAIL 'The inline VAR=value form reaches the CLI (USAGE 8.2)' \
    "DEBUG ${#VERBOSE_OUT} chars vs ERROR ${#QUIET_OUT} chars"
fi

EXPORT_OUT="$(cd "$WORK" && export LOG_LEVEL=DEBUG && run_cli guardduty_handler.yml -o dbg3 --skip-implement)"
if [ "${#EXPORT_OUT}" -gt "${#QUIET_OUT}" ]; then
  add_result D2 PASS 'export VAR=value reaches the CLI (USAGE 8.2)'
else
  add_result D2 FAIL 'export VAR=value reaches the CLI (USAGE 8.2)' \
    "export made no difference to output volume"
fi

if printf '%s' "$QUIET_OUT$VERBOSE_OUT" | LC_ALL=C grep -q $'\033'; then
  add_result D3 FAIL "No literal ANSI escape codes in captured output" \
    "ESC sequences present in captured (non-tty) output"
else
  add_result D3 PASS "No literal ANSI escape codes in captured output"
fi

# ---------------------------------------------------------------------------
# F. Generated workflows actually run (ADR-0007, ADR-0009)
# ---------------------------------------------------------------------------
section "F. Generated workflows run"

GEN_DIR="$WORK/gen"
(cd "$WORK" && run_cli simple_workflow.yml -o "$GEN_DIR" --skip-implement >/dev/null 2>&1)
(cd "$WORK" && run_cli guardduty_handler.yml -o "$GEN_DIR" --skip-implement >/dev/null 2>&1)

# Workflow inputs go under the Start Node's own key (ADR-0009); a required one
# that is absent raises rather than being invented.
printf '%s' '{"start_node": {"query": "example"}}' > "$WORK/f1.json"
F1_OUT="$(run_py "$RUN_PY" "$GEN_DIR" simple_workflow --initial-file "$WORK/f1.json")"
F1_JSON="$(printf '%s' "$F1_OUT" | grep '^{' | tail -1)"
if printf '%s' "$F1_JSON" | grep -q '"start_node"' &&
   printf '%s' "$F1_JSON" | grep -q '"llm_node"' &&
   printf '%s' "$F1_JSON" | grep -q '"end_node"'; then
  add_result F1 PASS "A generated linear workflow runs and visits every node"
else
  add_result F1 FAIL "A generated linear workflow runs and visits every node" \
    "$(printf '%s' "$F1_OUT" | error_detail)"
fi

if printf '%s' "$F1_JSON" | grep -q '"query": "example"'; then
  add_result F2 PASS "The caller's workflow inputs survive the Start Node (ADR-0009)"
else
  add_result F2 FAIL "The caller's workflow inputs survive the Start Node (ADR-0009)" \
    "$(printf '%s' "$F1_JSON" | cut -c1-200)"
fi

F3_OUT="$(run_py "$RUN_PY" "$GEN_DIR" simple_workflow 2>&1 || true)"
if printf '%s' "$F3_OUT" | grep -q "missing required workflow input"; then
  add_result F3 PASS "A missing required input fails loudly rather than defaulting"
else
  add_result F3 FAIL "A missing required input fails loudly rather than defaulting" \
    "$(printf '%s' "$F3_OUT" | error_detail)"
fi

# ---------------------------------------------------------------------------
# C. Console encoding (USAGE 8.1)
# ---------------------------------------------------------------------------
section "C. Console encoding (USAGE 8.1)"

RT_DIR="$WORK/rt"
(cd "$WORK" && run_cli simple_workflow.yml -o "$RT_DIR" --skip-implement >/dev/null 2>&1)
LLM_NODE="$RT_DIR/simple_workflow/nodes/llm_node.py"
if [ -f "$LLM_NODE" ] && grep -q '"text": "placeholder"' "$LLM_NODE"; then
  # Stand in for an implemented body so the printed state carries non-ASCII.
  run_py -c "
import sys
from pathlib import Path
p = Path(sys.argv[1])
p.write_text(
    p.read_text(encoding='utf-8').replace('\"text\": \"placeholder\"', '\"text\": \"\u7ffb\u8a33\u7d50\u679c\"'),
    encoding='utf-8', newline='\n',
)
" "$LLM_NODE" >/dev/null 2>&1

  # A narrow codec stands in for a legacy Windows console on any host: the
  # generated __main__.py must escape what it cannot encode, not crash.
  C1_OUT="$(cd "$RT_DIR" && PYTHONIOENCODING=cp1252 run_py -m simple_workflow 2>&1 || true)"
  if printf '%s' "$C1_OUT" | grep -q "UnicodeEncodeError"; then
    add_result C1 FAIL "A narrow console codec does not crash the run (USAGE 8.1)" \
      "$(printf '%s' "$C1_OUT" | error_detail)"
  else
    add_result C1 PASS "A narrow console codec does not crash the run (USAGE 8.1)" \
      "escaped rather than raising"
  fi

  C2_OUT="$(cd "$RT_DIR" && PYTHONUTF8=1 PYTHONIOENCODING=utf-8 run_py -m simple_workflow 2>&1 || true)"
  if printf '%s' "$C2_OUT" | grep -q "翻訳結果"; then
    add_result C2 PASS "With PYTHONUTF8=1, the workflow emits UTF-8"
  else
    add_result C2 FAIL "With PYTHONUTF8=1, the workflow emits UTF-8" \
      "$(printf '%s' "$C2_OUT" | error_detail)"
  fi
else
  add_result C0 SKIP "Console encoding checks" "the generator's stub shape changed"
fi

# ---------------------------------------------------------------------------
# E. Docker (USAGE 9.2) -- optional
# ---------------------------------------------------------------------------
section "E. Docker (USAGE 9.2)"

if [ "$SKIP_DOCKER" -eq 1 ]; then
  add_result E0 SKIP "Docker checks" "--skip-docker was passed"
elif ! command -v docker >/dev/null 2>&1; then
  add_result E0 SKIP "Docker checks" "docker CLI not on PATH"
elif ! docker version --format '{{.Server.Version}}' >/dev/null 2>&1; then
  add_result E0 SKIP "Docker checks" \
    "daemon unreachable (in a Parallels VM: nested virtualization is Pro/Business only)"
else
  if (cd "$REPO_ROOT" && docker build -q -t dify2langgraph-gitbash . >/dev/null 2>&1); then
    add_result E1 PASS "The converter image builds"
  else
    add_result E1 FAIL "The converter image builds"
  fi

  DOCKER_OUT="$WORK/dockerout"
  mkdir -p "$DOCKER_OUT"
  cp "$FIXTURES/guardduty_handler.yml" "$DOCKER_OUT/"
  # MSYS_NO_PATHCONV and pwd -W are the two Git-Bash-specific readings in
  # USAGE 9.2: without them MSYS rewrites target=/work into a host path.
  if [ "$ON_MSYS" -eq 1 ]; then
    MOUNT_SRC="$(cd "$DOCKER_OUT" && pwd -W)"
  else
    MOUNT_SRC="$DOCKER_OUT"
  fi
  E2_OUT="$(MSYS_NO_PATHCONV=1 docker run --rm \
      --mount "type=bind,source=$MOUNT_SRC,target=/work" \
      dify2langgraph-gitbash guardduty_handler.yml -o out --skip-implement 2>&1 || true)"
  if [ -f "$DOCKER_OUT/out/guardduty_handler/state.py" ]; then
    add_result E2 PASS "MSYS_NO_PATHCONV + pwd -W give a working bind mount (USAGE 9.2)"
    E2_DIGEST="$(run_py "$DIGEST_PY" --dir "$DOCKER_OUT/out/guardduty_handler" | tail -1 | tr -d '\r')"
    if [ "$E2_DIGEST" = "$DIGEST" ]; then
      add_result E3 PASS "Container output matches the native run" "$E2_DIGEST"
    else
      add_result E3 FAIL "Container output matches the native run" \
        "native $DIGEST, container $E2_DIGEST"
    fi
  else
    add_result E2 FAIL "MSYS_NO_PATHCONV + pwd -W give a working bind mount (USAGE 9.2)" \
      "$(printf '%s' "$E2_OUT" | error_detail)"
    add_result E3 SKIP "Container output matches the native run" "E2 produced no output"
  fi
fi

# ---------------------------------------------------------------------------
# G. Real LLM calls (opt-in)
# ---------------------------------------------------------------------------
section "G. LLM paths (opt-in)"

if [ "$WITH_LLM" -eq 0 ]; then
  add_result G0 SKIP "LLM paths" "pass --with-llm to run these (they call a real model)"
else
  if [ -f "$REPO_ROOT/.env" ]; then
    cp "$REPO_ROOT/.env" "$WORK/.env"
    printf '%s  .env: %s%s\n' "$C_DIM" "$REPO_ROOT/.env" "$C_OFF"
  else
    printf '%s  .env: not found at %s%s\n' "$C_DIM" "$REPO_ROOT/.env" "$C_OFF"
  fi

  # Only the names are read, never the values.
  CONV_PROVIDER=""
  for pair in "OPENAI_API_KEY openai" "ANTHROPIC_API_KEY anthropic" \
              "AWS_PROFILE bedrock" "GOOGLE_API_KEY google" "GEMINI_API_KEY google"; do
    _name="${pair%% *}"; _provider="${pair##* }"
    if eval "[ -n \"\${$_name:-}\" ]" ||
       { [ -f "$WORK/.env" ] && grep -Eq "^[[:space:]]*${_name}[[:space:]]*=[[:space:]]*[^[:space:]]" "$WORK/.env"; }; then
      if [ -z "$CONV_PROVIDER" ]; then CONV_PROVIDER="$_provider"; fi
    fi
  done

  if [ -z "$CONV_PROVIDER" ]; then
    add_result G1 SKIP "LLM fills node bodies at conversion time" \
      "no LLM credential found (OPENAI_API_KEY, ANTHROPIC_API_KEY, AWS_PROFILE, GOOGLE_API_KEY, GEMINI_API_KEY)"
  else
    printf '%s  conversion provider: %s%s\n' "$C_DIM" "$CONV_PROVIDER" "$C_OFF"
    LLM_DIR="$WORK/llm"
    G1_OUT="$(cd "$WORK" && run_cli simple_workflow.yml -o "$LLM_DIR" --llm-provider "$CONV_PROVIDER")"
    STILL_STUBBED=0
    if [ -d "$LLM_DIR/simple_workflow/nodes" ]; then
      STILL_STUBBED="$(grep -l "TODO: Implement" "$LLM_DIR"/simple_workflow/nodes/*.py 2>/dev/null | wc -l | tr -d ' ')"
    fi
    if [ -d "$LLM_DIR/simple_workflow/nodes" ] && [ "$STILL_STUBBED" = "0" ]; then
      add_result G1 PASS "LLM fills node bodies at conversion time" "via $CONV_PROVIDER"
      printf '%s' '{"start_node": {"query": "hello"}}' > "$WORK/g2.json"
      G2_OUT="$(run_py "$RUN_PY" "$LLM_DIR" simple_workflow --initial-file "$WORK/g2.json")"
      if printf '%s' "$G2_OUT" | grep -q '^{'; then
        add_result G2 PASS "An LLM-implemented workflow runs"
      else
        add_result G2 FAIL "An LLM-implemented workflow runs" \
          "the LLM-written body failed at run time: $(printf '%s' "$G2_OUT" | error_detail)"
      fi
    else
      add_result G1 FAIL "LLM fills node bodies at conversion time" \
        "$(printf '%s' "$G1_OUT" | error_detail)"
      add_result G2 SKIP "An LLM-implemented workflow runs" "G1 did not implement the nodes"
    fi
  fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
section "Summary"

if [ "$ON_MSYS" -eq 0 ]; then
  printf '%sDRY RUN on %s: the control flow was exercised, but no Git Bash\nclaim was actually verified.%s\n\n' \
    "$C_SKIP" "$UNAME_S" "$C_OFF"
fi

printf '%s' "$RESULTS" | while IFS='|' read -r rid rstatus rclaim; do
  [ -n "$rid" ] || continue
  printf '%-4s %-6s %s\n' "$rid" "$rstatus" "$rclaim"
done

printf '\n%d passed, %d failed, %d skipped\n' "$PASS_COUNT" "$FAIL_COUNT" "$SKIP_COUNT"
printf 'Output digest (this host): %s\n' "$DIGEST"
printf 'Compare on macOS/Linux with: make verify-digest\n'
printf 'Temp working directory: %s\n' "$WORK"
if [ "$WITH_LLM" -eq 1 ] && [ -f "$WORK/.env" ]; then
  printf '%sNote: a copy of your .env is in that directory -- delete it when done.%s\n' "$C_SKIP" "$C_OFF"
fi

[ "$FAIL_COUNT" -eq 0 ]
