"""
Tests for Step 6: Create Optimization INI (Pass 1 - Wide)
"""

import unittest
from pathlib import Path
import tempfile
import shutil
from datetime import datetime, timedelta

from ea_stress.workflow.steps.step06_ini import (
    create_optimization_ini,
    OptimizationINIResult,
    validate_ini_generation,
    _timeframe_to_minutes,
)


class TestStep06OptimizationINI(unittest.TestCase):
    """Test suite for Step 6: Create Optimization INI"""

    def setUp(self):
        """Set up test fixtures"""
        self.temp_dir = tempfile.mkdtemp()
        self.output_dir = Path(self.temp_dir) / "ini_output"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Create a dummy .ex5 file
        self.ex5_path = Path(self.temp_dir) / "TestEA.ex5"
        self.ex5_path.write_text("dummy ex5 content", encoding="utf-8")

        # Sample optimization ranges from Step 4
        self.optimization_ranges = [
            {
                "name": "FastMAPeriod",
                "optimize": True,
                "start": 10,
                "step": 5,
                "stop": 50,
                "default": 20,
            },
            {
                "name": "SlowMAPeriod",
                "optimize": True,
                "start": 30,
                "step": 10,
                "stop": 100,
                "default": 50,
            },
            {
                "name": "StopLoss",
                "optimize": False,
                "default": 100,
            },
            {
                "name": "TakeProfit",
                "optimize": False,
                "default": 200,
            },
        ]

        self.workflow_id = "abc123xyz789"

    def tearDown(self):
        """Clean up test fixtures"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_create_ini_success(self):
        """Test successful INI creation"""
        result = create_optimization_ini(
            ex5_path=str(self.ex5_path),
            symbol="EURUSD",
            timeframe="H1",
            workflow_id=self.workflow_id,
            optimization_ranges=self.optimization_ranges,
            output_dir=str(self.output_dir),
        )

        self.assertTrue(result.success)
        self.assertIsNone(result.error_message)
        self.assertEqual(result.param_count, 4)
        self.assertEqual(result.optimize_count, 2)
        self.assertEqual(result.fixed_count, 2)
        self.assertTrue(Path(result.ini_path).exists())
        self.assertIn("S6_opt1", result.report_name)
        self.assertIn("EURUSD", result.report_name)
        self.assertIn("H1", result.report_name)
        self.assertIn(self.workflow_id[:8], result.report_name)

    def test_ini_content_structure(self):
        """Test INI file content structure"""
        result = create_optimization_ini(
            ex5_path=str(self.ex5_path),
            symbol="GBPJPY",
            timeframe="M15",
            workflow_id=self.workflow_id,
            optimization_ranges=self.optimization_ranges,
            output_dir=str(self.output_dir),
        )

        self.assertTrue(result.success)

        # Read INI content
        ini_content = Path(result.ini_path).read_text(encoding="utf-8")

        # Check [Tester] section
        self.assertIn("[Tester]", ini_content)
        self.assertIn("Expert=TestEA.ex5", ini_content)
        self.assertIn("Symbol=GBPJPY", ini_content)
        self.assertIn("Period=15", ini_content)  # M15 = 15 minutes
        self.assertIn("ForwardMode=2", ini_content)  # Date-based
        self.assertIn("Optimization=2", ini_content)  # Genetic
        self.assertIn("OptimizationCriterion=6", ini_content)  # Custom OnTester
        self.assertIn("Deposit=3000", ini_content)
        self.assertIn("Currency=GBP", ini_content)
        self.assertIn("Leverage=100", ini_content)
        self.assertIn("Visual=0", ini_content)
        self.assertIn("ShutdownTerminal=1", ini_content)

        # Check [TesterInputs] section
        self.assertIn("[TesterInputs]", ini_content)
        self.assertIn("FastMAPeriod=20||10||5||50||Y", ini_content)  # Optimized
        self.assertIn("SlowMAPeriod=50||30||10||100||Y", ini_content)  # Optimized
        self.assertIn("StopLoss=100||0||0||0||N", ini_content)  # Fixed
        self.assertIn("TakeProfit=200||0||0||0||N", ini_content)  # Fixed

    def test_date_calculations(self):
        """Test backtest date calculations"""
        result = create_optimization_ini(
            ex5_path=str(self.ex5_path),
            symbol="EURUSD",
            timeframe="H1",
            workflow_id=self.workflow_id,
            optimization_ranges=self.optimization_ranges,
            output_dir=str(self.output_dir),
            backtest_years=4,
            in_sample_years=3,
        )

        self.assertTrue(result.success)

        # Parse dates
        start_date = datetime.strptime(result.start_date, "%Y.%m.%d")
        end_date = datetime.strptime(result.end_date, "%Y.%m.%d")
        forward_date = datetime.strptime(result.forward_date, "%Y.%m.%d")

        # Check date ranges (approximate due to time passing during test)
        total_days = (end_date - start_date).days
        self.assertGreater(total_days, 4 * 365 - 10)  # ~4 years
        self.assertLess(total_days, 4 * 365 + 10)

        forward_days = (end_date - forward_date).days
        self.assertGreater(forward_days, 365 - 10)  # ~1 year
        self.assertLess(forward_days, 365 + 10)

    def test_report_name_format(self):
        """Test deterministic report name format per PRD Section 8"""
        result = create_optimization_ini(
            ex5_path=str(self.ex5_path),
            symbol="USDJPY",
            timeframe="H4",
            workflow_id="workflow123456789",
            optimization_ranges=self.optimization_ranges,
            output_dir=str(self.output_dir),
            ea_name="MyCustomEA",
        )

        self.assertTrue(result.success)

        # Pattern: <ea_stem>_S6_opt1_<symbol>_<timeframe>_<workflow_id[:8]>
        expected = "MyCustomEA_S6_opt1_USDJPY_H4_workflow"
        self.assertEqual(result.report_name, expected)

    def test_ex5_not_found(self):
        """Test error when EX5 file doesn't exist"""
        result = create_optimization_ini(
            ex5_path="/nonexistent/path/EA.ex5",
            symbol="EURUSD",
            timeframe="H1",
            workflow_id=self.workflow_id,
            optimization_ranges=self.optimization_ranges,
            output_dir=str(self.output_dir),
        )

        self.assertFalse(result.success)
        self.assertIn("not found", result.error_message.lower())
        self.assertEqual(result.param_count, 0)

    def test_empty_optimization_ranges(self):
        """Test error when no optimization ranges provided"""
        result = create_optimization_ini(
            ex5_path=str(self.ex5_path),
            symbol="EURUSD",
            timeframe="H1",
            workflow_id=self.workflow_id,
            optimization_ranges=[],
            output_dir=str(self.output_dir),
        )

        self.assertFalse(result.success)
        self.assertIn("No optimization ranges", result.error_message)

    def test_all_fixed_parameters(self):
        """Test INI with all fixed parameters (no optimization)"""
        fixed_ranges = [
            {"name": "Param1", "optimize": False, "default": 10},
            {"name": "Param2", "optimize": False, "default": 20},
        ]

        result = create_optimization_ini(
            ex5_path=str(self.ex5_path),
            symbol="EURUSD",
            timeframe="H1",
            workflow_id=self.workflow_id,
            optimization_ranges=fixed_ranges,
            output_dir=str(self.output_dir),
        )

        self.assertTrue(result.success)
        self.assertEqual(result.param_count, 2)
        self.assertEqual(result.optimize_count, 0)
        self.assertEqual(result.fixed_count, 2)

        ini_content = Path(result.ini_path).read_text(encoding="utf-8")
        self.assertIn("Param1=10||0||0||0||N", ini_content)
        self.assertIn("Param2=20||0||0||0||N", ini_content)

    def test_all_optimized_parameters(self):
        """Test INI with all optimized parameters"""
        optimized_ranges = [
            {"name": "Param1", "optimize": True, "start": 1, "step": 1, "stop": 10, "default": 5},
            {"name": "Param2", "optimize": True, "start": 10, "step": 5, "stop": 50, "default": 20},
        ]

        result = create_optimization_ini(
            ex5_path=str(self.ex5_path),
            symbol="EURUSD",
            timeframe="H1",
            workflow_id=self.workflow_id,
            optimization_ranges=optimized_ranges,
            output_dir=str(self.output_dir),
        )

        self.assertTrue(result.success)
        self.assertEqual(result.param_count, 2)
        self.assertEqual(result.optimize_count, 2)
        self.assertEqual(result.fixed_count, 0)

        ini_content = Path(result.ini_path).read_text(encoding="utf-8")
        self.assertIn("Param1=5||1||1||10||Y", ini_content)
        self.assertIn("Param2=20||10||5||50||Y", ini_content)

    def test_custom_settings(self):
        """Test INI with custom backtest settings"""
        result = create_optimization_ini(
            ex5_path=str(self.ex5_path),
            symbol="EURUSD",
            timeframe="H1",
            workflow_id=self.workflow_id,
            optimization_ranges=self.optimization_ranges,
            output_dir=str(self.output_dir),
            backtest_years=5,
            in_sample_years=4,
            model=0,  # Tick mode
            execution_latency_ms=50,
            deposit=10000,
            currency="USD",
            leverage=500,
            optimization_criterion=1,  # Balance
        )

        self.assertTrue(result.success)

        ini_content = Path(result.ini_path).read_text(encoding="utf-8")
        self.assertIn("Model=0", ini_content)
        self.assertIn("ExecutionMode=50", ini_content)
        self.assertIn("Deposit=10000", ini_content)
        self.assertIn("Currency=USD", ini_content)
        self.assertIn("Leverage=500", ini_content)
        self.assertIn("OptimizationCriterion=1", ini_content)

        # Check metadata
        self.assertEqual(result.metadata["backtest_years"], 5)
        self.assertEqual(result.metadata["in_sample_years"], 4)
        self.assertEqual(result.metadata["forward_years"], 1)

    def test_timeframe_to_minutes(self):
        """Test timeframe conversion to minutes"""
        self.assertEqual(_timeframe_to_minutes("M1"), 1)
        self.assertEqual(_timeframe_to_minutes("M5"), 5)
        self.assertEqual(_timeframe_to_minutes("M15"), 15)
        self.assertEqual(_timeframe_to_minutes("M30"), 30)
        self.assertEqual(_timeframe_to_minutes("H1"), 60)
        self.assertEqual(_timeframe_to_minutes("H4"), 240)
        self.assertEqual(_timeframe_to_minutes("D1"), 1440)
        self.assertEqual(_timeframe_to_minutes("W1"), 10080)
        self.assertEqual(_timeframe_to_minutes("MN1"), 43200)
        self.assertEqual(_timeframe_to_minutes("UNKNOWN"), 60)  # Default

    def test_validate_ini_generation_success(self):
        """Test validation of successful INI generation"""
        result = create_optimization_ini(
            ex5_path=str(self.ex5_path),
            symbol="EURUSD",
            timeframe="H1",
            workflow_id=self.workflow_id,
            optimization_ranges=self.optimization_ranges,
            output_dir=str(self.output_dir),
        )

        self.assertTrue(validate_ini_generation(result))

    def test_validate_ini_generation_failure(self):
        """Test validation of failed INI generation"""
        failed_result = OptimizationINIResult(
            ini_path="",
            report_name="",
            param_count=0,
            optimize_count=0,
            fixed_count=0,
            start_date="",
            end_date="",
            forward_date="",
            success=False,
            error_message="Test error",
        )

        self.assertFalse(validate_ini_generation(failed_result))

    def test_to_dict_serialization(self):
        """Test JSON serialization"""
        result = create_optimization_ini(
            ex5_path=str(self.ex5_path),
            symbol="EURUSD",
            timeframe="H1",
            workflow_id=self.workflow_id,
            optimization_ranges=self.optimization_ranges,
            output_dir=str(self.output_dir),
        )

        result_dict = result.to_dict()

        self.assertIsInstance(result_dict, dict)
        self.assertIn("ini_path", result_dict)
        self.assertIn("report_name", result_dict)
        self.assertIn("param_count", result_dict)
        self.assertIn("optimize_count", result_dict)
        self.assertIn("fixed_count", result_dict)
        self.assertIn("start_date", result_dict)
        self.assertIn("end_date", result_dict)
        self.assertIn("forward_date", result_dict)
        self.assertIn("success", result_dict)
        self.assertIn("metadata", result_dict)
        self.assertTrue(result_dict["success"])
        self.assertEqual(result_dict["param_count"], 4)

    def test_output_directory_creation(self):
        """Test that output directory is created if it doesn't exist"""
        new_output_dir = Path(self.temp_dir) / "new_dir" / "nested" / "output"

        result = create_optimization_ini(
            ex5_path=str(self.ex5_path),
            symbol="EURUSD",
            timeframe="H1",
            workflow_id=self.workflow_id,
            optimization_ranges=self.optimization_ranges,
            output_dir=str(new_output_dir),
        )

        self.assertTrue(result.success)
        self.assertTrue(new_output_dir.exists())
        self.assertTrue(Path(result.ini_path).exists())


if __name__ == "__main__":
    unittest.main()
