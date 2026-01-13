"""Main entry point for the vibecoding package."""

from vibecoding.utils import greet, calculate_average, filter_positive


def main():
    """Run example demonstrations of the package functionality."""
    print("=== Vibecoding Examples ===\n")

    # Greet example
    print("1. Greeting:")
    print(f"   {greet('World')}")
    print(f"   {greet('Python', excited=True)}\n")

    # Average example
    numbers = [10, 20, 30, 40, 50]
    print(f"2. Calculate average of {numbers}:")
    print(f"   Average: {calculate_average(numbers)}\n")

    # Filter example
    mixed_numbers = [-5, 10, -3, 0, 7, -1, 15]
    print(f"3. Filter positive numbers from {mixed_numbers}:")
    print(f"   Result: {filter_positive(mixed_numbers)}\n")


if __name__ == "__main__":
    main()
