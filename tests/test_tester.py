"""Tests for MT5 Strategy Tester wrapper."""

import unittest
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import tempfile
import shutil

from ea_stress.mt5.tester import (
    MT5Tester,
    BacktestConfig,
    BacktestResult,
    OptimizationMode,
    OptimizationCriterion,
    ForwardMode,
    run_backtest
)


class TestBacktestConfig(unittest.TestCase):
    """Test BacktestConfig dataclass."""

    def test_minimal_config(self):
        """Test minimal configuration."""
        config = BacktestConfig(
            expert="TestEA.ex5",
            symbol="EURUSD",
            period="H1",
            from_date=datetime(2020, 1, 1),
            to_date=datetime(2024, 1, 1)
        )

        self.assertEqual(config.expert, "TestEA.ex5")
        self.assertEqual(config.symbol, "EURUSD")
        self.assertEqual(config.period, "H1")
        self.assertEqual(config.model, 1)  # Default
        self.assertEqual(config.deposit, 3000.0)  # Default
        self.assertEqual(config.optimization, OptimizationMode.DISABLED)

    def test_config_with_inputs(self):
        """Test configuration with expert inputs."""
        config = BacktestConfig(
            expert="TestEA.ex5",
            symbol="EURUSD",
            period="H1",
            from_date=datetime(2020, 1, 1),
            to_date=datetime(2024, 1, 1),
            inputs={"Lots": 0.1, "TakeProfit": 100, "StopLoss": 50}
        )

        self.assertEqual(len(config.inputs), 3)
        self.assertEqual(config.inputs["Lots"], 0.1)
        self.assertEqual(config.inputs["TakeProfit"], 100)

    def test_config_with_optimization_ranges(self):
        """Test configuration with optimization ranges."""
        config = BacktestConfig(
            expert="TestEA.ex5",
            symbol="EURUSD",
            period="H1",
            from_date=datetime(2020, 1, 1),
            to_date=datetime(2024, 1, 1),
            optimization=OptimizationMode.GENETIC,
            optimization_ranges={
                "TakeProfit": (50, 10, 200, "Y"),
                "StopLoss": (20, 5, 100, "Y")
            }
        )

        self.assertEqual(config.optimization, OptimizationMode.GENETIC)
        self.assertEqual(len(config.optimization_ranges), 2)
        self.assertEqual(config.optimization_ranges["TakeProfit"], (50, 10, 200, "Y"))


