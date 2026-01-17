"""
Step 5: Validate Trades

Run backtest with wide parameters to confirm EA generates sufficient trades.
Per PRD Section 3, Step 5.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any

from ea_stress.config import (
    MIN_TRADES,
    BACKTEST_YEARS,
    IN_SAMPLE_YEARS,
    FORWARD_YEARS,
    DATA_MODEL,
    EXECUTION_LATENCY_MS,
    DEPOSIT,
    CURRENCY,
    LEVERAGE,
    SAFETY_VALIDATION_MAX_SPREAD_PIPS,
    SAFETY_VALIDATION_MAX_SLIPPAGE_PIPS,
)
from ea_stress.mt5.tester import MT5Tester, BacktestConfig, ForwardMode, OptimizationMode
from ea_stress.mt5.parser import parse_backtest_xml, BacktestMetrics


@dataclass
class ValidationResult:
    """Result from Step 5: Validate Trades"""

    # Gate metrics
    total_trades: int
    gate_passed: bool

    # Core metrics
    net_profit: float
    profit_factor: float
    max_drawdown_pct: float
    win_rate: float

    # Back and forward metrics (stored separately)
    back_metrics: Optional[BacktestMetrics] = None
    forward_metrics: Optional[BacktestMetrics] = None

    # Metadata
    report_path: Optional[str] = None
    xml_path: Optional[str] = None
    from_date: Optional[str] = None
    to_date: Optional[str] = None
    split_date: Optional[str] = None
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None

    def passed_gate(self) -> bool:
        """Check if validation gate passed"""
        return self.gate_passed

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            'total_trades': self.total_trades,
            'gate_passed': self.gate_passed,
            'net_profit': self.net_profit,
            'profit_factor': self.profit_factor,
            'max_drawdown_pct': self.max_drawdown_pct,
            'win_rate': self.win_rate,
            'report_path': self.report_path,
            'xml_path': self.xml_path,
            'from_date': self.from_date,
            'to_date': self.to_date,
            'split_date': self.split_date,
            'duration_seconds': self.duration_seconds,
            'error_message': self.error_message,
        }

        # Add back and forward metrics if available
        if self.back_metrics:
            result['back_metrics'] = {
                'profit': self.back_metrics.profit,
                'profit_factor': self.back_metrics.profit_factor,
                'total_trades': self.back_metrics.total_trades,
                'max_drawdown_pct': self.back_metrics.max_drawdown_pct,
                'win_rate': self.back_metrics.win_rate,
            }

        if self.forward_metrics:
            result['forward_metrics'] = {
                'profit': self.forward_metrics.profit,
                'profit_factor': self.forward_metrics.profit_factor,
                'total_trades': self.forward_metrics.total_trades,
                'max_drawdown_pct': self.forward_metrics.max_drawdown_pct,
                'win_rate': self.forward_metrics.win_rate,
            }

        return result


def validate_trades(
    ex5_path: str,
    symbol: str,
    timeframe: str,
    terminal_path: str,
    wide_validation_params: Dict[str, Any],
    workflow_id: str,
    min_trades: int = MIN_TRADES,
    backtest_years: int = BACKTEST_YEARS,
    in_sample_years: int = IN_SAMPLE_YEARS,
    forward_years: int = FORWARD_YEARS,
) -> ValidationResult:
    """
    Run validation backtest with wide parameters.

    Per PRD Section 3, Step 5:
    - 4 years ending today (configurable)
    - 3 years in-sample, 1 year forward (configurable)
    - Model 1 (1-minute OHLC)
    - Safety limits: 500.0 pips (loose for validation)
    - Gate: total_trades >= MIN_TRADES (default: 50)
    - Report naming: S5_validate_<symbol>_<timeframe>_<workflow_id[:8]>

    Args:
        ex5_path: Path to compiled EA (.ex5)
        symbol: Trading symbol (e.g., "EURUSD")
        timeframe: Timeframe string (e.g., "H1", "M15")
        terminal_path: Path to MT5 terminal64.exe
        wide_validation_params: Parameter values for validation
        workflow_id: Workflow identifier
        min_trades: Minimum trades required (gate threshold)
        backtest_years: Total backtest period in years
        in_sample_years: In-sample period in years
        forward_years: Forward period in years

    Returns:
        ValidationResult with gate status and metrics
    """
    start_time = datetime.now()

    try:
        # Calculate date ranges (ending today) - use datetime objects
        to_date = datetime.now()
        from_date = to_date - timedelta(days=backtest_years * 365)
        split_date = to_date - timedelta(days=forward_years * 365)

        # Format dates as strings for serialization
        from_date_str = from_date.strftime('%Y.%m.%d')
        to_date_str = to_date.strftime('%Y.%m.%d')
        split_date_str = split_date.strftime('%Y.%m.%d')

        # Apply safety parameters (loose for validation per PRD Section 3, Step 1C)
        params = wide_validation_params.copy()
        params['EAStressSafety_MaxSpreadPips'] = SAFETY_VALIDATION_MAX_SPREAD_PIPS
        params['EAStressSafety_MaxSlippagePips'] = SAFETY_VALIDATION_MAX_SLIPPAGE_PIPS

        # Report naming per PRD Section 8
        ea_stem = Path(ex5_path).stem
        report_name = f"S5_validate_{symbol}_{timeframe}_{workflow_id[:8]}"

        # Create backtest configuration
        config = BacktestConfig(
            expert=ea_stem + ".ex5",
            symbol=symbol,
            period=timeframe,
            from_date=from_date,
            to_date=to_date,
            model=DATA_MODEL,
            execution_latency_ms=EXECUTION_LATENCY_MS,
            optimization=OptimizationMode.DISABLED,
            forward_mode=ForwardMode.DATE_BASED,
            forward_date=split_date,
            deposit=DEPOSIT,
            currency=CURRENCY,
            leverage=LEVERAGE,
            shutdown_terminal=True,
            inputs=params,
        )

        # Run backtest
        tester = MT5Tester(terminal_path)
        backtest_result = tester.run_backtest(config)

        if not backtest_result.success:
            return ValidationResult(
                total_trades=0,
                gate_passed=False,
                net_profit=0.0,
                profit_factor=0.0,
                max_drawdown_pct=0.0,
                win_rate=0.0,
                error_message=backtest_result.error_message or "Backtest failed",
                from_date=from_date_str,
                to_date=to_date_str,
                split_date=split_date_str,
            )

        # Parse backtest report (XML)
        if not backtest_result.xml_path or not backtest_result.xml_path.exists():
            return ValidationResult(
                total_trades=0,
                gate_passed=False,
                net_profit=0.0,
                profit_factor=0.0,
                max_drawdown_pct=0.0,
                win_rate=0.0,
                error_message="Backtest XML report not found",
                report_path=str(backtest_result.report_path) if backtest_result.report_path else None,
                from_date=from_date_str,
                to_date=to_date_str,
                split_date=split_date_str,
            )

        metrics = parse_backtest_xml(backtest_result.xml_path)

        if not metrics:
            return ValidationResult(
                total_trades=0,
                gate_passed=False,
                net_profit=0.0,
                profit_factor=0.0,
                max_drawdown_pct=0.0,
                win_rate=0.0,
                error_message="Failed to parse backtest metrics",
                xml_path=str(backtest_result.xml_path) if backtest_result.xml_path else None,
                report_path=str(backtest_result.report_path) if backtest_result.report_path else None,
                from_date=from_date_str,
                to_date=to_date_str,
                split_date=split_date_str,
            )

        # Check for forward metrics (required per PRD)
        back_metrics = None
        forward_metrics = None

        # Look for forward report (_fwd.xml)
        xml_path = backtest_result.xml_path
        fwd_xml_path = xml_path.parent / f"{xml_path.stem}_fwd{xml_path.suffix}"

        if fwd_xml_path.exists():
            fwd_metrics = parse_backtest_xml(fwd_xml_path)
            if fwd_metrics:
                # We have both back and forward
                back_metrics = metrics
                forward_metrics = fwd_metrics

                # Use combined metrics for gate check
                total_trades = metrics.total_trades
                net_profit = metrics.profit
                profit_factor = metrics.profit_factor
                max_drawdown_pct = metrics.max_drawdown_pct
                win_rate = metrics.win_rate
            else:
                # Forward file exists but couldn't parse
                total_trades = metrics.total_trades
                net_profit = metrics.profit
                profit_factor = metrics.profit_factor
                max_drawdown_pct = metrics.max_drawdown_pct
                win_rate = metrics.win_rate
        else:
            # No forward file found - use overall metrics
            # Note: This may indicate forward split didn't work
            total_trades = metrics.total_trades
            net_profit = metrics.profit
            profit_factor = metrics.profit_factor
            max_drawdown_pct = metrics.max_drawdown_pct
            win_rate = metrics.win_rate

        # Check gate: total_trades >= MIN_TRADES
        gate_passed = total_trades >= min_trades

        # Calculate duration
        duration = (datetime.now() - start_time).total_seconds()

        return ValidationResult(
            total_trades=total_trades,
            gate_passed=gate_passed,
            net_profit=net_profit,
            profit_factor=profit_factor,
            max_drawdown_pct=max_drawdown_pct,
            win_rate=win_rate,
            back_metrics=back_metrics,
            forward_metrics=forward_metrics,
            report_path=str(backtest_result.report_path) if backtest_result.report_path else None,
            xml_path=str(backtest_result.xml_path) if backtest_result.xml_path else None,
            from_date=from_date_str,
            to_date=to_date_str,
            split_date=split_date_str,
            duration_seconds=duration,
        )

    except Exception as e:
        return ValidationResult(
            total_trades=0,
            gate_passed=False,
            net_profit=0.0,
            profit_factor=0.0,
            max_drawdown_pct=0.0,
            win_rate=0.0,
            error_message=f"Validation error: {str(e)}",
        )


def validate_ea(
    ex5_path: str,
    symbol: str,
    timeframe: str,
    terminal_path: str,
    wide_validation_params: Dict[str, Any],
    workflow_id: str,
) -> ValidationResult:
    """
    Convenience function for EA validation.
    Uses default configuration from config.py.
    """
    return validate_trades(
        ex5_path=ex5_path,
        symbol=symbol,
        timeframe=timeframe,
        terminal_path=terminal_path,
        wide_validation_params=wide_validation_params,
        workflow_id=workflow_id,
    )
