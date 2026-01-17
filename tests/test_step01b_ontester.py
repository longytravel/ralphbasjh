"""
Tests for Step 1B: OnTester function injection
"""

import os
import tempfile
import pytest
from ea_stress.workflow.steps.step01b_ontester import (
    inject_ontester,
    OnTesterResult,
    validate_ontester_injection
)


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_ea_without_ontester(temp_dir):
    """Create a sample EA without OnTester function."""
    ea_path = os.path.join(temp_dir, "TestEA.mq5")
    content = """
//+------------------------------------------------------------------+
//| Test EA without OnTester
//+------------------------------------------------------------------+
#property copyright "Test"
#property version   "1.00"

input int FastPeriod = 10;
input int SlowPeriod = 20;

int OnInit()
{
    return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
}

void OnTick()
{
    // Trading logic here
}
"""
    with open(ea_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return ea_path


@pytest.fixture
def sample_ea_with_our_ontester(temp_dir):
    """Create a sample EA with our OnTester already injected."""
    ea_path = os.path.join(temp_dir, "TestEAWithOurs.mq5")
    content = """
//+------------------------------------------------------------------+
//| Test EA with our OnTester
//+------------------------------------------------------------------+
#property copyright "Test"
#property version   "1.00"

input int FastPeriod = 10;

int OnInit()
{
    return(INIT_SUCCEEDED);
}

void OnTick()
{
    // Trading logic
}

// EA_STRESS_ONTESTER_INJECTED
double OnTester()
{
    return 100.0;
}
"""
    with open(ea_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return ea_path


@pytest.fixture
def sample_ea_with_external_ontester(temp_dir):
    """Create a sample EA with external OnTester (conflict)."""
    ea_path = os.path.join(temp_dir, "TestEAWithExternal.mq5")
    content = """
//+------------------------------------------------------------------+
//| Test EA with external OnTester
//+------------------------------------------------------------------+
#property copyright "Test"
#property version   "1.00"

input int FastPeriod = 10;

int OnInit()
{
    return(INIT_SUCCEEDED);
}

void OnTick()
{
    // Trading logic
}

double OnTester()
{
    // Custom external optimization criterion
    return TesterStatistics(STAT_PROFIT);
}
"""
    with open(ea_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return ea_path


def test_inject_ontester_new_ea(sample_ea_without_ontester, temp_dir):
    """Test injecting OnTester into EA without existing OnTester."""
    result = inject_ontester(sample_ea_without_ontester, temp_dir)

    assert result.status == "injected"
    assert result.passed_gate() is True
    assert result.modified_ea_path is not None
    assert os.path.exists(result.modified_ea_path)
    assert result.has_existing_ontester is False
    assert result.existing_ontester_is_ours is False
    assert result.error_message is None

    # Verify modified file contains OnTester
    with open(result.modified_ea_path, 'r', encoding='utf-8') as f:
        content = f.read()
        assert "EA_STRESS_ONTESTER_INJECTED" in content
        assert "double OnTester()" in content
        assert "CalculateRSquared()" in content
        assert "TesterStatistics(STAT_PROFIT)" in content


def test_inject_ontester_already_present(sample_ea_with_our_ontester, temp_dir):
    """Test detecting already injected OnTester."""
    result = inject_ontester(sample_ea_with_our_ontester, temp_dir)

    assert result.status == "already_present"
    assert result.passed_gate() is True
    assert result.has_existing_ontester is True
    assert result.existing_ontester_is_ours is True
    assert result.modified_ea_path == sample_ea_with_our_ontester
    assert result.error_message is None


def test_inject_ontester_conflict(sample_ea_with_external_ontester, temp_dir):
    """Test detecting conflict with external OnTester."""
    result = inject_ontester(sample_ea_with_external_ontester, temp_dir)

    assert result.status == "conflict"
    assert result.passed_gate() is False
    assert result.has_existing_ontester is True
    assert result.existing_ontester_is_ours is False
    assert result.error_message is not None
    assert "already has OnTester()" in result.error_message


def test_inject_ontester_custom_min_trades(sample_ea_without_ontester, temp_dir):
    """Test injecting OnTester with custom min_trades threshold."""
    result = inject_ontester(sample_ea_without_ontester, temp_dir, min_trades=20)

    assert result.status == "injected"
    assert result.passed_gate() is True

    # Verify custom threshold in generated code
    with open(result.modified_ea_path, 'r', encoding='utf-8') as f:
        content = f.read()
        assert "total_trades < 20" in content


def test_inject_ontester_file_not_found(temp_dir):
    """Test handling of non-existent file."""
    non_existent = os.path.join(temp_dir, "NonExistent.mq5")
    result = inject_ontester(non_existent, temp_dir)

    assert result.status == "error"
    assert result.passed_gate() is False
    assert result.error_message is not None


def test_inject_ontester_creates_output_dir(sample_ea_without_ontester, temp_dir):
    """Test that output directory is created if it doesn't exist."""
    output_dir = os.path.join(temp_dir, "subdir", "output")
    assert not os.path.exists(output_dir)

    result = inject_ontester(sample_ea_without_ontester, output_dir)

    assert result.status == "injected"
    assert os.path.exists(output_dir)
    assert os.path.exists(result.modified_ea_path)


def test_ontester_result_to_dict(sample_ea_without_ontester, temp_dir):
    """Test OnTesterResult serialization to dict."""
    result = inject_ontester(sample_ea_without_ontester, temp_dir)
    result_dict = result.to_dict()

    assert isinstance(result_dict, dict)
    assert result_dict["status"] == "injected"
    assert result_dict["passed_gate"] is True
    assert "modified_ea_path" in result_dict
    assert "original_ea_path" in result_dict
    assert "has_existing_ontester" in result_dict
    assert "existing_ontester_is_ours" in result_dict


def test_ontester_code_structure(sample_ea_without_ontester, temp_dir):
    """Test that generated OnTester code has all required components."""
    result = inject_ontester(sample_ea_without_ontester, temp_dir)

    with open(result.modified_ea_path, 'r', encoding='utf-8') as f:
        content = f.read()

        # Check for system marker
        assert "EA_STRESS_ONTESTER_INJECTED" in content

        # Check for main OnTester function
        assert "double OnTester()" in content

        # Check for all required statistics
        assert "TesterStatistics(STAT_PROFIT)" in content
        assert "TesterStatistics(STAT_PROFIT_FACTOR)" in content
        assert "TesterStatistics(STAT_EQUITY_DDREL_PERCENT)" in content
        assert "TesterStatistics(STAT_TRADES)" in content

        # Check for gates
        assert "return -1000.0" in content  # Min trades gate
        assert "return -500.0" in content   # Profit > 0 gate

        # Check for R^2 calculation
        assert "CalculateRSquared()" in content
        assert "double CalculateRSquared()" in content

        # Check for formula components
        assert "dd_factor" in content
        assert "pf_bonus" in content
        assert "trade_scale" in content
        assert "r_squared" in content

        # Check for linear regression
        assert "sum_x" in content
        assert "sum_y" in content
        assert "sum_xy" in content
        assert "sum_x2" in content
        assert "ss_total" in content
        assert "ss_residual" in content


def test_ontester_ignores_commented_ontester(temp_dir):
    """Test that commented OnTester functions are ignored."""
    ea_path = os.path.join(temp_dir, "TestEACommented.mq5")
    content = """
//+------------------------------------------------------------------+
//| Test EA with commented OnTester
//+------------------------------------------------------------------+

int OnInit()
{
    return(INIT_SUCCEEDED);
}

// double OnTester()
// {
//     return 100.0;
// }

void OnTick()
{
    // Trading logic
}
"""
    with open(ea_path, 'w', encoding='utf-8') as f:
        f.write(content)

    result = inject_ontester(ea_path, temp_dir)

    # Should inject since commented OnTester doesn't count
    assert result.status == "injected"
    assert result.has_existing_ontester is False


def test_validate_ontester_injection(sample_ea_without_ontester, temp_dir):
    """Test validate_ontester_injection convenience function."""
    result = validate_ontester_injection(sample_ea_without_ontester)

    assert isinstance(result, OnTesterResult)
    assert result.status == "injected"


def test_ontester_unicode_handling(temp_dir):
    """Test handling of EA files with Unicode content."""
    ea_path = os.path.join(temp_dir, "TestEAUnicode.mq5")
    content = """
//+------------------------------------------------------------------+
//| Test EA with Unicode: €£¥
//+------------------------------------------------------------------+

input string Comment = "Testing: €£¥";

int OnInit()
{
    return(INIT_SUCCEEDED);
}

void OnTick()
{
    // Trading logic
}
"""
    with open(ea_path, 'w', encoding='utf-8') as f:
        f.write(content)

    result = inject_ontester(ea_path, temp_dir)

    assert result.status == "injected"
    assert result.passed_gate() is True

    # Verify Unicode is preserved
    with open(result.modified_ea_path, 'r', encoding='utf-8') as f:
        content = f.read()
        assert "€£¥" in content


def test_ontester_modified_filename(sample_ea_without_ontester, temp_dir):
    """Test that modified EA has correct filename suffix."""
    result = inject_ontester(sample_ea_without_ontester, temp_dir)

    assert result.modified_ea_path is not None
    filename = os.path.basename(result.modified_ea_path)
    assert filename.endswith("_ontester.mq5")
    assert "TestEA" in filename


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
