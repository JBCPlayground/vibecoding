"""Tests for the utils module."""

import pytest
from vibecoding.utils import greet, calculate_average, filter_positive


class TestGreet:
    """Tests for the greet function."""

    def test_basic_greeting(self):
        """Test basic greeting without excitement."""
        result = greet("Alice")
        assert result == "Hello, Alice."

    def test_excited_greeting(self):
        """Test greeting with excitement."""
        result = greet("Bob", excited=True)
        assert result == "Hello, Bob!"

    def test_empty_name(self):
        """Test greeting with empty name."""
        result = greet("")
        assert result == "Hello, ."


class TestCalculateAverage:
    """Tests for the calculate_average function."""

    def test_positive_numbers(self):
        """Test average of positive numbers."""
        result = calculate_average([1, 2, 3, 4, 5])
        assert result == 3.0

    def test_negative_numbers(self):
        """Test average including negative numbers."""
        result = calculate_average([-1, 0, 1])
        assert result == 0.0

    def test_single_number(self):
        """Test average of a single number."""
        result = calculate_average([42])
        assert result == 42.0

    def test_floats(self):
        """Test average with floating point numbers."""
        result = calculate_average([1.5, 2.5, 3.0])
        assert result == pytest.approx(2.333333, rel=1e-5)

    def test_empty_list_raises_error(self):
        """Test that empty list raises ValueError."""
        expected_msg = "Cannot calculate average of an empty list"
        with pytest.raises(ValueError, match=expected_msg):
            calculate_average([])


class TestFilterPositive:
    """Tests for the filter_positive function."""

    def test_mixed_numbers(self):
        """Test filtering mixed positive and negative numbers."""
        result = filter_positive([1, -2, 3, -4, 5])
        assert result == [1, 3, 5]

    def test_all_negative(self):
        """Test filtering when all numbers are negative."""
        result = filter_positive([-1, -2, -3])
        assert result == []

    def test_all_positive(self):
        """Test filtering when all numbers are positive."""
        result = filter_positive([1, 2, 3])
        assert result == [1, 2, 3]

    def test_includes_zero(self):
        """Test that zero is included in the results."""
        result = filter_positive([0, -1, 1])
        assert result == [0, 1]

    def test_empty_list(self):
        """Test filtering an empty list."""
        result = filter_positive([])
        assert result == []

    def test_floats(self):
        """Test filtering with floating point numbers."""
        result = filter_positive([1.5, -2.5, 3.0, -0.5])
        assert result == [1.5, 3.0]
