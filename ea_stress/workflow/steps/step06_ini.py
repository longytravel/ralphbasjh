"""
Step 6: Create Optimization INI (Pass 1 - Wide)

Generates MT5 tester configuration file for the first optimization pass
using wide optimization ranges from Step 4.

Per PRD Section 3, Step 6.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
import os


@dataclass
class OptimizationINIResult:
    """Result of Step 6: Create Optimization INI (Pass 1 - Wide)"""

    ini_path: str
    """Path to generated INI file"""

    report_name: str
    """MT5 report name (deterministic)"""

    param_count: int
    """Total parameters in INI"""

    optimize_count: int
    """Parameters being optimized"""

    fixed_count: int
    """Parameters with fixed values"""

    start_date: str
    """Backtest start date (YYYY.MM.DD)"""

    end_date: str
    """Backtest end date (YYYY.MM.DD)"""

    forward_date: str
    """Forward split date (YYYY.MM.DD)"""

    success: bool = True
    """Whether INI generation succeeded"""

    error_message: Optional[str] = None
    """Error message if failed"""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional metadata"""

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON persistence"""
        return {
            "ini_path": self.ini_path,
            "report_name": self.report_name,
            "param_count": self.param_count,
            "optimize_count": self.optimize_count,
            "fixed_count": self.fixed_count,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "forward_date": self.forward_date,
            "success": self.success,
            "error_message": self.error_message,
            "metadata": self.metadata,
        }


def create_optimization_ini(
    ex5_path: str,
    symbol: str,
    timeframe: str,
    workflow_id: str,
    optimization_ranges: List[Dict[str, Any]],
    output_dir: str,
    ea_name: Optional[str] = None,
    backtest_years: int = 4,
    in_sample_years: int = 3,
    model: int = 1,
    execution_latency_ms: int = 10,
    deposit: int = 3000,
    currency: str = "GBP",
    leverage: int = 100,
    optimization_criterion: int = 6,
) -> OptimizationINIResult:
    """
    Create MT5 optimization INI file for Pass 1.

    Per PRD Section 3, Step 6:
    - Uses wide optimization ranges from Step 4
    - Generates deterministic report name
    - Sets up forward testing with date-based split
    - Configures genetic algorithm optimization

    Args:
        ex5_path: Path to compiled .ex5 file
        symbol: Trading symbol (e.g., "EURUSD")
        timeframe: Timeframe string (e.g., "H1", "M15")
        workflow_id: Unique workflow identifier
        optimization_ranges: List of parameter range dicts from Step 4
        output_dir: Directory for INI file output
        ea_name: EA name for report (defaults to ex5 filename stem)
        backtest_years: Total backtest period (default: 4)
        in_sample_years: In-sample period for optimization (default: 3)
        model: MT5 model (0=tick, 1=OHLC, 2=open only, default: 1)
        execution_latency_ms: Simulated latency (default: 10)
        deposit: Starting balance (default: 3000)
        currency: Account currency (default: "GBP")
        leverage: Account leverage (default: 100)
        optimization_criterion: MT5 criterion (6=custom OnTester, default: 6)

    Returns:
        OptimizationINIResult with INI path and metadata
    """
    try:
        # Validate inputs
        ex5_path_obj = Path(ex5_path)
        if not ex5_path_obj.exists():
            return OptimizationINIResult(
                ini_path="",
                report_name="",
                param_count=0,
                optimize_count=0,
                fixed_count=0,
                start_date="",
                end_date="",
                forward_date="",
                success=False,
                error_message=f"EX5 file not found: {ex5_path}",
            )

        if not optimization_ranges:
            return OptimizationINIResult(
                ini_path="",
                report_name="",
                param_count=0,
                optimize_count=0,
                fixed_count=0,
                start_date="",
                end_date="",
                forward_date="",
                success=False,
                error_message="No optimization ranges provided",
            )

        # Determine EA name
        if ea_name is None:
            ea_name = ex5_path_obj.stem

        # Calculate dates (ending today, per PRD Section 3, Step 5)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=backtest_years * 365)
        forward_split_date = end_date - timedelta(days=(backtest_years - in_sample_years) * 365)

        # Format dates for MT5 (YYYY.MM.DD)
        start_date_str = start_date.strftime("%Y.%m.%d")
        end_date_str = end_date.strftime("%Y.%m.%d")
        forward_date_str = forward_split_date.strftime("%Y.%m.%d")

        # Convert timeframe to minutes for MT5
        timeframe_minutes = _timeframe_to_minutes(timeframe)

        # Generate deterministic report name per PRD Section 8
        # Pattern: <ea_stem>_S6_opt1_<symbol>_<timeframe>_<workflow_id[:8]>
        report_name = f"{ea_name}_S6_opt1_{symbol}_{timeframe}_{workflow_id[:8]}"

        # Create output directory if needed
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # INI file path
        ini_filename = f"{report_name}.ini"
        ini_path = output_path / ini_filename

        # Count optimize vs fixed params
        optimize_count = sum(1 for r in optimization_ranges if r.get("optimize", False))
        fixed_count = len(optimization_ranges) - optimize_count

        # Build INI content
        ini_lines = []

        # [Tester] section
        ini_lines.append("[Tester]")
        ini_lines.append(f"Expert={ex5_path_obj.name}")
        ini_lines.append(f"ExpertParameters={ex5_path_obj.stem}.set")
        ini_lines.append(f"Symbol={symbol}")
        ini_lines.append(f"Period={timeframe_minutes}")
        ini_lines.append(f"FromDate={start_date_str}")
        ini_lines.append(f"ToDate={end_date_str}")
        ini_lines.append("ForwardMode=2")  # Date-based forward
        ini_lines.append(f"ForwardDate={forward_date_str}")
        ini_lines.append(f"Model={model}")
        ini_lines.append(f"ExecutionMode={execution_latency_ms}")
        ini_lines.append("Optimization=2")  # Genetic algorithm
        ini_lines.append(f"OptimizationCriterion={optimization_criterion}")  # Custom (OnTester)
        ini_lines.append(f"Report={report_name}")
        ini_lines.append("ReplaceReport=1")
        ini_lines.append("UseLocal=1")
        ini_lines.append("Visual=0")
        ini_lines.append("ShutdownTerminal=1")
        ini_lines.append(f"Deposit={deposit}")
        ini_lines.append(f"Currency={currency}")
        ini_lines.append(f"Leverage={leverage}")
        ini_lines.append("")

        # [TesterInputs] section
        ini_lines.append("[TesterInputs]")

        for param_range in optimization_ranges:
            param_name = param_range["name"]
            optimize = param_range.get("optimize", False)

            if optimize:
                # Optimized parameter: default||start||step||stop||Y
                start = param_range.get("start", 0)
                step = param_range.get("step", 1)
                stop = param_range.get("stop", 100)
                default = param_range.get("default", start)

                param_line = f"{param_name}={default}||{start}||{step}||{stop}||Y"
            else:
                # Fixed parameter: value||0||0||0||N
                default = param_range.get("default", 0)
                param_line = f"{param_name}={default}||0||0||0||N"

            ini_lines.append(param_line)

        ini_lines.append("")

        # Write INI file
        ini_content = "\n".join(ini_lines)
        ini_path.write_text(ini_content, encoding="utf-8")

        return OptimizationINIResult(
            ini_path=str(ini_path),
            report_name=report_name,
            param_count=len(optimization_ranges),
            optimize_count=optimize_count,
            fixed_count=fixed_count,
            start_date=start_date_str,
            end_date=end_date_str,
            forward_date=forward_date_str,
            success=True,
            error_message=None,
            metadata={
                "ea_name": ea_name,
                "timeframe_minutes": timeframe_minutes,
                "backtest_years": backtest_years,
                "in_sample_years": in_sample_years,
                "forward_years": backtest_years - in_sample_years,
                "model": model,
                "execution_latency_ms": execution_latency_ms,
                "deposit": deposit,
                "currency": currency,
                "leverage": leverage,
                "optimization_criterion": optimization_criterion,
            },
        )

    except Exception as e:
        return OptimizationINIResult(
            ini_path="",
            report_name="",
            param_count=0,
            optimize_count=0,
            fixed_count=0,
            start_date="",
            end_date="",
            forward_date="",
            success=False,
            error_message=f"Error creating optimization INI: {str(e)}",
        )


def _timeframe_to_minutes(timeframe: str) -> int:
    """
    Convert timeframe string to minutes for MT5.

    Examples:
        M1 -> 1
        M5 -> 5
        M15 -> 15
        M30 -> 30
        H1 -> 60
        H4 -> 240
        D1 -> 1440
        W1 -> 10080
        MN1 -> 43200

    Args:
        timeframe: Timeframe string (e.g., "H1", "M15")

    Returns:
        Minutes as integer
    """
    timeframe = timeframe.upper()

    # Monthly (check first before M check)
    if timeframe == "MN1":
        return 43200

    # Weekly
    if timeframe == "W1":
        return 10080

    # Daily
    if timeframe == "D1":
        return 1440

    # Hour timeframes
    if timeframe.startswith("H"):
        hours = int(timeframe[1:])
        return hours * 60

    # Minute timeframes
    if timeframe.startswith("M"):
        return int(timeframe[1:])

    # Default to 60 (H1) if unknown
    return 60


def validate_ini_generation(result: OptimizationINIResult) -> bool:
    """
    Validate INI generation result.

    Args:
        result: OptimizationINIResult to validate

    Returns:
        True if valid, False otherwise
    """
    if not result.success:
        return False

    if not result.ini_path or not Path(result.ini_path).exists():
        return False

    if result.param_count == 0:
        return False

    return True
