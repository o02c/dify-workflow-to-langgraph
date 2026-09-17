# The converter also ships as a Docker image; generated output does not

The **converter** (the `dify2langgraph` CLI) ships with a `Dockerfile`,
`.dockerignore` and `compose.yaml` in the repository root, so a destination site
can run it without providing a Python 3.13 toolchain of its own. The image is
**not published to a registry**: customers run `docker build -t dify2langgraph .`
against the shipped Dockerfile, so what they run is readable before they run it.
`scripts/build-release.sh` therefore stages those three files plus `uv.lock`.

**Generated packages get no Dockerfile and no requirements.txt.** They stay plain
Python sources that run in the destination's existing environment — the output
contract of [ADR-0007](./0007-generated-output-is-a-self-contained-package.md) is
unchanged. Containerizing the converter is about *our* toolchain being awkward to
install on a customer's Windows machine; it says nothing about how the customer
wants to deploy the workflow we hand them.

This is a distribution channel, not a behaviour change: the CLI's defaults are
identical inside and outside the container.

## Why a container

The Windows port cost us Python 3.13 provisioning, console-codepage mangling
(cp932 vs UTF-8) and per-shell environment-variable syntax. Each of those is a
property of the *environment*, so shipping the environment removes all three at
once. `PYTHONUTF8=1` is baked into the image rather than left as an instruction.

## Consequences

### There is no implicit AWS region any more

`BedrockProvider` used to default to `region="us-east-1"` and pass it to
`boto3.Session` unconditionally, which outranked both the environment and the
profile's own `region`. A customer whose Bedrock lives in `ap-northeast-1` got a
silent `AccessDeniedException` against the wrong region.

The region now resolves as `--aws-region` → `AWS_REGION` → `AWS_DEFAULT_REGION`,
and when none is set **no `region_name` is passed at all**, letting boto3 resolve
the profile's region. **If nothing resolves, this now raises `NoRegionError`
instead of silently using us-east-1.** Failing loudly beats calling the wrong
account's endpoint; the CLI turns that error into an instruction naming the flag.

Both region variables must be set, not one: botocore reads only
`AWS_DEFAULT_REGION`, while `langchain-aws` also reads `AWS_REGION`.

`boto3.Session(profile_name=...)` is still passed **only** when `--aws-profile` is
given, because naming a profile makes botocore drop `EnvProvider` from the
credential chain — passing it unconditionally would make static credentials in
the environment stop working.

### `~/.aws` is mounted read-write

botocore refreshes an SSO token when it is within 15 minutes of expiry and writes
the result back to `~/.aws/sso/cache/`. That write has no `try/except`, and on the
first resolution it is mandatory, so a read-only mount raises `OSError` — *after*
the sso-oidc call succeeds, which makes the cause hard to see. The failure only
appears in a 15-minute window every ~8 hours, so it looks intermittent. The write
is the same one the host's AWS CLI performs, so read-write is not a widening of
trust. There is no environment variable to relocate that cache, and `HOME` must
be set explicitly in the image because `--user <uid>` leaves no `/etc/passwd`
entry for `~` to resolve against.

`aws sso login` needs a browser and cannot run in the container, so it stays a
host-side prerequisite and the image deliberately contains no AWS CLI.

### `.env` is mounted, never passed via `--env-file`

Docker's `--env-file` uses its own parser (`docker/cli/pkg/kvfile`), which differs
from python-dotenv on quoting, `export ` prefixes and `#`. A hand-written `.env`
that works with the CLI is silently mangled by it. The working tree is mounted at
`/work` and python-dotenv reads `/work/.env` itself. This is why
`find_dotenv(usecwd=True)` is now used: with the default, the search starts at the
provider module's directory, which after installation is inside the venv and never
reaches the user's `.env`.

`docker compose`'s `env_file:` is a *different*, dotenv-compatible parser and is
safe; `compose.yaml` uses it.

### Dependencies are quarantined at lock time, not build time

`pyproject.toml` carries `[tool.uv] exclude-newer`, three days behind the present,
so no version is adopted before it has been public long enough to be yanked or
pulled. `make lock` rolls that timestamp forward (uv takes a fixed instant, not a
window) and re-resolves. The image builds with `uv sync --frozen`, which resolves
nothing and simply replays the result, so `uv.lock` has to be in the release
archive — and since the archive also ships `pyproject.toml`, a customer who
re-resolves inherits the same quarantine.

**The cutoff belongs in `pyproject.toml`, not in a `--exclude-newer` flag.** The
flag is not durable: `uv lock --exclude-newer <t>` followed by a plain `uv sync`
silently re-resolves past `<t>` and rewrites the lock. That was not hypothetical —
the first attempt here used the flag from a Makefile target and the resulting lock
contained `ruff` 0.16.8, `openai` 3.14.1 and `ty` 0.0.81, all published *after* its
own cutoff. In `pyproject.toml` the value survives `uv sync`, `uv add` and even
`uv lock --upgrade`, which is the property we actually wanted.

The first `make lock` moved 61 packages, because the lock had drifted: it pinned
`numpy==2.4.0`, which is yanked. It also raised `ruff` (to 0.16.8 then, 0.16.7 once
the quarantine was enforced properly), whose isort rules caught import ordering and
line wrapping that the generators had always got wrong in emitted `graph.py` and
node files. Generated packages ship without a
`pyproject.toml`, so they are linted with ruff's defaults — an 88-character line
length, not this repo's 100 — which is what `format_from_import` now targets and
what `TestGeneratedCodeIsLintClean` pins via `ruff check --isolated`.

`ruff` and `ty` moved out of the `dev` group into a `lint` group that the image
installs: `--lint` / `--auto-fix` shell out to those binaries, so they are runtime
dependencies of a CLI feature, not developer tooling. `psycopg2-binary`, left over
from the direct-SQL retriever removed in
[ADR-0006](./0006-retrieval-via-dify-api-behind-a-port.md), is dropped.

## Status

Implemented and verified on macOS / Rancher Desktop. The image builds and converts
deterministically (byte-identical to a host run) under both the default and an
arbitrary `--user` uid, via `docker run` and `docker compose`, leaving no
`__pycache__/` or `.ruff_cache/` in the mounted tree. `--lint` runs, confirming
ruff and ty are present. The Bedrock path was exercised against a real
`sso_session` profile with `~/.aws` mounted read-write: `--name-nodes` succeeded in
`ap-northeast-1` via both environment variables and `--aws-region`/`--aws-profile`,
and with an expired token it produced botocore's "Token has expired and refresh
failed" followed by our `aws sso login --profile ...` hint. Windows and Linux hosts
have not been exercised.
