.PHONY: test lint release

test:
	uv run pytest tests/ -q

lint:
	uv run ruff check src tests
	uv run ty check src

# Build a release archive (user-facing docs + .py sources, no build step).
release:
	scripts/build-release.sh
