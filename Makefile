POETRY_VERSION = 1.7.1
PYTHON_VERSION = 3.10

# Managing
# ========
.PHONY: poetry
poetry:
	curl -sSL https://install.python-poetry.org | python3 - --version $(POETRY_VERSION)

.PHONY: venv-with-dependencies
venv-with-dependencies:
	python$(PYTHON_VERSION) -m venv .venv --prompt patry
	poetry run pip install --upgrade pip
	poetry install

# Checking
# ========
.PHONY: black
black:
	poetry run black . --check

.PHONY: black!
black!:
	poetry run black .

.PHONY: mypy
mypy:
	poetry run mypy .

.PHONY: ruff
ruff:
	poetry run ruff check .

.PHONY: ruff!
ruff!:
	poetry run ruff check . --fix

.PHONY: doctests
doctests:
	poetry run python -m doctest patry/asset.py patry/bchile.py patry/utils.py

.PHONY: checks
checks: black mypy ruff doctests
