DEVPI_URL ?= "https://$(DEVPI_USER):$(DEVPI_PASS)@$(DEVPI_HOST)/$(DEVPI_USER)"

SHELL := /bin/bash

ISORT_TARGETS := platform_logging setup.py tests
BLACK_TARGETS := $(ISORT_TARGETS)
MYPY_TARGETS :=  $(ISORT_TARGETS)
FLAKE8_TARGETS:= $(ISORT_TARGETS)


setup:
	pip install -r requirements-test.txt

format:
	isort -rc $(ISORT_TARGETS)
	black $(BLACK_TARGETS)

lint:
	black --check $(BLACK_TARGETS)
	flake8 $(FLAKE8_TARGETS)
	mypy $(MYPY_TARGETS)

test:
	pytest --cov=platform_logging --cov-report xml:.coverage.xml tests


devpi_setup:
	pip install devpi-client
	pip install wheel
	@devpi use $(DEVPI_URL)/$(DEVPI_INDEX)

devpi_login:
	@devpi login $(DEVPI_USER) --password=$(DEVPI_PASS)

devpi_upload: devpi_login
	devpi upload --formats bdist_wheel
