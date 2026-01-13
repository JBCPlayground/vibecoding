# vibecoding

A Python project.

## Setup

Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

Install dependencies:
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt  # For development
```

## Development

Run tests:
```bash
pytest
```

## Usage

Run the example module:
```bash
python -m vibecoding
```

Or use the utilities in your own code:
```python
from vibecoding.utils import greet, calculate_average, filter_positive

print(greet("World", excited=True))
avg = calculate_average([1, 2, 3, 4, 5])
positive = filter_positive([-1, 0, 1, 2])
```
