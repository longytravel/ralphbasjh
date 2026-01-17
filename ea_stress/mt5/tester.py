"""MT5 Strategy Tester Integration.

This module handles:
- INI file generation for backtests and optimizations
- Strategy tester execution via terminal64.exe
- Result file monitoring and validation
"""

import os
import subprocess
import time
from pathlib import Path
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import IntEnum


class OptimizationMode(IntEnum):
    """MT5 optimization modes."""
    DISABLED = 0
    SLOW_COMPLETE = 1
    GENETIC = 2
    ALL_SYMBOLS = 3


class OptimizationCriterion(IntEnum):
    """MT5 optimization criteria."""
    BALANCE_MAX = 0
    PROFIT_FACTOR = 1
    EXPECTED_PAYOFF = 2
    DRAWDOWN_MIN = 3
    RECOVERY_FACTOR = 4
    SHARPE_RATIO = 5
    CUSTOM = 6  # Uses OnTester() return value


class ForwardMode(IntEnum):
    """MT5 forward testing modes."""
    DISABLED = 0
    PERIOD_BASED = 1  # 1/2, 1/3, 1/4
    DATE_BASED = 2  # Specific date range


@dataclass
class BacktestConfig:
    """Configuration for a single backtest run."""
    expert: str  # EA filename (e.g., "MyEA.ex5")
    symbol: str  # Trading symbol (e.g., "EURUSD")
    period: str  # Timeframe (e.g., "H1", "M15", "D1")
    from_date: datetime  # Start date
    to_date: datetime  # End date

    # Optional settings with defaults
    model: int = 1  # 0=Every tick, 1=1-min OHLC, 2=Open prices
    deposit: float = 3000.0
    currency: str = "GBP"
    leverage: int = 100
    execution_latency_ms: int = 10
    optimization: OptimizationMode = OptimizationMode.DISABLED
    optimization_criterion: OptimizationCriterion = OptimizationCriterion.CUSTOM
    forward_mode: ForwardMode = ForwardMode.DISABLED
    forward_date: Optional[datetime] = None
    shutdown_terminal: bool = True

    # Expert inputs (parameter values)
    inputs: Dict[str, Any] = field(default_factory=dict)

    # Optimization ranges (for optimization mode)
    # Format: {param_name: (start, step, stop, optimize_flag)}
    optimization_ranges: Dict[str, tuple] = field(default_factory=dict)


@dataclass
class BacktestResult:
    """Result of a backtest execution."""
    success: bool
    report_path: Optional[Path] = None
    xml_path: Optional[Path] = None
    duration_seconds: float = 0.0
    error_message: Optional[str] = None
    terminal_output: str = ""


