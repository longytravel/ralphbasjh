"""Tests for Step 7: Run Optimization."""

import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from ea_stress.workflow.steps.step07_optimize import (
    run_optimization,
    validate_optimization,
    OptimizationResult,
    _count_passes_in_xml
)
from ea_stress.mt5.tester import BacktestResult


class TestOptimizationResult(unittest.TestCase):
    """Test OptimizationResult dataclass."""

    def test_gate_passed_with_passes(self):
        """Gate passes when passes_found >= 1."""
        result = OptimizationResult(
            success=True,
            passes_found=42,
            gate_passed=False  # Will be overridden by passed_gate()
        )
        self.assertTrue(result.passed_gate())

    def test_gate_failed_no_passes(self):
        """Gate fails when passes_found == 0."""
        result = OptimizationResult(
            success=True,
            passes_found=0
        )
        self.assertFalse(result.passed_gate())

    def test_to_dict_serialization(self):
        """Test JSON serialization."""
        result = OptimizationResult(
            success=True,
            xml_path=Path("/test/report.xml"),
            passes_found=100,
            duration_seconds=3600.5,
            terminal_output="Optimization complete"
        )
        data = result.to_dict()

        self.assertEqual(data["success"], True)
        self.assertIn("report.xml", data["xml_path"])
        self.assertEqual(data["passes_found"], 100)
        self.assertEqual(data["duration_seconds"], 3600.5)
        self.assertTrue(data["gate_passed"])


