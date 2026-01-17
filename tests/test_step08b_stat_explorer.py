"""
Tests for Step 8B: Stat Explorer
"""

import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from ea_stress.workflow.steps.step08b_stat_explorer import (
    run_stat_explorer,
    validate_stat_explorer,
    StatExplorerResult,
    SessionStats,
    BucketStats,
    ParameterSensitivity,
    _get_session_windows,
    _compute_session_stats,
    _compute_hour_stats,
    _compute_dow_stats,
    _compute_duration_buckets,
    _compute_long_short_stats,
    _compute_profit_concentration,
    _compute_parameter_sensitivity,
    _identify_session_bias
)


class TestStatExplorerHelpers(unittest.TestCase):
    """Test helper functions."""

    def test_get_session_windows(self):
        """Test session window extraction."""
        windows = _get_session_windows("UTC")
        self.assertIn("Asia", windows)
        self.assertIn("London", windows)
        self.assertIn("NewYork", windows)
        self.assertEqual(windows["Asia"], (0, 7))
        self.assertEqual(windows["London"], (7, 16))
        self.assertEqual(windows["NewYork"], (13, 22))

    def test_compute_session_stats(self):
        """Test session statistics computation."""
        trades = [
            {'hour': 2, 'profit': 100.0},   # Asia
            {'hour': 8, 'profit': 200.0},   # London
            {'hour': 14, 'profit': 150.0},  # NewYork (overlaps London)
            {'hour': 1, 'profit': -50.0},   # Asia
        ]

        stats = _compute_session_stats(trades, "UTC")
        self.assertIn("Asia", stats)
        self.assertEqual(stats["Asia"].trades, 2)
        self.assertEqual(stats["Asia"].profit, 50.0)

        self.assertIn("London", stats)
        self.assertEqual(stats["London"].trades, 1)
        self.assertEqual(stats["London"].profit, 200.0)

    def test_compute_hour_stats(self):
        """Test hourly statistics computation."""
        trades = [
            {'hour': 8, 'profit': 100.0},
            {'hour': 8, 'profit': 50.0},
            {'hour': 9, 'profit': 200.0},
        ]

        stats = _compute_hour_stats(trades)
        self.assertIn("08", stats)
        self.assertEqual(stats["08"].trades, 2)
        self.assertEqual(stats["08"].profit, 150.0)
        self.assertIn("09", stats)
        self.assertEqual(stats["09"].trades, 1)

    def test_compute_dow_stats(self):
        """Test day-of-week statistics computation."""
        trades = [
            {'dow': 0, 'profit': 100.0},  # Monday
            {'dow': 1, 'profit': 200.0},  # Tuesday
            {'dow': 0, 'profit': 50.0},   # Monday
        ]

        stats = _compute_dow_stats(trades)
        self.assertIn("Mon", stats)
        self.assertEqual(stats["Mon"].trades, 2)
        self.assertEqual(stats["Mon"].profit, 150.0)
        self.assertIn("Tue", stats)
        self.assertEqual(stats["Tue"].trades, 1)

    def test_compute_duration_buckets(self):
        """Test duration bucket computation."""
        trades = [
            {'duration_minutes': 15, 'profit': 100.0},   # 0-30m
            {'duration_minutes': 60, 'profit': 200.0},   # 30-120m
            {'duration_minutes': 180, 'profit': 150.0},  # 120-360m
            {'duration_minutes': 500, 'profit': 250.0},  # 360m+
        ]

        buckets = _compute_duration_buckets(trades)
        self.assertEqual(buckets["0-30m"].trades, 1)
        self.assertEqual(buckets["0-30m"].profit, 100.0)
        self.assertEqual(buckets["30-120m"].trades, 1)
        self.assertEqual(buckets["120-360m"].trades, 1)
        self.assertEqual(buckets["360m+"].trades, 1)

    def test_compute_long_short_stats(self):
        """Test long vs short statistics."""
        trades = [
            {'type': 'buy', 'profit': 100.0},
            {'type': 'sell', 'profit': 200.0},
            {'type': 'long', 'profit': 50.0},
            {'type': 'short', 'profit': 150.0},
        ]

        stats = _compute_long_short_stats(trades)
        self.assertEqual(stats["long"].trades, 2)
        self.assertEqual(stats["long"].profit, 150.0)
        self.assertEqual(stats["short"].trades, 2)
        self.assertEqual(stats["short"].profit, 350.0)

    def test_compute_profit_concentration(self):
        """Test profit concentration calculation."""
        trades = [
            {'profit': 100.0},
            {'profit': 200.0},
            {'profit': 50.0},
            {'profit': 10.0},
            {'profit': 5.0},
        ]

        concentration = _compute_profit_concentration(trades)
        self.assertIn("top_20pct_trade_profit_share", concentration)
        # Top 20% = 1 trade (200.0) out of total 365.0
        expected_share = 200.0 / 365.0
        self.assertAlmostEqual(concentration["top_20pct_trade_profit_share"], expected_share, places=2)

    def test_compute_parameter_sensitivity(self):
        """Test parameter sensitivity calculation."""
        pass1_results = [
            {'result': 1000, 'params': {'FastMA': 10, 'SlowMA': 20}},
            {'result': 900, 'params': {'FastMA': 15, 'SlowMA': 25}},
            {'result': 800, 'params': {'FastMA': 20, 'SlowMA': 30}},
            {'result': 700, 'params': {'FastMA': 25, 'SlowMA': 35}},
            {'result': 600, 'params': {'FastMA': 30, 'SlowMA': 40}},
            {'result': 500, 'params': {'FastMA': 35, 'SlowMA': 45}},
            {'result': 400, 'params': {'FastMA': 40, 'SlowMA': 50}},
            {'result': 300, 'params': {'FastMA': 45, 'SlowMA': 55}},
            {'result': 200, 'params': {'FastMA': 50, 'SlowMA': 60}},
            {'result': 100, 'params': {'FastMA': 55, 'SlowMA': 65}},
        ]

        sensitivities = _compute_parameter_sensitivity(pass1_results)
        self.assertGreater(len(sensitivities), 0)
        self.assertIsInstance(sensitivities[0], ParameterSensitivity)
        # FastMA should have negative correlation (lower values = higher results)
        fast_ma_sens = next((s for s in sensitivities if s.name == 'FastMA'), None)
        self.assertIsNotNone(fast_ma_sens)
        self.assertLess(fast_ma_sens.corr_to_result, 0)

    def test_identify_session_bias(self):
        """Test session bias flag identification."""
        session_stats = {
            "Asia": SessionStats(trades=50, profit=100.0),
            "London": SessionStats(trades=100, profit=800.0),
            "NewYork": SessionStats(trades=30, profit=100.0),
        }
        total_profit = 1000.0

        flags = _identify_session_bias(session_stats, total_profit)
        self.assertGreater(len(flags), 0)
        self.assertTrue(any("London" in flag for flag in flags))