class MT5Tester:
    """MT5 Strategy Tester wrapper for backtests and optimizations."""

    def __init__(self, terminal_path: Path, data_path: Optional[Path] = None):
        """Initialize tester.

        Args:
            terminal_path: Path to terminal64.exe
            data_path: Path to MT5 data directory (auto-detected if None)
        """
        self.terminal_path = Path(terminal_path)
        if not self.terminal_path.exists():
            raise FileNotFoundError(f"Terminal not found: {terminal_path}")

        # Auto-detect data path if not provided
        if data_path is None:
            self.data_path = self._detect_data_path()
        else:
            self.data_path = Path(data_path)

        self.tester_dir = self.data_path / "MQL5" / "Profiles" / "Tester"
        self.tester_dir.mkdir(parents=True, exist_ok=True)

    def _detect_data_path(self) -> Path:
        """Auto-detect MT5 data directory."""
        # Common data directory structure
        terminal_dir = self.terminal_path.parent

        # Check if terminal directory contains MQL5 (portable install)
        if (terminal_dir / "MQL5").exists():
            return terminal_dir

        # Check AppData for standard install
        appdata = Path(os.environ.get("APPDATA", ""))
        roaming_path = appdata.parent / "Roaming" / "MetaQuotes" / "Terminal"

        if roaming_path.exists():
            # Find the data directory (hash-based folder name)
            terminals = list(roaming_path.glob("*"))
            if terminals:
                # Use the first one found (ideally should match terminal installation)
                return terminals[0]

        # Fallback: create in terminal directory
        return terminal_dir

    def generate_ini(self, config: BacktestConfig, ini_path: Optional[Path] = None) -> Path:
        """Generate MT5 tester INI configuration file.

        Args:
            config: Backtest configuration
            ini_path: Output path for INI file (auto-generated if None)

        Returns:
            Path to generated INI file
        """
        if ini_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            ini_path = self.tester_dir / f"backtest_{timestamp}.ini"
        else:
            ini_path = Path(ini_path)

        # Ensure parent directory exists
        ini_path.parent.mkdir(parents=True, exist_ok=True)

        # Generate INI content
        lines = ["[Tester]"]

        # Basic settings
        lines.append(f"Expert={config.expert}")
        lines.append(f"Symbol={config.symbol}")
        lines.append(f"Period={config.period}")
        lines.append(f"Model={config.model}")
        lines.append(f"Deposit={config.deposit:.2f}")
        lines.append(f"Currency={config.currency}")
        lines.append(f"Leverage=1:{config.leverage}")
        lines.append(f"ExecutionMode=0")  # 0=Real ticks (when available)
        lines.append(f"ExecutionDelay={config.execution_latency_ms}")

        # Date range
        lines.append(f"FromDate={config.from_date.strftime('%Y.%m.%d')}")
        lines.append(f"ToDate={config.to_date.strftime('%Y.%m.%d')}")

        # Optimization settings
        lines.append(f"Optimization={config.optimization}")
        if config.optimization != OptimizationMode.DISABLED:
            lines.append(f"OptimizationCriterion={config.optimization_criterion}")
            lines.append(f"MaxThreads=0")  # 0=Auto-detect

        # Forward testing
        lines.append(f"ForwardMode={config.forward_mode}")
        if config.forward_mode == ForwardMode.DATE_BASED and config.forward_date:
            lines.append(f"ForwardDate={config.forward_date.strftime('%Y.%m.%d')}")

        # Shutdown terminal after test
        lines.append(f"ShutdownTerminal={'1' if config.shutdown_terminal else '0'}")

        # Report generation
        lines.append("GenerateReport=1")
        lines.append("GenerateXML=1")

        # Visual mode (disabled for automated testing)
        lines.append("Visual=0")

        # Expert inputs section
        if config.inputs or config.optimization_ranges:
            lines.append("")
            lines.append("[TesterInputs]")

            # Add fixed inputs
            for param_name, value in config.inputs.items():
                if param_name not in config.optimization_ranges:
                    lines.append(f"{param_name}={self._format_value(value)}")

            # Add optimization ranges
            for param_name, range_spec in config.optimization_ranges.items():
                if len(range_spec) == 4:
                    start, step, stop, optimize = range_spec
                else:
                    # If no optimize flag, default to Y
                    start, step, stop = range_spec
                    optimize = "Y"

                default = config.inputs.get(param_name, start)
                lines.append(
                    f"{param_name}={self._format_value(default)}||"
                    f"{self._format_value(start)}||"
                    f"{self._format_value(step)}||"
                    f"{self._format_value(stop)}||"
                    f"{optimize}"
                )

        # Write INI file
        content = "\n".join(lines) + "\n"
        ini_path.write_text(content, encoding="utf-8")

        return ini_path

    def _format_value(self, value: Any) -> str:
        """Format a parameter value for INI file."""
        if isinstance(value, bool):
            return "true" if value else "false"
        elif isinstance(value, float):
            return f"{value:.10g}"  # Remove trailing zeros
        elif isinstance(value, str):
            return value
        else:
            return str(value)

    def run_backtest(
        self,
        config: BacktestConfig,
        ini_path: Optional[Path] = None,
        timeout: int = 7200
    ) -> BacktestResult:
        """Execute a backtest using MT5 terminal.

        Args:
            config: Backtest configuration
            ini_path: Path to INI file (will be generated if None)
            timeout: Maximum execution time in seconds

        Returns:
            BacktestResult with execution status and output paths
        """
        start_time = time.time()

        try:
            # Generate INI file if not provided
            if ini_path is None:
                ini_path = self.generate_ini(config)
            else:
                ini_path = Path(ini_path)
                if not ini_path.exists():
                    return BacktestResult(
                        success=False,
                        error_message=f"INI file not found: {ini_path}"
                    )

            # Prepare command
            cmd = [
                str(self.terminal_path),
                "/config:" + str(ini_path)
            ]

            # Execute backtest
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=self.terminal_path.parent
            )

            duration = time.time() - start_time

            # Find generated report files
            report_path, xml_path = self._find_report_files(config)

            if report_path is None:
                return BacktestResult(
                    success=False,
                    duration_seconds=duration,
                    error_message="Report files not generated",
                    terminal_output=result.stdout + result.stderr
                )

            return BacktestResult(
                success=True,
                report_path=report_path,
                xml_path=xml_path,
                duration_seconds=duration,
                terminal_output=result.stdout
            )

        except subprocess.TimeoutExpired:
            return BacktestResult(
                success=False,
                duration_seconds=time.time() - start_time,
                error_message=f"Backtest timed out after {timeout} seconds"
            )

        except Exception as e:
            return BacktestResult(
                success=False,
                duration_seconds=time.time() - start_time,
                error_message=f"Execution error: {str(e)}"
            )

    def _find_report_files(
        self,
        config: BacktestConfig,
        max_wait: int = 30
    ) -> tuple[Optional[Path], Optional[Path]]:
        """Wait for and locate generated report files.

        Args:
            config: Backtest configuration
            max_wait: Maximum seconds to wait for files

        Returns:
            Tuple of (report_path, xml_path), None if not found
        """
        # Reports are typically saved in Tester directory
        report_dir = self.data_path / "MQL5" / "Profiles" / "Tester"

        # Expected filename pattern
        expert_name = Path(config.expert).stem

        start_time = time.time()
        while time.time() - start_time < max_wait:
            # Look for recently created HTML reports
            html_files = list(report_dir.glob(f"*{expert_name}*.htm"))
            xml_files = list(report_dir.glob(f"*{expert_name}*.xml"))

            if html_files:
                # Get most recent file
                html_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                xml_file = xml_files[0] if xml_files else None
                return html_files[0], xml_file

            time.sleep(0.5)

        return None, None

    def run_optimization(
        self,
        config: BacktestConfig,
        ini_path: Optional[Path] = None,
        timeout: int = 36000
    ) -> BacktestResult:
        """Execute an optimization using MT5 terminal.

        This is a wrapper around run_backtest with optimization-specific defaults.

        Args:
            config: Backtest configuration (must have optimization enabled)
            ini_path: Path to INI file (will be generated if None)
            timeout: Maximum execution time in seconds (default: 10 hours)

        Returns:
            BacktestResult with execution status and output paths
        """
        # Ensure optimization is enabled
        if config.optimization == OptimizationMode.DISABLED:
            config.optimization = OptimizationMode.GENETIC

        if config.optimization_criterion != OptimizationCriterion.CUSTOM:
            config.optimization_criterion = OptimizationCriterion.CUSTOM

        return self.run_backtest(config, ini_path, timeout)


def run_backtest(
    terminal_path: Path,
    expert: str,
    symbol: str,
    period: str,
    from_date: datetime,
    to_date: datetime,
    inputs: Optional[Dict[str, Any]] = None,
    **kwargs
) -> BacktestResult:
    """Convenience function to run a backtest.

    Args:
        terminal_path: Path to terminal64.exe
        expert: EA filename (e.g., "MyEA.ex5")
        symbol: Trading symbol
        period: Timeframe
        from_date: Start date
        to_date: End date
        inputs: Expert input parameters
        **kwargs: Additional BacktestConfig parameters

    Returns:
        BacktestResult
    """
    config = BacktestConfig(
        expert=expert,
        symbol=symbol,
        period=period,
        from_date=from_date,
        to_date=to_date,
        inputs=inputs or {},
        **kwargs
    )

    tester = MT5Tester(terminal_path)
    return tester.run_backtest(config)
