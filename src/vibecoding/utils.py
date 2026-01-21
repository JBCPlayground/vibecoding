"""Utility functions for vibecoding."""

from typing import List, Union


def greet(name: str, excited: bool = False) -> str:
    """
    Generate a greeting message.

    Args:
        name: The name to greet
        excited: Whether to use an exclamation mark

    Returns:
        A greeting message

    Example:
        >>> greet("World")
        'Hello, World.'
        >>> greet("World", excited=True)
        'Hello, World!'
    """
    punctuation = "!" if excited else "."
    return f"Hello, {name}{punctuation}"


def calculate_average(numbers: List[Union[int, float]]) -> float:
    """
    Calculate the average of a list of numbers.

    Args:
        numbers: A list of numbers to average

    Returns:
        The arithmetic mean of the numbers

    Raises:
        ValueError: If the list is empty

    Example:
        >>> calculate_average([1, 2, 3, 4, 5])
        3.0
        >>> calculate_average([10, 20])
        15.0
    """
    if not numbers:
        raise ValueError("Cannot calculate average of an empty list")

    return sum(numbers) / len(numbers)


def filter_positive(
    numbers: List[Union[int, float]]
) -> List[Union[int, float]]:
    """
    Filter out negative numbers from a list.

    Args:
        numbers: A list of numbers to filter

    Returns:
        A new list containing only positive numbers (and zero)

    Example:
        >>> filter_positive([1, -2, 3, -4, 5])
        [1, 3, 5]
        >>> filter_positive([-1, -2, -3])
        []
    """
    return [n for n in numbers if n >= 0]
