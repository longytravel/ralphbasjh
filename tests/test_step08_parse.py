"""Tests for Step 8: Parse Optimization Results."""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import tempfile
import xml.etree.ElementTree as ET

from ea_stress.workflow.steps.step08_parse import (
    parse_optimization_results,
    validate_parse_results,
    ParseResult,
    _optimization_pass_to_dict
)
from ea_stress.mt5.parser import OptimizationPass
from ea_stress.config import ONTESTER_MIN_TRADES


class TestParseResult:
    """Test ParseResult dataclass."""

    def test_gate_passed_with_valid_passes(self):
        """Test gate passes when valid_passes >= 1."""
        result = ParseResult(
            success=True,
            xml_path=Path("test.xml"),
            valid_passes=5,
            total_passes=10
        )
        assert result.passed_gate() is True
        assert result.gate_passed is False  # Not auto-set, must be set explicitly

    def test_gate_failed_no_passes(self):
        """Test gate fails when valid_passes == 0."""
        result = ParseResult(
            success=True,
            xml_path=Path("test.xml"),
            valid_passes=0,
            total_passes=10
        )
        assert result.passed_gate() is False

    def test_to_dict_serialization(self):
        """Test conversion to dictionary."""
        result = ParseResult(
            success=True,
            xml_path=Path("C:/test/test.xml"),
            valid_passes=3,
            total_passes=5,
            passes=[{"pass_number": 1, "profit": 100.0}],
            gate_passed=True,
            min_trades_threshold=10,
            forward_merged=True,
            forward_xml_path=Path("C:/test/test_fwd.xml"),
            error_message=None
        )
        d = result.to_dict()
        assert d["success"] is True
        assert str(Path(d["xml_path"])) == str(Path("C:/test/test.xml"))
        assert d["valid_passes"] == 3
        assert d["total_passes"] == 5
        assert len(d["passes"]) == 1
        assert d["gate_passed"] is True
        assert d["forward_merged"] is True
        assert str(Path(d["forward_xml_path"])) == str(Path("C:/test/test_fwd.xml"))


class TestOptimizationPassToDict:
    """Test _optimization_pass_to_dict helper."""

    def test_convert_pass_without_forward(self):
        """Test converting pass without forward metrics."""
        opt_pass = OptimizationPass(
            pass_number=1,
            result=1234.56,
            profit=500.0,
            profit_factor=1.8,
            expected_payoff=10.5,
            max_drawdown_pct=15.2,
            total_trades=50,
            sharpe_ratio=1.45,
            recovery_factor=3.2,
            win_rate=55.0,
            parameters={"Param1": 10, "Param2": 20}
        )
        d = _optimization_pass_to_dict(opt_pass)
        assert d["result"] == 1234.56
        assert d["profit"] == 500.0
        assert d["source"] == "pass1"
        assert d["back"]["profit"] == 500.0
        assert d["params"]["Pass"] == 1
        assert d["params"]["Param1"] == 10
        assert "forward" not in d

    def test_convert_pass_with_forward(self):
        """Test converting pass with forward metrics."""
        opt_pass = OptimizationPass(
            pass_number=2,
            result=1500.0,
            profit=600.0,
            profit_factor=1.9,
            expected_payoff=12.0,
            max_drawdown_pct=18.0,
            total_trades=60,
            sharpe_ratio=1.55,
            recovery_factor=3.5,
            win_rate=58.0,
            parameters={"Param1": 15},
            forward_profit=150.0,
            forward_profit_factor=1.5,
            forward_total_trades=20,
            forward_drawdown_pct=12.0,
            forward_win_rate=52.0
        )
        d = _optimization_pass_to_dict(opt_pass)
        assert d["forward"]["profit"] == 150.0
        assert d["forward"]["profit_factor"] == 1.5
        assert d["forward"]["total_trades"] == 20
        assert d["params"]["Forward Result"] == 150.0


