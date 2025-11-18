.PHONY: all
all: setup lint test

.PHONY: setup
setup:
	uv sync --dev
	uv run pre-commit install

.PHONY: format
format:
ifdef CI
	uv run pre-commit run --all-files --show-diff-on-failure
else
	uv run pre-commit run --all-files
endif


.PHONY: lint
lint: format
	uv run mypy

.PHONY: test
test:
	uv run pytest --cov=neuro_logging --cov-report xml:.coverage.xml tests


.PHONY: clean
clean:
	git clean -df