class TestRunOptimization(unittest.TestCase):
    """Test run_optimization function."""

    def test_ini_file_not_found(self):
        """Return error when INI file doesn't exist."""
        result = run_optimization(
            ini_path=Path("/nonexistent/test.ini"),
            terminal_path=Path("C:/MT5/terminal64.exe")
        )

        self.assertFalse(result.success)
        self.assertIn("INI file not found", result.error_message)
        self.assertEqual(result.passes_found, 0)
        self.assertFalse(result.passed_gate())

    @patch('ea_stress.workflow.steps.step07_optimize.MT5Tester')
    @patch('pathlib.Path.exists')
    def test_successful_optimization(self, mock_exists, mock_tester_class):
        """Test successful optimization with passes."""
        # Mock INI file exists
        mock_exists.return_value = True

        # Mock tester instance and result
        mock_tester = Mock()
        mock_tester_class.return_value = mock_tester

        mock_xml_path = Path("/test/optimization.xml")
        mock_backtest_result = BacktestResult(
            success=True,
            xml_path=mock_xml_path,
            duration_seconds=3600.0
        )
        mock_tester.run_backtest.return_value = mock_backtest_result

        # Mock XML pass counting
        with patch('ea_stress.workflow.steps.step07_optimize._count_passes_in_xml', return_value=250):
            result = run_optimization(
                ini_path=Path("/test/optimization.ini"),
                terminal_path=Path("C:/MT5/terminal64.exe")
            )

        self.assertTrue(result.success)
        self.assertEqual(result.xml_path, mock_xml_path)
        self.assertEqual(result.passes_found, 250)
        self.assertTrue(result.passed_gate())
        self.assertGreater(result.duration_seconds, 0)

    @patch('ea_stress.workflow.steps.step07_optimize.MT5Tester')
    @patch('pathlib.Path.exists')
    def test_optimization_failed_no_xml(self, mock_exists, mock_tester_class):
        """Test optimization failure when XML is not generated."""
        mock_exists.return_value = True

        mock_tester = Mock()
        mock_tester_class.return_value = mock_tester

        # Backtest succeeds but no XML
        mock_backtest_result = BacktestResult(
            success=True,
            xml_path=None,
            duration_seconds=100.0
        )
        mock_tester.run_backtest.return_value = mock_backtest_result

        result = run_optimization(
            ini_path=Path("/test/optimization.ini"),
            terminal_path=Path("C:/MT5/terminal64.exe")
        )

        self.assertFalse(result.success)
        self.assertIn("XML report not found", result.error_message)
        self.assertEqual(result.passes_found, 0)
        self.assertFalse(result.passed_gate())

    @patch('ea_stress.workflow.steps.step07_optimize.MT5Tester')
    @patch('pathlib.Path.exists')
    def test_optimization_terminal_failure(self, mock_exists, mock_tester_class):
        """Test optimization failure from terminal."""
        mock_exists.return_value = True

        mock_tester = Mock()
        mock_tester_class.return_value = mock_tester

        mock_backtest_result = BacktestResult(
            success=False,
            error_message="Terminal execution failed",
            terminal_output="Error: Symbol not found"
        )
        mock_tester.run_backtest.return_value = mock_backtest_result

        result = run_optimization(
            ini_path=Path("/test/optimization.ini"),
            terminal_path=Path("C:/MT5/terminal64.exe")
        )

        self.assertFalse(result.success)
        self.assertEqual(result.error_message, "Terminal execution failed")
        self.assertIn("Error: Symbol not found", result.terminal_output)
        self.assertEqual(result.passes_found, 0)
        self.assertFalse(result.passed_gate())

    @patch('ea_stress.workflow.steps.step07_optimize.MT5Tester')
    @patch('pathlib.Path.exists')
    def test_optimization_gate_failure_no_passes(self, mock_exists, mock_tester_class):
        """Test gate failure when optimization produces zero passes."""
        mock_exists.return_value = True

        mock_tester = Mock()
        mock_tester_class.return_value = mock_tester

        mock_xml_path = Path("/test/optimization.xml")
        mock_backtest_result = BacktestResult(
            success=True,
            xml_path=mock_xml_path,
            duration_seconds=3600.0
        )
        mock_tester.run_backtest.return_value = mock_backtest_result

        # Mock zero passes found
        with patch('ea_stress.workflow.steps.step07_optimize._count_passes_in_xml', return_value=0):
            result = run_optimization(
                ini_path=Path("/test/optimization.ini"),
                terminal_path=Path("C:/MT5/terminal64.exe")
            )

        self.assertTrue(result.success)  # Optimization ran successfully
        self.assertEqual(result.passes_found, 0)
        self.assertFalse(result.passed_gate())  # But gate failed

    @patch('ea_stress.workflow.steps.step07_optimize.MT5Tester')
    @patch('pathlib.Path.exists')
    def test_optimization_exception_handling(self, mock_exists, mock_tester_class):
        """Test exception handling during optimization."""
        mock_exists.return_value = True

        mock_tester_class.side_effect = RuntimeError("Terminal crashed")

        result = run_optimization(
            ini_path=Path("/test/optimization.ini"),
            terminal_path=Path("C:/MT5/terminal64.exe")
        )

        self.assertFalse(result.success)
        self.assertIn("Optimization exception", result.error_message)
        self.assertIn("Terminal crashed", result.error_message)
        self.assertEqual(result.passes_found, 0)

    @patch('ea_stress.workflow.steps.step07_optimize.MT5Tester')
    @patch('pathlib.Path.exists')
    def test_custom_timeout(self, mock_exists, mock_tester_class):
        """Test custom timeout parameter."""
        mock_exists.return_value = True

        mock_tester = Mock()
        mock_tester_class.return_value = mock_tester

        mock_xml_path = Path("/test/optimization.xml")
        mock_backtest_result = BacktestResult(
            success=True,
            xml_path=mock_xml_path
        )
        mock_tester.run_backtest.return_value = mock_backtest_result

        with patch('ea_stress.workflow.steps.step07_optimize._count_passes_in_xml', return_value=10):
            result = run_optimization(
                ini_path=Path("/test/optimization.ini"),
                terminal_path=Path("C:/MT5/terminal64.exe"),
                timeout=7200  # 2 hours
            )

        # Verify timeout was passed to run_backtest
        mock_tester.run_backtest.assert_called_once()
        call_kwargs = mock_tester.run_backtest.call_args[1]
        self.assertEqual(call_kwargs['timeout'], 7200)

    @patch('ea_stress.workflow.steps.step07_optimize.MT5Tester')
    @patch('pathlib.Path.exists')
    def test_data_path_parameter(self, mock_exists, mock_tester_class):
        """Test custom data_path parameter."""
        mock_exists.return_value = True

        mock_tester = Mock()
        mock_tester_class.return_value = mock_tester

        mock_xml_path = Path("/test/optimization.xml")
        mock_backtest_result = BacktestResult(
            success=True,
            xml_path=mock_xml_path
        )
        mock_tester.run_backtest.return_value = mock_backtest_result

        custom_data_path = Path("C:/Custom/MT5Data")

        with patch('ea_stress.workflow.steps.step07_optimize._count_passes_in_xml', return_value=5):
            result = run_optimization(
                ini_path=Path("/test/optimization.ini"),
                terminal_path=Path("C:/MT5/terminal64.exe"),
                data_path=custom_data_path
            )

        # Verify data_path was passed to MT5Tester constructor
        mock_tester_class.assert_called_once_with(
            terminal_path=Path("C:/MT5/terminal64.exe"),
            data_path=custom_data_path
        )


