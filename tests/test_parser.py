"""Tests for MT5 XML report parser."""

import unittest
from pathlib import Path
from datetime import datetime
import tempfile
import xml.etree.ElementTree as ET

from ea_stress.mt5.parser import (
    MT5XMLParser,
    OptimizationPass,
    BacktestMetrics,
    parse_optimization_xml,
    parse_backtest_xml
)


class TestMT5XMLParser(unittest.TestCase):
    """Test MT5 XML report parsing."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        """Clean up test files."""
        for file in self.test_dir.glob("*.xml"):
            file.unlink()
        self.test_dir.rmdir()

    def create_optimization_xml(self, passes_data: list, suffix: str = "") -> Path:
        """Create a mock optimization XML file.

        Args:
            passes_data: List of dicts with pass metrics and parameters
            suffix: Optional suffix for filename to create unique files

        Returns:
            Path to created XML file
        """
        filename = f"optimization{suffix}.xml" if suffix else "optimization.xml"
        xml_path = self.test_dir / filename

        # Build XML structure
        root = ET.Element(
            '{urn:schemas-microsoft-com:office:spreadsheet}Workbook'
        )

        # Create worksheet
        worksheet = ET.SubElement(
            root,
            '{urn:schemas-microsoft-com:office:spreadsheet}Worksheet',
            attrib={'{urn:schemas-microsoft-com:office:spreadsheet}Name': 'Optimization Graph'}
        )

        table = ET.SubElement(worksheet, '{urn:schemas-microsoft-com:office:spreadsheet}Table')

        # Header row
        header_row = ET.SubElement(table, '{urn:schemas-microsoft-com:office:spreadsheet}Row')
        headers = [
            'Pass', 'Result', 'Profit', 'Profit Factor', 'Expected Payoff',
            'Drawdown %', 'Trades', 'Sharpe Ratio', 'Recovery Factor', 'Win %'
        ]

        # Add parameter columns from first pass
        if passes_data:
            for param_name in passes_data[0].get('parameters', {}).keys():
                headers.append(param_name)

        for header in headers:
            cell = ET.SubElement(header_row, '{urn:schemas-microsoft-com:office:spreadsheet}Cell')
            data = ET.SubElement(
                cell,
                '{urn:schemas-microsoft-com:office:spreadsheet}Data',
                attrib={'{urn:schemas-microsoft-com:office:spreadsheet}Type': 'String'}
            )
            data.text = header

        # Data rows
        for idx, pass_info in enumerate(passes_data, start=1):
            row = ET.SubElement(table, '{urn:schemas-microsoft-com:office:spreadsheet}Row')

            values = [
                str(idx),
                str(pass_info['result']),
                str(pass_info['profit']),
                str(pass_info['profit_factor']),
                str(pass_info['expected_payoff']),
                str(pass_info['max_drawdown_pct']),
                str(pass_info['total_trades']),
                str(pass_info['sharpe_ratio']),
                str(pass_info['recovery_factor']),
                str(pass_info['win_rate'])
            ]

            # Add parameter values
            for param_value in pass_info.get('parameters', {}).values():
                values.append(str(param_value))

            for value in values:
                cell = ET.SubElement(row, '{urn:schemas-microsoft-com:office:spreadsheet}Cell')
                data = ET.SubElement(
                    cell,
                    '{urn:schemas-microsoft-com:office:spreadsheet}Data',
                    attrib={'{urn:schemas-microsoft-com:office:spreadsheet}Type': 'Number'}
                )
                data.text = value

        # Write XML
        tree = ET.ElementTree(root)
        tree.write(xml_path, encoding='utf-8', xml_declaration=True)

        return xml_path

    def create_backtest_xml(self, metrics: dict) -> Path:
        """Create a mock backtest XML file.

        Args:
            metrics: Dictionary of metric name to value

        Returns:
            Path to created XML file
        """
        xml_path = self.test_dir / "backtest.xml"

        root = ET.Element(
            '{urn:schemas-microsoft-com:office:spreadsheet}Workbook'
        )

        worksheet = ET.SubElement(
            root,
            '{urn:schemas-microsoft-com:office:spreadsheet}Worksheet',
            attrib={'{urn:schemas-microsoft-com:office:spreadsheet}Name': 'Result'}
        )

        table = ET.SubElement(worksheet, '{urn:schemas-microsoft-com:office:spreadsheet}Table')

        # Add metric rows
        for key, value in metrics.items():
            row = ET.SubElement(table, '{urn:schemas-microsoft-com:office:spreadsheet}Row')

            # Key cell
            key_cell = ET.SubElement(row, '{urn:schemas-microsoft-com:office:spreadsheet}Cell')
            key_data = ET.SubElement(
                key_cell,
                '{urn:schemas-microsoft-com:office:spreadsheet}Data',
                attrib={'{urn:schemas-microsoft-com:office:spreadsheet}Type': 'String'}
            )
            key_data.text = key

            # Value cell
            value_cell = ET.SubElement(row, '{urn:schemas-microsoft-com:office:spreadsheet}Cell')
            value_data = ET.SubElement(
                value_cell,
                '{urn:schemas-microsoft-com:office:spreadsheet}Data',
                attrib={'{urn:schemas-microsoft-com:office:spreadsheet}Type': 'String'}
            )
            value_data.text = str(value)

        tree = ET.ElementTree(root)
        tree.write(xml_path, encoding='utf-8', xml_declaration=True)

        return xml_path

    def test_parse_optimization_results(self):
        """Test parsing optimization XML."""
        passes_data = [
            {
                'result': 1.25,
                'profit': 1500.0,
                'profit_factor': 1.8,
                'expected_payoff': 15.0,
                'max_drawdown_pct': 12.5,
                'total_trades': 100,
                'sharpe_ratio': 1.2,
                'recovery_factor': 7.5,
                'win_rate': 65.0,
                'parameters': {'FastMA': 10, 'SlowMA': 30}
            },
            {
                'result': 1.15,
                'profit': 1200.0,
                'profit_factor': 1.6,
                'expected_payoff': 12.0,
                'max_drawdown_pct': 15.0,
                'total_trades': 80,
                'sharpe_ratio': 1.0,
                'recovery_factor': 6.0,
                'win_rate': 60.0,
                'parameters': {'FastMA': 15, 'SlowMA': 40}
            }
        ]

        xml_path = self.create_optimization_xml(passes_data)
        parser = MT5XMLParser(xml_path)
        results = parser.parse_optimization_results(min_trades=10)

        self.assertEqual(len(results), 2)

        # Check first pass
        pass1 = results[0]
        self.assertEqual(pass1.pass_number, 1)
        self.assertAlmostEqual(pass1.result, 1.25)
        self.assertAlmostEqual(pass1.profit, 1500.0)
        self.assertAlmostEqual(pass1.profit_factor, 1.8)
        self.assertEqual(pass1.total_trades, 100)
        self.assertEqual(pass1.parameters['FastMA'], 10)
        self.assertEqual(pass1.parameters['SlowMA'], 30)

        # Check second pass
        pass2 = results[1]
        self.assertEqual(pass2.pass_number, 2)
        self.assertAlmostEqual(pass2.result, 1.15)
        self.assertEqual(pass2.total_trades, 80)

    def test_min_trades_filter(self):
        """Test filtering by minimum trades."""
        passes_data = [
            {
                'result': 1.25,
                'profit': 1500.0,
                'profit_factor': 1.8,
                'expected_payoff': 15.0,
                'max_drawdown_pct': 12.5,
                'total_trades': 100,
                'sharpe_ratio': 1.2,
                'recovery_factor': 7.5,
                'win_rate': 65.0,
                'parameters': {}
            },
            {
                'result': 1.15,
                'profit': 1200.0,
                'profit_factor': 1.6,
                'expected_payoff': 12.0,
                'max_drawdown_pct': 15.0,
                'total_trades': 5,  # Below minimum
                'sharpe_ratio': 1.0,
                'recovery_factor': 6.0,
                'win_rate': 60.0,
                'parameters': {}
            }
        ]

        xml_path = self.create_optimization_xml(passes_data)
        parser = MT5XMLParser(xml_path)
        results = parser.parse_optimization_results(min_trades=10)

        # Only first pass should be included
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].total_trades, 100)

    def test_parse_backtest_metrics(self):
        """Test parsing backtest XML."""
        metrics = {
            'Total net profit': '1500.00',
            'Profit factor': '1.80',
            'Expected payoff': '15.00',
            'Maximal drawdown': '12.5%',
            'Total trades': '100',
            'Sharpe ratio': '1.20',
            'Recovery factor': '7.50',
            'Profit trades (% of total)': '65.0%',
            'Balance': '4500.00',
            'Equity': '4500.00',
            'Gross profit': '2700.00',
            'Gross loss': '1200.00',
            'Maximum consecutive wins': '8',
            'Maximum consecutive losses': '5'
        }

        xml_path = self.create_backtest_xml(metrics)
        parser = MT5XMLParser(xml_path)
        result = parser.parse_backtest_metrics()

        self.assertIsNotNone(result)
        self.assertAlmostEqual(result.profit, 1500.0)
        self.assertAlmostEqual(result.profit_factor, 1.8)
        self.assertAlmostEqual(result.expected_payoff, 15.0)
        self.assertAlmostEqual(result.max_drawdown_pct, 12.5)
        self.assertEqual(result.total_trades, 100)
        self.assertAlmostEqual(result.sharpe_ratio, 1.2)
        self.assertAlmostEqual(result.recovery_factor, 7.5)
        self.assertAlmostEqual(result.win_rate, 65.0)
        self.assertAlmostEqual(result.balance, 4500.0)
        self.assertEqual(result.max_consecutive_wins, 8)
        self.assertEqual(result.max_consecutive_losses, 5)

    def test_merge_forward_metrics(self):
        """Test merging forward testing metrics."""
        # Create back period results
        back_passes = [
            {
                'result': 1.25,
                'profit': 1500.0,
                'profit_factor': 1.8,
                'expected_payoff': 15.0,
                'max_drawdown_pct': 12.5,
                'total_trades': 100,
                'sharpe_ratio': 1.2,
                'recovery_factor': 7.5,
                'win_rate': 65.0,
                'parameters': {'FastMA': 10, 'SlowMA': 30}
            }
        ]

        # Create forward period results (same parameters)
        forward_passes = [
            {
                'result': 1.10,
                'profit': 800.0,
                'profit_factor': 1.5,
                'expected_payoff': 10.0,
                'max_drawdown_pct': 10.0,
                'total_trades': 50,
                'sharpe_ratio': 0.9,
                'recovery_factor': 5.0,
                'win_rate': 60.0,
                'parameters': {'FastMA': 10, 'SlowMA': 30}
            }
        ]

        back_xml = self.create_optimization_xml(back_passes, "_back")
        forward_xml = self.create_optimization_xml(forward_passes, "_fwd")

        parser = MT5XMLParser(back_xml)
        back_results = parser.parse_optimization_results(min_trades=10)
        merged_results = parser.merge_forward_metrics(back_results, forward_xml)

        self.assertEqual(len(merged_results), 1)
        merged = merged_results[0]

        # Check back metrics unchanged
        self.assertAlmostEqual(merged.profit, 1500.0)
        self.assertEqual(merged.total_trades, 100)

        # Check forward metrics merged
        self.assertIsNotNone(merged.forward_profit)
        self.assertAlmostEqual(merged.forward_profit, 800.0)
        self.assertAlmostEqual(merged.forward_profit_factor, 1.5)
        self.assertEqual(merged.forward_total_trades, 50)
        self.assertAlmostEqual(merged.forward_drawdown_pct, 10.0)
        self.assertAlmostEqual(merged.forward_win_rate, 60.0)

    def test_convenience_functions(self):
        """Test convenience functions."""
        passes_data = [
            {
                'result': 1.25,
                'profit': 1500.0,
                'profit_factor': 1.8,
                'expected_payoff': 15.0,
                'max_drawdown_pct': 12.5,
                'total_trades': 100,
                'sharpe_ratio': 1.2,
                'recovery_factor': 7.5,
                'win_rate': 65.0,
                'parameters': {}
            }
        ]

        xml_path = self.create_optimization_xml(passes_data)
        results = parse_optimization_xml(xml_path, min_trades=10)

        self.assertEqual(len(results), 1)
        self.assertAlmostEqual(results[0].profit, 1500.0)

    def test_missing_file(self):
        """Test handling of missing XML file."""
        with self.assertRaises(FileNotFoundError):
            MT5XMLParser(Path("nonexistent.xml"))

    def test_empty_results(self):
        """Test parsing XML with no data rows."""
        xml_path = self.create_optimization_xml([])
        parser = MT5XMLParser(xml_path)
        results = parser.parse_optimization_results()

        self.assertEqual(len(results), 0)

    def test_parameter_type_detection(self):
        """Test automatic parameter type detection."""
        passes_data = [
            {
                'result': 1.25,
                'profit': 1500.0,
                'profit_factor': 1.8,
                'expected_payoff': 15.0,
                'max_drawdown_pct': 12.5,
                'total_trades': 100,
                'sharpe_ratio': 1.2,
                'recovery_factor': 7.5,
                'win_rate': 65.0,
                'parameters': {
                    'IntParam': 10,
                    'FloatParam': 1.5,
                    'StringParam': 'test'
                }
            }
        ]

        xml_path = self.create_optimization_xml(passes_data)
        parser = MT5XMLParser(xml_path)
        results = parser.parse_optimization_results(min_trades=10)

        self.assertEqual(len(results), 1)
        params = results[0].parameters

        # Check type preservation
        self.assertIsInstance(params['IntParam'], int)
        self.assertEqual(params['IntParam'], 10)
        self.assertIsInstance(params['FloatParam'], float)
        self.assertAlmostEqual(params['FloatParam'], 1.5)


if __name__ == '__main__':
    unittest.main()