class TestStatExplorerResult(unittest.TestCase):
    """Test StatExplorerResult dataclass."""

    def test_to_dict(self):
        """Test serialization to dictionary."""
        result = StatExplorerResult(
            success=True,
            stat_explorer_path="/path/to/stat_explorer.json",
            trade_count=100,
            session_stats={
                "London": SessionStats(trades=50, profit=500.0, pf=1.5, win_rate=60.0)
            },
            parameter_sensitivity=[
                ParameterSensitivity(name="FastMA", corr_to_result=-0.8, top_decile_median=12.0)
            ]
        )

        data = result.to_dict()
        self.assertTrue(data['success'])
        self.assertEqual(data['trade_count'], 100)
        self.assertIn("London", data['session_stats'])
        self.assertEqual(data['session_stats']['London']['trades'], 50)
        self.assertEqual(len(data['parameter_sensitivity']), 1)


class TestStatExplorer(unittest.TestCase):
    """Test main Stat Explorer function."""

    def setUp(self):
        """Set up test fixtures."""
        self.pass1_results = [
            {'result': 1000, 'params': {'Pass': 1, 'FastMA': 10}},
            {'result': 900, 'params': {'Pass': 2, 'FastMA': 15}},
            {'result': 800, 'params': {'Pass': 3, 'FastMA': 20}},
        ]
        self.top_pass_params = {'FastMA': 10}
        self.ex5_path = Path("C:/MT5/Experts/test_ea.ex5")
        self.symbol = "EURUSD"
        self.timeframe = "H1"
        self.workflow_id = "abc123xyz"
        self.mt5_terminal_path = Path("C:/MT5/terminal64.exe")

    @patch('ea_stress.workflow.steps.step08b_stat_explorer.MT5Tester')
    @patch('ea_stress.workflow.steps.step08b_stat_explorer.Path.mkdir')
    def test_run_stat_explorer_success(self, mock_mkdir, mock_tester_class):
        """Test successful Stat Explorer run."""
        # Mock backtest result
        mock_result = Mock()
        mock_result.success = True
        mock_result.xml_report = Path("C:/MT5/reports/test.xml")
        mock_result.html_report = None

        mock_tester = Mock()
        mock_tester.run_backtest.return_value = mock_result
        mock_tester_class.return_value = mock_tester

        result = run_stat_explorer(
            pass1_results=self.pass1_results,
            top_pass_params=self.top_pass_params,
            ex5_path=self.ex5_path,
            symbol=self.symbol,
            timeframe=self.timeframe,
            workflow_id=self.workflow_id,
            mt5_terminal_path=self.mt5_terminal_path
        )

        self.assertTrue(result.success)
        self.assertIsNotNone(result.stat_explorer_path)
        self.assertEqual(result.trade_count, 0)  # No HTML parsing implemented
        self.assertGreater(len(result.parameter_sensitivity), 0)

    @patch('ea_stress.workflow.steps.step08b_stat_explorer.MT5Tester')
    @patch('ea_stress.workflow.steps.step08b_stat_explorer.Path.mkdir')
    def test_run_stat_explorer_with_fallback(self, mock_mkdir, mock_tester_class):
        """Test Stat Explorer with fallback to Step 5."""
        # Mock backtest failure
        mock_result = Mock()
        mock_result.success = False
        mock_result.xml_report = None

        mock_tester = Mock()
        mock_tester.run_backtest.return_value = mock_result
        mock_tester_class.return_value = mock_tester

        step5_xml = Path("C:/MT5/reports/step5.xml")

        with patch.object(Path, 'exists', return_value=True):
            result = run_stat_explorer(
                pass1_results=self.pass1_results,
                top_pass_params=self.top_pass_params,
                ex5_path=self.ex5_path,
                symbol=self.symbol,
                timeframe=self.timeframe,
                workflow_id=self.workflow_id,
                mt5_terminal_path=self.mt5_terminal_path,
                step5_xml_path=step5_xml
            )

        self.assertTrue(result.success)
        self.assertTrue(result.fallback_to_step5)

    @patch('ea_stress.workflow.steps.step08b_stat_explorer.MT5Tester')
    @patch('ea_stress.workflow.steps.step08b_stat_explorer.Path.mkdir')
    def test_run_stat_explorer_no_fallback(self, mock_mkdir, mock_tester_class):
        """Test Stat Explorer failure with no fallback."""
        # Mock backtest failure
        mock_result = Mock()
        mock_result.success = False
        mock_result.xml_report = None

        mock_tester = Mock()
        mock_tester.run_backtest.return_value = mock_result
        mock_tester_class.return_value = mock_tester

        result = run_stat_explorer(
            pass1_results=self.pass1_results,
            top_pass_params=self.top_pass_params,
            ex5_path=self.ex5_path,
            symbol=self.symbol,
            timeframe=self.timeframe,
            workflow_id=self.workflow_id,
            mt5_terminal_path=self.mt5_terminal_path,
            step5_xml_path=None
        )

        self.assertFalse(result.success)
        self.assertIn("no Step 5 fallback", result.error_message)

    @patch('ea_stress.workflow.steps.step08b_stat_explorer.MT5Tester')
    @patch('ea_stress.workflow.steps.step08b_stat_explorer.Path.mkdir')
    def test_run_stat_explorer_exception(self, mock_mkdir, mock_tester_class):
        """Test Stat Explorer with exception."""
        mock_tester_class.side_effect = Exception("MT5 error")

        result = run_stat_explorer(
            pass1_results=self.pass1_results,
            top_pass_params=self.top_pass_params,
            ex5_path=self.ex5_path,
            symbol=self.symbol,
            timeframe=self.timeframe,
            workflow_id=self.workflow_id,
            mt5_terminal_path=self.mt5_terminal_path
        )

        self.assertFalse(result.success)
        self.assertIn("Stat Explorer error", result.error_message)

    def test_validate_stat_explorer(self):
        """Test convenience function."""
        with patch('ea_stress.workflow.steps.step08b_stat_explorer.run_stat_explorer') as mock_run:
            mock_run.return_value = StatExplorerResult(success=True)

            result = validate_stat_explorer(
                pass1_results=self.pass1_results,
                top_pass_params=self.top_pass_params,
                ex5_path=self.ex5_path,
                symbol=self.symbol,
                timeframe=self.timeframe,
                workflow_id=self.workflow_id,
                mt5_terminal_path=self.mt5_terminal_path
            )

            self.assertTrue(result.success)
            mock_run.assert_called_once()


if __name__ == '__main__':
    unittest.main()