class TestCountPassesInXml(unittest.TestCase):
    """Test _count_passes_in_xml helper function."""

    def test_count_passes_with_data(self):
        """Count passes from XML with optimization results."""
        xml_content = """<?xml version="1.0"?>
<Workbook>
  <Worksheet>
    <Table>
      <Row><Cell>Pass</Cell><Cell>Result</Cell></Row>
      <Row><Cell>1</Cell><Cell>1234.56</Cell></Row>
      <Row><Cell>2</Cell><Cell>2345.67</Cell></Row>
      <Row><Cell>3</Cell><Cell>3456.78</Cell></Row>
    </Table>
  </Worksheet>
</Workbook>"""

        xml_path = Path("test_optimization.xml")
        with open(xml_path, 'w', encoding='utf-8') as f:
            f.write(xml_content)

        try:
            count = _count_passes_in_xml(xml_path)
            # 4 rows total - 1 header = 3 passes
            self.assertEqual(count, 3)
        finally:
            xml_path.unlink()

    def test_count_passes_header_only(self):
        """Return 0 when XML has only header row."""
        xml_content = """<?xml version="1.0"?>
<Workbook>
  <Worksheet>
    <Table>
      <Row><Cell>Pass</Cell><Cell>Result</Cell></Row>
    </Table>
  </Worksheet>
</Workbook>"""

        xml_path = Path("test_optimization_empty.xml")
        with open(xml_path, 'w', encoding='utf-8') as f:
            f.write(xml_content)

        try:
            count = _count_passes_in_xml(xml_path)
            self.assertEqual(count, 0)
        finally:
            xml_path.unlink()

    def test_count_passes_file_not_found(self):
        """Return 0 when XML file doesn't exist."""
        count = _count_passes_in_xml(Path("/nonexistent/file.xml"))
        self.assertEqual(count, 0)

    def test_count_passes_malformed_xml(self):
        """Return 0 for malformed XML (exception handling)."""
        xml_path = Path("test_malformed.xml")
        with open(xml_path, 'w', encoding='utf-8') as f:
            f.write("Not valid XML at all")

        try:
            # Should not raise exception, just return 0
            count = _count_passes_in_xml(xml_path)
            # Will count "<Row" occurrences, which is 0 in this case
            self.assertEqual(count, 0)
        finally:
            xml_path.unlink()


class TestValidateOptimization(unittest.TestCase):
    """Test validate_optimization convenience function."""

    @patch('ea_stress.workflow.steps.step07_optimize.run_optimization')
    def test_validate_optimization_alias(self, mock_run):
        """Validate that validate_optimization is an alias for run_optimization."""
        mock_result = OptimizationResult(
            success=True,
            passes_found=50
        )
        mock_run.return_value = mock_result

        result = validate_optimization(
            ini_path=Path("/test/opt.ini"),
            terminal_path=Path("C:/MT5/terminal64.exe"),
            data_path=Path("C:/MT5/Data"),
            timeout=1800
        )

        # Verify run_optimization was called with correct args
        mock_run.assert_called_once_with(
            ini_path=Path("/test/opt.ini"),
            terminal_path=Path("C:/MT5/terminal64.exe"),
            data_path=Path("C:/MT5/Data"),
            timeout=1800
        )

        self.assertEqual(result, mock_result)


if __name__ == '__main__':
    unittest.main()