class TestParseOptimizationResults:
    """Test parse_optimization_results function."""

    def test_xml_file_not_found(self):
        """Test handling of missing XML file."""
        result = parse_optimization_results(Path("nonexistent.xml"))
        assert result.success is False
        assert result.valid_passes == 0
        assert result.total_passes == 0
        assert result.passed_gate() is False
        assert "not found" in result.error_message.lower()

    @patch('ea_stress.workflow.steps.step08_parse.MT5XMLParser')
    def test_successful_parse_with_valid_passes(self, mock_parser_class):
        """Test successful parsing with valid passes."""
        # Create temporary XML file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            f.write("<xml></xml>")
            xml_path = Path(f.name)

        try:
            # Mock parser
            mock_parser = Mock()
            mock_parser_class.return_value = mock_parser

            # Create mock passes
            pass1 = OptimizationPass(
                pass_number=1, result=1000.0, profit=500.0, profit_factor=1.8,
                expected_payoff=10.0, max_drawdown_pct=15.0, total_trades=50,
                sharpe_ratio=1.5, recovery_factor=3.0, win_rate=55.0,
                parameters={"Param1": 10}
            )
            pass2 = OptimizationPass(
                pass_number=2, result=1200.0, profit=600.0, profit_factor=2.0,
                expected_payoff=12.0, max_drawdown_pct=18.0, total_trades=60,
                sharpe_ratio=1.6, recovery_factor=3.5, win_rate=58.0,
                parameters={"Param1": 15}
            )

            # Mock parse_optimization_results to return passes for min_trades filter
            # and all passes for total count
            def parse_side_effect(min_trades=10):
                if min_trades == 0:
                    return [pass1, pass2]
                else:
                    return [pass1, pass2]

            mock_parser.parse_optimization_results.side_effect = parse_side_effect
            mock_parser.merge_forward_metrics.return_value = [pass1, pass2]

            result = parse_optimization_results(xml_path, min_trades=10)

            assert result.success is True
            assert result.valid_passes == 2
            assert result.total_passes == 2
            assert result.passed_gate() is True
            assert len(result.passes) == 2
            assert result.error_message is None

        finally:
            xml_path.unlink()

    @patch('ea_stress.workflow.steps.step08_parse.MT5XMLParser')
    def test_parse_with_no_valid_passes(self, mock_parser_class):
        """Test parsing when no passes meet minimum trades threshold."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            f.write("<xml></xml>")
            xml_path = Path(f.name)

        try:
            mock_parser = Mock()
            mock_parser_class.return_value = mock_parser

            # No passes meet threshold, but 3 total passes
            low_trade_pass = OptimizationPass(
                pass_number=1, result=100.0, profit=50.0, profit_factor=1.2,
                expected_payoff=5.0, max_drawdown_pct=10.0, total_trades=5,
                sharpe_ratio=1.0, recovery_factor=2.0, win_rate=50.0,
                parameters={}
            )

            def parse_side_effect(min_trades=10):
                if min_trades == 0:
                    return [low_trade_pass, low_trade_pass, low_trade_pass]
                else:
                    return []

            mock_parser.parse_optimization_results.side_effect = parse_side_effect

            result = parse_optimization_results(xml_path, min_trades=10)

            assert result.success is True
            assert result.valid_passes == 0
            assert result.total_passes == 3
            assert result.passed_gate() is False

        finally:
            xml_path.unlink()

    @patch('ea_stress.workflow.steps.step08_parse.MT5XMLParser')
    def test_forward_xml_merge_explicit_path(self, mock_parser_class):
        """Test forward XML merge with explicit path."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            f.write("<xml></xml>")
            xml_path = Path(f.name)

        with tempfile.NamedTemporaryFile(mode='w', suffix='_fwd.xml', delete=False) as f:
            f.write("<xml></xml>")
            fwd_path = Path(f.name)

        try:
            mock_parser = Mock()
            mock_parser_class.return_value = mock_parser

            pass1 = OptimizationPass(
                pass_number=1, result=1000.0, profit=500.0, profit_factor=1.8,
                expected_payoff=10.0, max_drawdown_pct=15.0, total_trades=50,
                sharpe_ratio=1.5, recovery_factor=3.0, win_rate=55.0,
                parameters={}, forward_profit=100.0
            )

            mock_parser.parse_optimization_results.return_value = [pass1]
            mock_parser.merge_forward_metrics.return_value = [pass1]

            result = parse_optimization_results(xml_path, forward_xml_path=fwd_path)

            assert result.forward_merged is True
            assert result.forward_xml_path == fwd_path
            mock_parser.merge_forward_metrics.assert_called_once()

        finally:
            xml_path.unlink()
            fwd_path.unlink()

    @patch('ea_stress.workflow.steps.step08_parse.MT5XMLParser')
    def test_forward_xml_auto_detect(self, mock_parser_class):
        """Test automatic forward XML detection (_fwd suffix)."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            f.write("<xml></xml>")
            xml_path = Path(f.name)

        # Create forward file with _fwd suffix
        fwd_path = xml_path.parent / f"{xml_path.stem}_fwd.xml"
        fwd_path.write_text("<xml></xml>")

        try:
            mock_parser = Mock()
            mock_parser_class.return_value = mock_parser

            pass1 = OptimizationPass(
                pass_number=1, result=1000.0, profit=500.0, profit_factor=1.8,
                expected_payoff=10.0, max_drawdown_pct=15.0, total_trades=50,
                sharpe_ratio=1.5, recovery_factor=3.0, win_rate=55.0,
                parameters={}
            )

            mock_parser.parse_optimization_results.return_value = [pass1]
            mock_parser.merge_forward_metrics.return_value = [pass1]

            result = parse_optimization_results(xml_path)

            assert result.forward_merged is True
            assert result.forward_xml_path == fwd_path
            mock_parser.merge_forward_metrics.assert_called_once()

        finally:
            xml_path.unlink()
            if fwd_path.exists():
                fwd_path.unlink()

    @patch('ea_stress.workflow.steps.step08_parse.MT5XMLParser')
    def test_parse_exception_handling(self, mock_parser_class):
        """Test exception handling during parsing."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            f.write("<xml></xml>")
            xml_path = Path(f.name)

        try:
            mock_parser = Mock()
            mock_parser_class.return_value = mock_parser
            mock_parser.parse_optimization_results.side_effect = Exception("Parse error")

            result = parse_optimization_results(xml_path)

            assert result.success is False
            assert result.valid_passes == 0
            assert result.passed_gate() is False
            assert "Parse error" in result.error_message

        finally:
            xml_path.unlink()

    @patch('ea_stress.workflow.steps.step08_parse.MT5XMLParser')
    def test_custom_min_trades_threshold(self, mock_parser_class):
        """Test using custom minimum trades threshold."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            f.write("<xml></xml>")
            xml_path = Path(f.name)

        try:
            mock_parser = Mock()
            mock_parser_class.return_value = mock_parser

            pass1 = OptimizationPass(
                pass_number=1, result=1000.0, profit=500.0, profit_factor=1.8,
                expected_payoff=10.0, max_drawdown_pct=15.0, total_trades=25,
                sharpe_ratio=1.5, recovery_factor=3.0, win_rate=55.0,
                parameters={}
            )

            mock_parser.parse_optimization_results.return_value = [pass1]

            result = parse_optimization_results(xml_path, min_trades=20)

            assert result.min_trades_threshold == 20
            mock_parser.parse_optimization_results.assert_called()

        finally:
            xml_path.unlink()

    @patch('ea_stress.workflow.steps.step08_parse.MT5XMLParser')
    def test_default_min_trades_from_config(self, mock_parser_class):
        """Test default min_trades uses ONTESTER_MIN_TRADES from config."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            f.write("<xml></xml>")
            xml_path = Path(f.name)

        try:
            mock_parser = Mock()
            mock_parser_class.return_value = mock_parser
            mock_parser.parse_optimization_results.return_value = []

            result = parse_optimization_results(xml_path)

            assert result.min_trades_threshold == ONTESTER_MIN_TRADES

        finally:
            xml_path.unlink()


class TestValidateParseResults:
    """Test validate_parse_results convenience function."""

    @patch('ea_stress.workflow.steps.step08_parse.parse_optimization_results')
    def test_validate_parse_results_alias(self, mock_parse):
        """Test that validate_parse_results is an alias for parse_optimization_results."""
        mock_result = ParseResult(
            success=True,
            xml_path=Path("test.xml"),
            valid_passes=5,
            total_passes=10
        )
        mock_parse.return_value = mock_result

        result = validate_parse_results(Path("test.xml"), min_trades=15)

        mock_parse.assert_called_once_with(Path("test.xml"), min_trades=15)
        assert result == mock_result
