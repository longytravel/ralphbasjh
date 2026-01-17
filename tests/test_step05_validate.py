"""
Tests for Step 5: Validate Trades
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from pathlib import Path

from ea_stress.workflow.steps.step05_validate import (
    validate_trades,
    validate_ea,
    ValidationResult,
)
from ea_stress.mt5.tester import BacktestResult
from ea_stress.mt5.parser import BacktestMetrics
from ea_stress.config import (
    MIN_TRADES,
    SAFETY_VALIDATION_MAX_SPREAD_PIPS,
    SAFETY_VALIDATION_MAX_SLIPPAGE_PIPS,
)


class TestStep05Validate(unittest.TestCase):
    """Test Step 5: Validate Trades"""

    def setUp(self):
        """Set up test fixtures"""
        self.ex5_path = "C:/MT5/Experts/TestEA.ex5"
        self.symbol = "EURUSD"
        self.timeframe = "H1"
        self.terminal_path = "C:/MT5/terminal64.exe"
        self.workflow_id = "abc123xyz"
        self.wide_params = {
            "FastMA": 10,
            "SlowMA": 50,
            "UseFilter": True,
        }

    @patch('ea_stress.workflow.steps.step05_validate.MT5Tester')
    @patch('ea_stress.workflow.steps.step05_validate.parse_backtest_xml')
    def test_validate_trades_success_with_gate_pass(self, mock_parse, mock_tester_class):
        """Test successful validation with gate pass"""
        # Mock backtest result
        mock_tester = MagicMock()
        mock_tester_class.return_value = mock_tester

        # Create mock paths with proper methods
        mock_xml_path = MagicMock()
        mock_xml_path.exists.return_value = True
        mock_xml_path.stem = "test"
        mock_xml_path.suffix = ".xml"
        mock_fwd_path = MagicMock()
        mock_fwd_path.exists.return_value = False
        mock_xml_path.parent.__truediv__.return_value = mock_fwd_path

        backtest_result = BacktestResult(
            success=True,
            report_path=MagicMock(),
            xml_path=mock_xml_path,
            duration_seconds=120.0,
        )
        mock_tester.run_backtest.return_value = backtest_result

        # Mock XML parsing (no forward file)
        mock_parse.return_value = BacktestMetrics(
            profit=1500.00,
            profit_factor=1.8,
            total_trades=75,
            max_drawdown_pct=12.5,
            win_rate=55.0,
            sharpe_ratio=1.5,
            expected_payoff=20.0,
            recovery_factor=3.0,
        )

        result = validate_trades(
            ex5_path=self.ex5_path,
            symbol=self.symbol,
            timeframe=self.timeframe,
            terminal_path=self.terminal_path,
            wide_validation_params=self.wide_params,
            workflow_id=self.workflow_id,
        )

        # Check results
        self.assertTrue(result.passed_gate())
        self.assertEqual(result.total_trades, 75)
        self.assertEqual(result.net_profit, 1500.00)
        self.assertEqual(result.profit_factor, 1.8)
        self.assertEqual(result.max_drawdown_pct, 12.5)
        self.assertEqual(result.win_rate, 55.0)
        self.assertIsNotNone(result.report_path)
        self.assertIsNotNone(result.xml_path)
        self.assertIsNone(result.error_message)

        # Verify MT5Tester was called with correct config
        mock_tester.run_backtest.assert_called_once()
        config = mock_tester.run_backtest.call_args[0][0]
        self.assertEqual(config.symbol, "EURUSD")
        self.assertEqual(config.period, "H1")

        # Verify safety parameters were applied (loose for validation)
        self.assertEqual(
            config.inputs['EAStressSafety_MaxSpreadPips'],
            SAFETY_VALIDATION_MAX_SPREAD_PIPS
        )
        self.assertEqual(
            config.inputs['EAStressSafety_MaxSlippagePips'],
            SAFETY_VALIDATION_MAX_SLIPPAGE_PIPS
        )

    @patch('ea_stress.workflow.steps.step05_validate.MT5Tester')
    @patch('ea_stress.workflow.steps.step05_validate.parse_backtest_xml')
    def test_validate_trades_gate_fail_insufficient_trades(self, mock_parse, mock_tester_class):
        """Test validation gate fails when insufficient trades"""
        # Mock backtest result
        mock_tester = Mock()
        mock_tester_class.return_value = mock_tester

        backtest_result = BacktestResult(
            success=True,
            report_path=Path("C:/MT5/reports/test.html"),
            xml_path=Path("C:/MT5/reports/test.xml"),
            duration_seconds=120.0,
        )
        mock_tester.run_backtest.return_value = backtest_result

        # Mock XML parsing with insufficient trades
        mock_parse.return_value = BacktestMetrics(
            profit=500.00,
            profit_factor=1.5,
            total_trades=25,  # Less than MIN_TRADES (50)
            max_drawdown_pct=10.0,
            win_rate=60.0,
            sharpe_ratio=1.2,
            expected_payoff=20.0,
            recovery_factor=5.0,
        )

        # Mock Path.exists
        with patch('ea_stress.workflow.steps.step05_validate.Path') as mock_path:
            mock_path.return_value.stem = "TestEA"
            mock_path.return_value.exists.return_value = False

            result = validate_trades(
                ex5_path=self.ex5_path,
                symbol=self.symbol,
                timeframe=self.timeframe,
                terminal_path=self.terminal_path,
                wide_validation_params=self.wide_params,
                workflow_id=self.workflow_id,
                min_trades=50,
            )

        # Check gate failed
        self.assertFalse(result.passed_gate())
        self.assertEqual(result.total_trades, 25)
        self.assertIsNone(result.error_message)  # No error, just gate fail

    @patch('ea_stress.workflow.steps.step05_validate.MT5Tester')
    @patch('ea_stress.workflow.steps.step05_validate.parse_backtest_xml')
    @patch('ea_stress.workflow.steps.step05_validate.Path')
    def test_validate_trades_with_forward_metrics(self, mock_path_class, mock_parse, mock_tester_class):
        """Test validation with separate back and forward metrics"""
        # Mock backtest result
        mock_tester = Mock()
        mock_tester_class.return_value = mock_tester

        backtest_result = BacktestResult(
            success=True,
            report_path=Path("C:/MT5/reports/test.html"),
            xml_path=Path("C:/MT5/reports/test.xml"),
            duration_seconds=120.0,
        )
        mock_tester.run_backtest.return_value = backtest_result

        # Mock back metrics
        back_metrics = BacktestMetrics(
            profit=1200.00,
            profit_factor=1.9,
            total_trades=80,
            max_drawdown_pct=12.0,
            win_rate=56.0,
            sharpe_ratio=1.6,
            expected_payoff=15.0,
            recovery_factor=3.5,
        )

        # Mock forward metrics
        forward_metrics = BacktestMetrics(
            profit=300.00,
            profit_factor=1.5,
            total_trades=20,
            max_drawdown_pct=8.0,
            win_rate=50.0,
            sharpe_ratio=1.2,
            expected_payoff=15.0,
            recovery_factor=2.5,
        )

        # Mock parse to return different metrics
        mock_parse.side_effect = [back_metrics, forward_metrics]

        # Mock Path for forward file
        mock_xml_path = Mock()
        mock_xml_path.stem = "test"
        mock_xml_path.suffix = ".xml"
        mock_fwd_path = Mock()
        mock_fwd_path.exists.return_value = True
        mock_xml_path.parent.__truediv__.return_value = mock_fwd_path

        mock_path_class.return_value = mock_xml_path

        result = validate_trades(
            ex5_path=self.ex5_path,
            symbol=self.symbol,
            timeframe=self.timeframe,
            terminal_path=self.terminal_path,
            wide_validation_params=self.wide_params,
            workflow_id=self.workflow_id,
        )

        # Check that both back and forward metrics are stored
        self.assertIsNotNone(result.back_metrics)
        self.assertIsNotNone(result.forward_metrics)
        self.assertEqual(result.back_metrics.profit, 1200.00)
        self.assertEqual(result.forward_metrics.profit, 300.00)

        # Check serialization includes both
        result_dict = result.to_dict()
        self.assertIn('back_metrics', result_dict)
        self.assertIn('forward_metrics', result_dict)
        self.assertEqual(result_dict['back_metrics']['profit'], 1200.00)
        self.assertEqual(result_dict['forward_metrics']['profit'], 300.00)

    @patch('ea_stress.workflow.steps.step05_validate.MT5Tester')
    def test_validate_trades_backtest_failure(self, mock_tester_class):
        """Test validation handles backtest failure"""
        # Mock backtest failure
        mock_tester = Mock()
        mock_tester_class.return_value = mock_tester

        backtest_result = BacktestResult(
            success=False,
            error_message="Terminal crashed",
            duration_seconds=10.0,
        )
        mock_tester.run_backtest.return_value = backtest_result

        result = validate_trades(
            ex5_path=self.ex5_path,
            symbol=self.symbol,
            timeframe=self.timeframe,
            terminal_path=self.terminal_path,
            wide_validation_params=self.wide_params,
            workflow_id=self.workflow_id,
        )

        # Check failure handled
        self.assertFalse(result.passed_gate())
        self.assertEqual(result.total_trades, 0)
        self.assertIn("Terminal crashed", result.error_message)

    @patch('ea_stress.workflow.steps.step05_validate.MT5Tester')
    def test_validate_trades_missing_xml_report(self, mock_tester_class):
        """Test validation handles missing XML report"""
        # Mock backtest success but no XML
        mock_tester = Mock()
        mock_tester_class.return_value = mock_tester

        backtest_result = BacktestResult(
            success=True,
            report_path=Path("C:/MT5/reports/test.html"),
            xml_path=None,  # No XML
            duration_seconds=120.0,
        )
        mock_tester.run_backtest.return_value = backtest_result

        result = validate_trades(
            ex5_path=self.ex5_path,
            symbol=self.symbol,
            timeframe=self.timeframe,
            terminal_path=self.terminal_path,
            wide_validation_params=self.wide_params,
            workflow_id=self.workflow_id,
        )

        # Check failure handled
        self.assertFalse(result.passed_gate())
        self.assertEqual(result.total_trades, 0)
        self.assertIn("XML report not found", result.error_message)

    @patch('ea_stress.workflow.steps.step05_validate.MT5Tester')
    @patch('ea_stress.workflow.steps.step05_validate.parse_backtest_xml')
    def test_validate_trades_parse_failure(self, mock_parse, mock_tester_class):
        """Test validation handles XML parse failure"""
        # Mock backtest success
        mock_tester = Mock()
        mock_tester_class.return_value = mock_tester

        backtest_result = BacktestResult(
            success=True,
            report_path=Path("C:/MT5/reports/test.html"),
            xml_path=Path("C:/MT5/reports/test.xml"),
            duration_seconds=120.0,
        )
        mock_tester.run_backtest.return_value = backtest_result

        # Mock parse failure
        mock_parse.return_value = None

        with patch('ea_stress.workflow.steps.step05_validate.Path') as mock_path:
            mock_path.return_value.exists.return_value = True

            result = validate_trades(
                ex5_path=self.ex5_path,
                symbol=self.symbol,
                timeframe=self.timeframe,
                terminal_path=self.terminal_path,
                wide_validation_params=self.wide_params,
                workflow_id=self.workflow_id,
            )

        # Check failure handled
        self.assertFalse(result.passed_gate())
        self.assertEqual(result.total_trades, 0)
        self.assertIn("Failed to parse", result.error_message)

    @patch('ea_stress.workflow.steps.step05_validate.validate_trades')
    def test_validate_ea_convenience_function(self, mock_validate):
        """Test validate_ea convenience wrapper"""
        # Mock validate_trades
        mock_result = ValidationResult(
            total_trades=100,
            gate_passed=True,
            net_profit=2000.0,
            profit_factor=2.0,
            max_drawdown_pct=10.0,
            win_rate=60.0,
        )
        mock_validate.return_value = mock_result

        result = validate_ea(
            ex5_path=self.ex5_path,
            symbol=self.symbol,
            timeframe=self.timeframe,
            terminal_path=self.terminal_path,
            wide_validation_params=self.wide_params,
            workflow_id=self.workflow_id,
        )

        # Verify result
        self.assertEqual(result, mock_result)
        mock_validate.assert_called_once()

    def test_validation_result_to_dict(self):
        """Test ValidationResult serialization"""
        back_metrics = BacktestMetrics(
            profit=1200.00,
            profit_factor=1.9,
            total_trades=60,
            max_drawdown_pct=12.0,
            win_rate=56.0,
            sharpe_ratio=1.6,
            expected_payoff=20.0,
            recovery_factor=3.5,
        )

        forward_metrics = BacktestMetrics(
            profit=300.00,
            profit_factor=1.5,
            total_trades=15,
            max_drawdown_pct=8.0,
            win_rate=50.0,
            sharpe_ratio=1.2,
            expected_payoff=20.0,
            recovery_factor=2.5,
        )

        result = ValidationResult(
            total_trades=75,
            gate_passed=True,
            net_profit=1500.00,
            profit_factor=1.8,
            max_drawdown_pct=12.5,
            win_rate=55.0,
            back_metrics=back_metrics,
            forward_metrics=forward_metrics,
            report_path="C:/reports/test.html",
            xml_path="C:/reports/test.xml",
            from_date="2021.01.17",
            to_date="2025.01.17",
            split_date="2024.01.17",
            duration_seconds=120.0,
        )

        result_dict = result.to_dict()

        # Verify structure
        self.assertEqual(result_dict['total_trades'], 75)
        self.assertEqual(result_dict['gate_passed'], True)
        self.assertEqual(result_dict['net_profit'], 1500.00)
        self.assertIn('back_metrics', result_dict)
        self.assertIn('forward_metrics', result_dict)
        self.assertEqual(result_dict['back_metrics']['profit'], 1200.00)
        self.assertEqual(result_dict['forward_metrics']['profit'], 300.00)

    @patch('ea_stress.workflow.steps.step05_validate.MT5Tester')
    def test_validate_trades_exception_handling(self, mock_tester_class):
        """Test validation handles unexpected exceptions"""
        # Mock exception during backtest
        mock_tester = Mock()
        mock_tester_class.return_value = mock_tester
        mock_tester.run_backtest.side_effect = Exception("Unexpected error")

        result = validate_trades(
            ex5_path=self.ex5_path,
            symbol=self.symbol,
            timeframe=self.timeframe,
            terminal_path=self.terminal_path,
            wide_validation_params=self.wide_params,
            workflow_id=self.workflow_id,
        )

        # Check error handled gracefully
        self.assertFalse(result.passed_gate())
        self.assertEqual(result.total_trades, 0)
        self.assertIn("Unexpected error", result.error_message)

    @patch('ea_stress.workflow.steps.step05_validate.MT5Tester')
    @patch('ea_stress.workflow.steps.step05_validate.parse_backtest_xml')
    def test_validate_trades_custom_thresholds(self, mock_parse, mock_tester_class):
        """Test validation with custom min_trades threshold"""
        # Mock backtest result
        mock_tester = Mock()
        mock_tester_class.return_value = mock_tester

        backtest_result = BacktestResult(
            success=True,
            report_path=Path("C:/MT5/reports/test.html"),
            xml_path=Path("C:/MT5/reports/test.xml"),
            duration_seconds=120.0,
        )
        mock_tester.run_backtest.return_value = backtest_result

        # Mock XML with 30 trades
        mock_parse.return_value = BacktestMetrics(
            profit=500.00,
            profit_factor=1.6,
            total_trades=30,
            max_drawdown_pct=10.0,
            win_rate=55.0,
            sharpe_ratio=1.3,
            expected_payoff=16.67,
            recovery_factor=5.0,
        )

        with patch('ea_stress.workflow.steps.step05_validate.Path') as mock_path:
            mock_path.return_value.stem = "TestEA"
            mock_path.return_value.exists.return_value = False

            # Test with lower threshold (should pass)
            result = validate_trades(
                ex5_path=self.ex5_path,
                symbol=self.symbol,
                timeframe=self.timeframe,
                terminal_path=self.terminal_path,
                wide_validation_params=self.wide_params,
                workflow_id=self.workflow_id,
                min_trades=20,
            )

            self.assertTrue(result.passed_gate())

            # Test with higher threshold (should fail)
            result = validate_trades(
                ex5_path=self.ex5_path,
                symbol=self.symbol,
                timeframe=self.timeframe,
                terminal_path=self.terminal_path,
                wide_validation_params=self.wide_params,
                workflow_id=self.workflow_id,
                min_trades=50,
            )

            self.assertFalse(result.passed_gate())


if __name__ == '__main__':
    unittest.main()
