# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python project with a standard package structure. The main source code lives in `src/vibecoding/` and tests in `tests/`.

## Essential Commands

### Environment Setup
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt          # Production dependencies
pip install -r requirements-dev.txt      # Development dependencies
```

### Testing
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_filename.py

# Run specific test function
pytest tests/test_filename.py::test_function_name

# Run with coverage
pytest --cov=src/vibecoding --cov-report=html

# Run with verbose output
pytest -v
```

### Code Quality
```bash
# Format code with Black
black src/ tests/

# Check formatting without modifying
black --check src/ tests/

# Lint with flake8
flake8 src/ tests/

# Type checking with mypy
mypy src/
```

### Running Individual Checks
```bash
# Format a single file
black src/vibecoding/module.py

# Lint a single file
flake8 src/vibecoding/module.py

# Type check a single file
mypy src/vibecoding/module.py
```

## Project Structure

```
vibecoding/
├── src/
│   └── vibecoding/        # Main package source code
│       └── __init__.py
├── tests/                 # Test files (mirror src structure)
│   └── __init__.py
├── requirements.txt       # Production dependencies
├── requirements-dev.txt   # Development dependencies
├── pyproject.toml         # Project configuration (Black, mypy, pytest)
└── README.md              # Project documentation
```

## Development Workflow

### Adding New Modules
- Place new Python modules in `src/vibecoding/`
- Create corresponding test files in `tests/` with `test_` prefix
- Import from the package using: `from vibecoding.module import function`

### Testing Conventions
- Test files must start with `test_` (e.g., `test_utils.py`)
- Test functions must start with `test_` (e.g., `def test_calculation():`)
- Test classes must start with `Test` (e.g., `class TestCalculator:`)

### Code Style
- Line length: 100 characters (configured in pyproject.toml)
- Formatter: Black (auto-formats on run)
- Linter: flake8 (checks for style issues)
- Type hints: Encouraged but not enforced by mypy

## Virtual Environment

Always ensure the virtual environment is activated before running commands. You can check if it's active by looking for `(venv)` in your terminal prompt or running:
```bash
which python  # Should point to venv/bin/python
```
