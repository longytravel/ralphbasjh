"""Step 7: Run Optimization (Pass 1 - Wide).

This module executes MT5 genetic optimization using the INI file from Step 6.
Per PRD Section 3, Step 7:
- Gate: passes_found >= 1
- Uses genetic algorithm (Optimization=2)
- Custom criterion (OptimizationCriterion=6, uses OnTester)
- Timeout: 36,000 seconds (10 hours)
- Max passes kept: 1,000
"""

import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime

from ea_stress.mt5.tester import MT5Tester, BacktestResult
from ea_stress.config import OPTIMIZATION_TIMEOUT


@dataclass
class OptimizationResult:
    """Result of optimization execution."""
    success: bool
    xml_path: Optional[Path] = None
    passes_found: int = 0
    duration_seconds: float = 0.0
    error_message: Optional[str] = None
    terminal_output: str = ""
    gate_passed: bool = False

    def passed_gate(self) -> bool:
        """Check if optimization passed gate (passes_found >= 1)."""
        return self.passes_found >= 1

    def to_dict(self):
        """Convert to dict for JSON serialization."""
        return {
            "success": self.success,
            "xml_path": str(self.xml_path) if self.xml_path else None,
            "passes_found": self.passes_found,
            "duration_seconds": self.duration_seconds,
            "error_message": self.error_message,
            "terminal_output": self.terminal_output,
            "gate_passed": self.passed_gate()
        }


def run_optimization(
    ini_path: Path,
    terminal_path: Path,
    data_path: Optional[Path] = None,
    timeout: int = OPTIMIZATION_TIMEOUT
) -> OptimizationResult:
    """Run MT5 optimization using the provided INI file.

    Per PRD Section 3, Step 7:
    - Execute genetic optimization
    - Gate: passes_found >= 1
    - Timeout: OPTIMIZATION_TIMEOUT (default: 36,000 seconds = 10 hours)
    - Max passes kept: 1,000 (configured in INI)

    Args:
        ini_path: Path to optimization INI file from Step 6
        terminal_path: Path to terminal64.exe
        data_path: Optional path to MT5 data directory
        timeout: Timeout in seconds (default: OPTIMIZATION_TIMEOUT)

    Returns:
        OptimizationResult with success status, XML path, and pass count
    """
    start_time = datetime.now()

    # Validate INI file exists
    if not ini_path.exists():
        return OptimizationResult(
            success=False,
            error_message=f"INI file not found: {ini_path}"
        )

    try:
        # Initialize MT5 tester
        tester = MT5Tester(terminal_path=terminal_path, data_path=data_path)

        # Run optimization via INI file
        # MT5Tester.run_backtest handles INI file execution
        result: BacktestResult = tester.run_backtest(
            ini_path=ini_path,
            timeout=timeout
        )

        duration = (datetime.now() - start_time).total_seconds()

        if not result.success:
            return OptimizationResult(
                success=False,
                duration_seconds=duration,
                error_message=result.error_message if result.error_message else "Optimization failed",
                terminal_output=result.terminal_output
            )

        # Check if XML report exists
        if not result.xml_path or not result.xml_path.exists():
            return OptimizationResult(
                success=False,
                duration_seconds=duration,
                error_message="Optimization XML report not found",
                terminal_output=result.terminal_output
            )

        # Count passes in XML (basic check - full parsing in Step 8)
        passes_found = _count_passes_in_xml(result.xml_path)

        return OptimizationResult(
            success=True,
            xml_path=result.xml_path,
            passes_found=passes_found,
            duration_seconds=duration,
            terminal_output=result.terminal_output,
            gate_passed=passes_found >= 1
        )

    except Exception as e:
        duration = (datetime.now() - start_time).total_seconds()
        return OptimizationResult(
            success=False,
            duration_seconds=duration,
            error_message=f"Optimization exception: {str(e)}"
        )


def _count_passes_in_xml(xml_path: Path) -> int:
    """Quick count of optimization passes in XML file.

    This is a lightweight check to see if we got any results.
    Full parsing happens in Step 8.

    Args:
        xml_path: Path to MT5 XML report

    Returns:
        Number of passes found (rows in optimization table)
    """
    try:
        with open(xml_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

            # Look for <Row> tags in the XML
            # Each optimization pass is a row in the table
            # We exclude the header row
            row_count = content.count('<Row')

            # First row is usually headers, so subtract 1
            # But check if there are at least 2 rows (header + data)
            if row_count >= 2:
                return row_count - 1
            else:
                return 0

    except Exception:
        return 0


def validate_optimization(
    ini_path: Path,
    terminal_path: Path,
    data_path: Optional[Path] = None,
    timeout: int = OPTIMIZATION_TIMEOUT
) -> OptimizationResult:
    """Convenience function to run and validate optimization.

    Alias for run_optimization() with clearer naming.
    """
    return run_optimization(
        ini_path=ini_path,
        terminal_path=terminal_path,
        data_path=data_path,
        timeout=timeout
    )
