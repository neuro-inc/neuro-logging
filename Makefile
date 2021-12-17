SHELL := /bin/bash

ISORT_TARGETS := neuro_logging tests
BLACK_TARGETS := $(ISORT_TARGETS)
MYPY_TARGETS :=  $(ISORT_TARGETS)
FLAKE8_TARGETS:= $(ISORT_TARGETS)


setup:
	pip install -U pip
	pip install -r requirements-test.txt
	pre-commit install

format:
ifdef CI
	pre-commit run --all-files --show-diff-on-failure
else
	pre-commit run --all-files
endif


lint: format
	mypy $(MYPY_TARGETS)

test:
	pytest --cov=neuro_logging --cov-report xml:.coverage.xml tests
