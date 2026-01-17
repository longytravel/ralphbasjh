"""
Tests for Step 3: Extract Parameters
"""

import tempfile
import unittest
from pathlib import Path

from ea_stress.workflow.steps.step03_extract import (
    extract_parameters,
    normalize_type,
    is_numeric_type,
    validate_extraction,
)


class TestNormalizeType(unittest.TestCase):
    def test_int_types(self):
        self.assertEqual(normalize_type('int'), 'int')
        self.assertEqual(normalize_type('uint'), 'int')
        self.assertEqual(normalize_type('long'), 'int')

    def test_double_types(self):
        self.assertEqual(normalize_type('double'), 'double')
        self.assertEqual(normalize_type('float'), 'double')

    def test_enum_types(self):
        self.assertEqual(normalize_type('ENUM_TIMEFRAMES'), 'enum')


class TestParameterExtraction(unittest.TestCase):
    def test_simple_parameter(self):
        ea_code = """
input int FastPeriod = 10;  // Fast MA period
input double LotSize = 0.1;  // Position size
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.mq5', delete=False, encoding='utf-8') as f:
            f.write(ea_code)
            temp_path = f.name

        try:
            result = extract_parameters(temp_path)
            self.assertTrue(result.gate_passed)
            self.assertEqual(result.params_found, 2)
            self.assertEqual(result.optimizable_count, 2)
            self.assertEqual(result.parameters[0].name, 'FastPeriod')
            self.assertTrue(result.parameters[0].optimizable)
        finally:
            Path(temp_path).unlink()

    def test_sinput_not_optimizable(self):
        ea_code = """
sinput int MagicNumber = 12345;
input int Period = 20;
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.mq5', delete=False, encoding='utf-8') as f:
            f.write(ea_code)
            temp_path = f.name

        try:
            result = extract_parameters(temp_path)
            self.assertEqual(result.params_found, 2)
            self.assertEqual(result.optimizable_count, 1)
            self.assertFalse(result.parameters[0].optimizable)
        finally:
            Path(temp_path).unlink()

    def test_gate_passes_with_params(self):
        ea_code = """
input int Period = 20;
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.mq5', delete=False, encoding='utf-8') as f:
            f.write(ea_code)
            temp_path = f.name

        try:
            result = extract_parameters(temp_path)
            self.assertTrue(result.passed_gate())
        finally:
            Path(temp_path).unlink()


if __name__ == '__main__':
    unittest.main()