class TestMT5Tester(unittest.TestCase):
    """Test MT5Tester class."""

    def setUp(self):
        """Set up test fixtures."""
        # Create temporary directory structure
        self.temp_dir = Path(tempfile.mkdtemp())
        self.terminal_path = self.temp_dir / "terminal64.exe"
        self.data_path = self.temp_dir / "data"

        # Create mock terminal executable
        self.terminal_path.touch()

        # Create data directory structure
        self.tester_dir = self.data_path / "MQL5" / "Profiles" / "Tester"
        self.tester_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir)

    def test_init_with_data_path(self):
        """Test initialization with explicit data path."""
        tester = MT5Tester(self.terminal_path, self.data_path)

        self.assertEqual(tester.terminal_path, self.terminal_path)
        self.assertEqual(tester.data_path, self.data_path)
        self.assertTrue(tester.tester_dir.exists())

    def test_init_without_data_path(self):
        """Test initialization with auto-detected data path."""
        # Create MQL5 directory in terminal path (portable install)
        (self.terminal_path.parent / "MQL5").mkdir()

        tester = MT5Tester(self.terminal_path)

        self.assertEqual(tester.terminal_path, self.terminal_path)
        self.assertEqual(tester.data_path, self.terminal_path.parent)

    def test_init_invalid_terminal(self):
        """Test initialization with invalid terminal path."""
        with self.assertRaises(FileNotFoundError):
            MT5Tester(self.temp_dir / "nonexistent.exe")

    def test_generate_ini_basic(self):
        """Test INI generation with basic configuration."""
        tester = MT5Tester(self.terminal_path, self.data_path)

        config = BacktestConfig(
            expert="TestEA.ex5",
            symbol="EURUSD",
            period="H1",
            from_date=datetime(2020, 1, 1),
            to_date=datetime(2024, 1, 1)
        )

        ini_path = tester.generate_ini(config)

        self.assertTrue(ini_path.exists())
        content = ini_path.read_text()

        # Check key settings
        self.assertIn("Expert=TestEA.ex5", content)
        self.assertIn("Symbol=EURUSD", content)
        self.assertIn("Period=H1", content)
        self.assertIn("FromDate=2020.01.01", content)
        self.assertIn("ToDate=2024.01.01", content)
        self.assertIn("Model=1", content)
        self.assertIn("Deposit=3000.00", content)

    def test_generate_ini_with_inputs(self):
        """Test INI generation with expert inputs."""
        tester = MT5Tester(self.terminal_path, self.data_path)

        config = BacktestConfig(
            expert="TestEA.ex5",
            symbol="EURUSD",
            period="H1",
            from_date=datetime(2020, 1, 1),
            to_date=datetime(2024, 1, 1),
            inputs={
                "Lots": 0.1,
                "TakeProfit": 100,
                "StopLoss": 50,
                "UseMartingale": True
            }
        )

        ini_path = tester.generate_ini(config)
        content = ini_path.read_text()

        # Check inputs section
        self.assertIn("[TesterInputs]", content)
        self.assertIn("Lots=0.1", content)
        self.assertIn("TakeProfit=100", content)
        self.assertIn("StopLoss=50", content)
        self.assertIn("UseMartingale=true", content)

    def test_generate_ini_with_optimization(self):
        """Test INI generation with optimization ranges."""
        tester = MT5Tester(self.terminal_path, self.data_path)

        config = BacktestConfig(
            expert="TestEA.ex5",
            symbol="EURUSD",
            period="H1",
            from_date=datetime(2020, 1, 1),
            to_date=datetime(2024, 1, 1),
            optimization=OptimizationMode.GENETIC,
            optimization_criterion=OptimizationCriterion.CUSTOM,
            inputs={"TakeProfit": 100},
            optimization_ranges={
                "TakeProfit": (50, 10, 200, "Y"),
                "StopLoss": (20, 5, 100, "Y")
            }
        )

        ini_path = tester.generate_ini(config)
        content = ini_path.read_text()

        # Check optimization settings
        self.assertIn("Optimization=2", content)  # Genetic
        self.assertIn("OptimizationCriterion=6", content)  # Custom

        # Check optimization ranges format
        self.assertIn("TakeProfit=100||50||10||200||Y", content)
        self.assertIn("StopLoss=", content)
        self.assertIn("||20||5||100||Y", content)

    def test_generate_ini_with_forward_testing(self):
        """Test INI generation with forward testing."""
        tester = MT5Tester(self.terminal_path, self.data_path)

        forward_date = datetime(2023, 1, 1)
        config = BacktestConfig(
            expert="TestEA.ex5",
            symbol="EURUSD",
            period="H1",
            from_date=datetime(2020, 1, 1),
            to_date=datetime(2024, 1, 1),
            forward_mode=ForwardMode.DATE_BASED,
            forward_date=forward_date
        )

        ini_path = tester.generate_ini(config)
        content = ini_path.read_text()

        self.assertIn("ForwardMode=2", content)  # Date-based
        self.assertIn("ForwardDate=2023.01.01", content)

    def test_format_value(self):
        """Test value formatting for INI file."""
        tester = MT5Tester(self.terminal_path, self.data_path)

        # Boolean
        self.assertEqual(tester._format_value(True), "true")
        self.assertEqual(tester._format_value(False), "false")

        # Float
        self.assertEqual(tester._format_value(0.1), "0.1")
        self.assertEqual(tester._format_value(100.0), "100")

        # String
        self.assertEqual(tester._format_value("EURUSD"), "EURUSD")

        # Integer
        self.assertEqual(tester._format_value(100), "100")

    @patch('subprocess.run')
    def test_run_backtest_success(self, mock_run):
        """Test successful backtest execution."""
        tester = MT5Tester(self.terminal_path, self.data_path)

        # Create mock report files
        report_path = self.tester_dir / "TestEA_report.htm"
        xml_path = self.tester_dir / "TestEA_report.xml"
        report_path.touch()
        xml_path.touch()

        # Mock subprocess result
        mock_run.return_value = Mock(stdout="Success", stderr="", returncode=0)

        config = BacktestConfig(
            expert="TestEA.ex5",
            symbol="EURUSD",
            period="H1",
            from_date=datetime(2020, 1, 1),
            to_date=datetime(2024, 1, 1)
        )

        result = tester.run_backtest(config, timeout=10)

        self.assertTrue(result.success)
        self.assertIsNotNone(result.report_path)
        self.assertIsNotNone(result.xml_path)
        self.assertGreater(result.duration_seconds, 0)

    @patch('subprocess.run')
    def test_run_backtest_no_report(self, mock_run):
        """Test backtest execution with missing report."""
        tester = MT5Tester(self.terminal_path, self.data_path)

        # Mock subprocess result (no report files created)
        mock_run.return_value = Mock(stdout="", stderr="", returncode=0)

        config = BacktestConfig(
            expert="TestEA.ex5",
            symbol="EURUSD",
            period="H1",
            from_date=datetime(2020, 1, 1),
            to_date=datetime(2024, 1, 1)
        )

        result = tester.run_backtest(config, timeout=10)

        self.assertFalse(result.success)
        self.assertIn("Report files not generated", result.error_message)

    @patch('subprocess.run')
    def test_run_backtest_timeout(self, mock_run):
        """Test backtest timeout handling."""
        import subprocess
        tester = MT5Tester(self.terminal_path, self.data_path)

        # Mock timeout exception
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 10)

        config = BacktestConfig(
            expert="TestEA.ex5",
            symbol="EURUSD",
            period="H1",
            from_date=datetime(2020, 1, 1),
            to_date=datetime(2024, 1, 1)
        )

        result = tester.run_backtest(config, timeout=10)

        self.assertFalse(result.success)
        self.assertIn("timed out", result.error_message)

    @patch('subprocess.run')
    def test_run_optimization(self, mock_run):
        """Test optimization execution."""
        tester = MT5Tester(self.terminal_path, self.data_path)

        # Create mock report files
        report_path = self.tester_dir / "TestEA_report.htm"
        report_path.touch()

        mock_run.return_value = Mock(stdout="Success", stderr="", returncode=0)

        config = BacktestConfig(
            expert="TestEA.ex5",
            symbol="EURUSD",
            period="H1",
            from_date=datetime(2020, 1, 1),
            to_date=datetime(2024, 1, 1),
            optimization_ranges={
                "TakeProfit": (50, 10, 200, "Y")
            }
        )

        result = tester.run_optimization(config, timeout=10)

        # Optimization should be automatically enabled
        self.assertTrue(result.success)

    def test_find_report_files_timeout(self):
        """Test report file search timeout."""
        tester = MT5Tester(self.terminal_path, self.data_path)

        config = BacktestConfig(
            expert="NonExistentEA.ex5",
            symbol="EURUSD",
            period="H1",
            from_date=datetime(2020, 1, 1),
            to_date=datetime(2024, 1, 1)
        )

        # Should timeout quickly
        report, xml = tester._find_report_files(config, max_wait=1)

        self.assertIsNone(report)
        self.assertIsNone(xml)


class TestConvenienceFunction(unittest.TestCase):
    """Test convenience function."""

    @patch('ea_stress.mt5.tester.MT5Tester')
    def test_run_backtest_convenience(self, mock_tester_class):
        """Test run_backtest convenience function."""
        # Mock tester instance
        mock_tester = Mock()
        mock_tester.run_backtest.return_value = BacktestResult(success=True)
        mock_tester_class.return_value = mock_tester

        terminal = Path("C:/MT5/terminal64.exe")
        result = run_backtest(
            terminal_path=terminal,
            expert="TestEA.ex5",
            symbol="EURUSD",
            period="H1",
            from_date=datetime(2020, 1, 1),
            to_date=datetime(2024, 1, 1),
            inputs={"Lots": 0.1}
        )

        self.assertTrue(result.success)
        mock_tester_class.assert_called_once_with(terminal)
        mock_tester.run_backtest.assert_called_once()


if __name__ == "__main__":
    unittest.main()
