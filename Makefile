# Copyright (c) 2026 Qualcomm Technologies, Inc. and/or its subsidiaries.
# SPDX-License-Identifier: BSD-3-Clause

PY_FILES := $(shell git ls-files '*.py')

.PHONY: lint format install-dev

# Install the linting/formatting toolchain (ruff).
install-dev:
	python -m pip install --upgrade pip
	pip install -e ".[dev]"

# Check formatting and lint rules. Used locally and in CI.
lint:
	ruff check $(PY_FILES)
	ruff format --check $(PY_FILES)

# Auto-fix lint issues and reformat in place.
format:
	ruff check --fix $(PY_FILES)
	ruff format $(PY_FILES)
