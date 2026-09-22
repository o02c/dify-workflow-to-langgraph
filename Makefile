.PHONY: test lint lock docker-build verify-digest release

test:
	uv run pytest tests/ -q

lint:
	uv run ruff check src tests
	uv run ty check src

# Roll the dependency quarantine forward to "3 days ago" and re-resolve uv.lock.
# The cutoff itself lives in pyproject.toml ([tool.uv] exclude-newer) so that every
# uv resolution obeys it, not only this target; uv wants a fixed timestamp, so the
# script rewrites it. Commit the pyproject.toml change together with uv.lock.
# The Docker build reads the lock with `--frozen` and never resolves itself.
lock:
	python3 scripts/refresh-quarantine.py
	uv lock

# Build the converter image. Customers build this themselves from the shipped
# Dockerfile rather than pulling from a registry.
docker-build:
	docker build -t dify2langgraph .

# Digest of a reference conversion, for comparing against another platform.
# scripts/verify-windows.ps1 prints the same value on a Windows host; equal digests
# mean the two runs produced byte-identical output (ADR-0001). Uses --skip-implement
# so the run is deterministic and needs no credentials.
verify-digest:
	@uv run python scripts/output_digest.py tests/fixtures/guardduty_handler.yml

# Build a release archive (user-facing docs + .py sources, no build step).
release:
	scripts/build-release.sh
