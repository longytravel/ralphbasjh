"""
Tests for Step 1: Load EA
"""

import os
import tempfile
from pathlib import Path
import unittest

from ea_stress.workflow.steps.step01_load import load_ea, validate_ea_path, LoadResult


class TestStep01Load(unittest.TestCase):
    """Test cases for EA load step."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up test files."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_load_valid_mq5_file(self):
        """Test loading a valid .mq5 file."""
        # Create a test .mq5 file
        test_file = os.path.join(self.temp_dir, "test_ea.mq5")
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write("// Test EA\ninput int Period = 14;\n")

        result = load_ea(test_file)

        self.assertTrue(result.file_exists)
        self.assertTrue(result.is_mq5)
        self.assertFalse(result.is_mq4)
        self.assertIsNone(result.error)
        self.assertTrue(result.passed_gate())
        self.assertGreater(result.file_size, 0)
        self.assertEqual(result.file_path, test_file)

    def test_load_valid_mq4_file(self):
        """Test loading a valid .mq4 file."""
        # Create a test .mq4 file
        test_file = os.path.join(self.temp_dir, "test_ea.mq4")
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write("// Test EA MQ4\ninput int Period = 14;\n")

        result = load_ea(test_file)

        self.assertTrue(result.file_exists)
        self.assertFalse(result.is_mq5)
        self.assertTrue(result.is_mq4)
        self.assertIsNone(result.error)
        self.assertTrue(result.passed_gate())

    def test_load_nonexistent_file(self):
        """Test loading a file that doesn't exist."""
        test_file = os.path.join(self.temp_dir, "nonexistent.mq5")

        result = load_ea(test_file)

        self.assertFalse(result.file_exists)
        self.assertFalse(result.passed_gate())
        self.assertIsNotNone(result.error)
        self.assertIn("does not exist", result.error)

    def test_load_directory_instead_of_file(self):
        """Test loading a directory instead of a file."""
        result = load_ea(self.temp_dir)

        self.assertFalse(result.file_exists)
        self.assertFalse(result.passed_gate())
        self.assertIsNotNone(result.error)
        self.assertIn("not a file", result.error)

    def test_load_invalid_extension(self):
        """Test loading a file with invalid extension."""
        test_file = os.path.join(self.temp_dir, "test_ea.txt")
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write("// Not an EA file\n")

        result = load_ea(test_file)

        self.assertFalse(result.file_exists)
        self.assertFalse(result.passed_gate())
        self.assertIsNotNone(result.error)
        self.assertIn("Invalid file extension", result.error)

    def test_load_empty_file(self):
        """Test loading an empty but valid .mq5 file."""
        test_file = os.path.join(self.temp_dir, "empty.mq5")
        with open(test_file, 'w', encoding='utf-8') as f:
            pass  # Create empty file

        result = load_ea(test_file)

        self.assertTrue(result.file_exists)
        self.assertTrue(result.passed_gate())
        self.assertEqual(result.file_size, 0)

    def test_load_with_unicode_content(self):
        """Test loading file with Unicode content."""
        test_file = os.path.join(self.temp_dir, "unicode.mq5")
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write("// EA with unicode: €£¥\ninput int Period = 14;\n")

        result = load_ea(test_file)

        self.assertTrue(result.file_exists)
        self.assertTrue(result.passed_gate())

    def test_absolute_path_resolution(self):
        """Test that absolute path is correctly resolved."""
        test_file = os.path.join(self.temp_dir, "test.mq5")
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write("// Test\n")

        result = load_ea(test_file)

        self.assertTrue(os.path.isabs(result.absolute_path))
        self.assertTrue(os.path.exists(result.absolute_path))

    def test_to_dict_serialization(self):
        """Test conversion to dictionary for JSON serialization."""
        test_file = os.path.join(self.temp_dir, "test.mq5")
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write("// Test\n")

        result = load_ea(test_file)
        result_dict = result.to_dict()

        self.assertIsInstance(result_dict, dict)
        self.assertIn('file_exists', result_dict)
        self.assertIn('file_path', result_dict)
        self.assertIn('absolute_path', result_dict)
        self.assertIn('file_size', result_dict)
        self.assertIn('is_mq5', result_dict)
        self.assertIn('is_mq4', result_dict)
        self.assertIn('error', result_dict)
        self.assertIn('gate_passed', result_dict)
        self.assertTrue(result_dict['gate_passed'])

    def test_validate_ea_path_helper_valid(self):
        """Test validate_ea_path helper with valid file."""
        test_file = os.path.join(self.temp_dir, "test.mq5")
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write("// Test\n")

        is_valid, error = validate_ea_path(test_file)

        self.assertTrue(is_valid)
        self.assertEqual(error, "")

    def test_validate_ea_path_helper_invalid(self):
        """Test validate_ea_path helper with invalid file."""
        test_file = os.path.join(self.temp_dir, "nonexistent.mq5")

        is_valid, error = validate_ea_path(test_file)

        self.assertFalse(is_valid)
        self.assertNotEqual(error, "")

    def test_load_with_spaces_in_path(self):
        """Test loading file with spaces in path."""
        subdir = os.path.join(self.temp_dir, "test folder with spaces")
        os.makedirs(subdir, exist_ok=True)
        test_file = os.path.join(subdir, "test ea.mq5")
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write("// Test EA\n")

        result = load_ea(test_file)

        self.assertTrue(result.file_exists)
        self.assertTrue(result.passed_gate())

    def test_load_case_insensitive_extension(self):
        """Test that extension matching is case-insensitive."""
        # Test .MQ5
        test_file_upper = os.path.join(self.temp_dir, "test.MQ5")
        with open(test_file_upper, 'w', encoding='utf-8') as f:
            f.write("// Test\n")

        result = load_ea(test_file_upper)
        self.assertTrue(result.file_exists)
        self.assertTrue(result.is_mq5)

    def test_gate_failure_on_nonexistent(self):
        """Test that gate fails for nonexistent file."""
        result = load_ea("nonexistent.mq5")
        self.assertFalse(result.passed_gate())

    def test_gate_failure_on_invalid_extension(self):
        """Test that gate fails for invalid extension."""
        test_file = os.path.join(self.temp_dir, "test.cpp")
        with open(test_file, 'w', encoding='utf-8') as f:
            f.write("// C++ file\n")

        result = load_ea(test_file)
        self.assertFalse(result.passed_gate())


if __name__ == '__main__':
    unittest.main()
