"""
Step 8B: Stat Explorer (Pass 1)

Purpose: Build an evidence pack from Pass 1 results and representative trade lists
for LLM-guided improvements. This step is deterministic and does not use the LLM.

Per PRD Section 3, Step 8B:
- Run a single backtest for the top Pass 1 candidate (highest OnTester)
- If no trades are produced, fall back to the Step 5 trade list
- Compute session, hour, and day-of-week profitability and win rates
- Compute long vs short profitability and trade duration buckets
- Identify profit concentration (top X% trades vs total profit)
- Compute parameter sensitivity from Pass 1 (correlation of parameter values to result in top decile)
"""

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any
import json
from datetime import datetime, timezone

from ...mt5.tester import MT5Tester, BacktestConfig
from ...mt5.parser import MT5XMLParser, BacktestMetrics
from ...config import (
    STAT_EXPLORER_TIMEZONE,
    STAT_MIN_TRADES_PER_BUCKET,
    STAT_MIN_EFFECT_PCT,
    STAT_MIN_SESSION_PROFIT_SHARE,
    BACKTEST_YEARS,
    IN_SAMPLE_YEARS,
    DATA_MODEL,
    EXECUTION_LATENCY_MS,
    DEPOSIT,
    CURRENCY,
    LEVERAGE,
    RUNS_DIR
)


@dataclass
class SessionStats:
    """Statistics for a trading session."""
    trades: int = 0
    profit: float = 0.0
    pf: float = 0.0
    win_rate: float = 0.0


@dataclass
class BucketStats:
    """Statistics for a generic bucket (hour, DOW, duration, etc.)."""
    trades: int = 0
    profit: float = 0.0
    pf: float = 0.0
    win_rate: float = 0.0


@dataclass
class ParameterSensitivity:
    """Parameter sensitivity analysis."""
    name: str
    corr_to_result: float
    top_decile_median: float


@dataclass
class StatExplorerResult:
    """Result from Stat Explorer analysis."""
    success: bool
    stat_explorer_path: Optional[str] = None
    backtest_xml_path: Optional[str] = None
    trade_count: int = 0
    fallback_to_step5: bool = False
    session_stats: Dict[str, SessionStats] = field(default_factory=dict)
    hour_stats: Dict[str, BucketStats] = field(default_factory=dict)
    dow_stats: Dict[str, BucketStats] = field(default_factory=dict)
    trade_duration_buckets: Dict[str, BucketStats] = field(default_factory=dict)
    long_short: Dict[str, BucketStats] = field(default_factory=dict)
    profit_concentration: Dict[str, float] = field(default_factory=dict)
    parameter_sensitivity: List[ParameterSensitivity] = field(default_factory=list)
    session_bias_flags: List[str] = field(default_factory=list)
    error_message: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        # Convert SessionStats and BucketStats to dicts
        result['session_stats'] = {k: asdict(v) for k, v in self.session_stats.items()}
        result['hour_stats'] = {k: asdict(v) for k, v in self.hour_stats.items()}
        result['dow_stats'] = {k: asdict(v) for k, v in self.dow_stats.items()}
        result['trade_duration_buckets'] = {k: asdict(v) for k, v in self.trade_duration_buckets.items()}
        result['long_short'] = {k: asdict(v) for k, v in self.long_short.items()}
        result['parameter_sensitivity'] = [asdict(p) for p in self.parameter_sensitivity]
        return result


def _get_session_windows(timezone: str = "UTC") -> Dict[str, tuple]:
    """
    Get session time windows based on timezone.

    Returns:
        Dict mapping session name to (start_hour, end_hour) in 24h format
    """
    # Default UTC windows per PRD
    return {
        "Asia": (0, 7),      # 00:00-06:59
        "London": (7, 16),   # 07:00-15:59
        "NewYork": (13, 22)  # 13:00-21:59
    }


def _parse_trade_history_from_html(html_path: Path) -> List[Dict[str, Any]]:
    """
    Parse trade history from MT5 HTML report.

    Note: This is a simplified parser. Full implementation would use BeautifulSoup
    or similar, but we're keeping stdlib-only for core functionality.

    Returns:
        List of trade dicts with keys: time, type, profit, duration_minutes
    """
    # TODO: Implement HTML parsing to extract trade list
    # For now, return empty list (will trigger fallback to Step 5)
    return []


def _compute_session_stats(trades: List[Dict[str, Any]], timezone: str) -> Dict[str, SessionStats]:
    """Compute statistics by trading session."""
    sessions = _get_session_windows(timezone)
    stats = {name: SessionStats() for name in sessions}

    for trade in trades:
        trade_hour = trade.get('hour', 0)
        profit = trade.get('profit', 0.0)
        is_win = profit > 0

        for session_name, (start, end) in sessions.items():
            if start <= trade_hour < end:
                stats[session_name].trades += 1
                stats[session_name].profit += profit
                if is_win:
                    stats[session_name].win_rate += 1
                break

    # Calculate derived metrics
    for session_name, stat in stats.items():
        if stat.trades > 0:
            stat.win_rate = (stat.win_rate / stat.trades) * 100
            # PF calculation would require wins/losses separation
            # Simplified: assume profit > 0 means PF > 1
            stat.pf = 1.0 if stat.profit > 0 else 0.0

    return stats


def _compute_hour_stats(trades: List[Dict[str, Any]]) -> Dict[str, BucketStats]:
    """Compute statistics by hour of day."""
    stats = {}

    for trade in trades:
        hour_key = f"{trade.get('hour', 0):02d}"
        if hour_key not in stats:
            stats[hour_key] = BucketStats()

        stats[hour_key].trades += 1
        profit = trade.get('profit', 0.0)
        stats[hour_key].profit += profit
        if profit > 0:
            stats[hour_key].win_rate += 1

    # Calculate win rates
    for stat in stats.values():
        if stat.trades > 0:
            stat.win_rate = (stat.win_rate / stat.trades) * 100

    return stats


def _compute_dow_stats(trades: List[Dict[str, Any]]) -> Dict[str, BucketStats]:
    """Compute statistics by day of week."""
    dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    stats = {name: BucketStats() for name in dow_names}

    for trade in trades:
        dow = trade.get('dow', 0)  # 0=Monday
        if 0 <= dow < 7:
            dow_name = dow_names[dow]
            stats[dow_name].trades += 1
            stats[dow_name].profit += trade.get('profit', 0.0)

    return stats


def _compute_duration_buckets(trades: List[Dict[str, Any]]) -> Dict[str, BucketStats]:
    """Compute statistics by trade duration."""
    buckets = {
        "0-30m": BucketStats(),
        "30-120m": BucketStats(),
        "120-360m": BucketStats(),
        "360m+": BucketStats()
    }

    for trade in trades:
        duration = trade.get('duration_minutes', 0)
        profit = trade.get('profit', 0.0)

        if duration < 30:
            bucket = "0-30m"
        elif duration < 120:
            bucket = "30-120m"
        elif duration < 360:
            bucket = "120-360m"
        else:
            bucket = "360m+"

        buckets[bucket].trades += 1
        buckets[bucket].profit += profit

    return buckets


def _compute_long_short_stats(trades: List[Dict[str, Any]]) -> Dict[str, BucketStats]:
    """Compute statistics for long vs short trades."""
    stats = {
        "long": BucketStats(),
        "short": BucketStats()
    }

    for trade in trades:
        trade_type = trade.get('type', 'long').lower()
        if 'short' in trade_type or 'sell' in trade_type:
            key = "short"
        else:
            key = "long"

        stats[key].trades += 1
        stats[key].profit += trade.get('profit', 0.0)

    return stats


def _compute_profit_concentration(trades: List[Dict[str, Any]]) -> Dict[str, float]:
    """Compute profit concentration (top X% trades vs total profit)."""
    if not trades:
        return {}

    # Sort trades by profit descending
    sorted_trades = sorted(trades, key=lambda t: t.get('profit', 0.0), reverse=True)
    total_profit = sum(t.get('profit', 0.0) for t in trades)

    if total_profit <= 0:
        return {"top_20pct_trade_profit_share": 0.0}

    # Calculate top 20% profit share
    top_20_count = max(1, int(len(trades) * 0.2))
    top_20_profit = sum(t.get('profit', 0.0) for t in sorted_trades[:top_20_count])

    return {
        "top_20pct_trade_profit_share": top_20_profit / total_profit if total_profit > 0 else 0.0
    }


def _compute_parameter_sensitivity(pass1_results: List[dict]) -> List[ParameterSensitivity]:
    """
    Compute parameter sensitivity from Pass 1 results.

    Analyzes correlation of parameter values to result in top decile.
    """
    if not pass1_results or len(pass1_results) < 10:
        return []

    # Sort by result (OnTester score) descending
    sorted_passes = sorted(pass1_results, key=lambda p: p.get('result', 0), reverse=True)

    # Get top decile (top 10%)
    top_decile_count = max(1, int(len(sorted_passes) * 0.1))
    top_decile = sorted_passes[:top_decile_count]

    # Extract parameter names from first pass
    if not top_decile or 'params' not in top_decile[0]:
        return []

    param_names = [k for k in top_decile[0]['params'].keys()
                   if k not in ['Pass', 'Back Result', 'Forward Result']]

    sensitivities = []

    for param_name in param_names:
        # Get parameter values and results from top decile
        values = []
        results = []

        for p in top_decile:
            if 'params' in p and param_name in p['params']:
                try:
                    val = float(p['params'][param_name])
                    values.append(val)
                    results.append(p.get('result', 0))
                except (ValueError, TypeError):
                    continue

        if len(values) < 3:
            continue

        # Calculate simple correlation (Pearson's r)
        # Simplified: using covariance / (std_x * std_y)
        mean_val = sum(values) / len(values)
        mean_res = sum(results) / len(results)

        cov = sum((values[i] - mean_val) * (results[i] - mean_res) for i in range(len(values))) / len(values)
        std_val = (sum((v - mean_val) ** 2 for v in values) / len(values)) ** 0.5
        std_res = (sum((r - mean_res) ** 2 for r in results) / len(results)) ** 0.5

        if std_val > 0 and std_res > 0:
            corr = cov / (std_val * std_res)
            median_val = sorted(values)[len(values) // 2]

            sensitivities.append(ParameterSensitivity(
                name=param_name,
                corr_to_result=round(corr, 3),
                top_decile_median=round(median_val, 2)
            ))

    # Sort by absolute correlation descending
    sensitivities.sort(key=lambda s: abs(s.corr_to_result), reverse=True)

    return sensitivities


def _identify_session_bias(session_stats: Dict[str, SessionStats],
                           total_profit: float) -> List[str]:
    """Identify session bias flags based on profit concentration."""
    flags = []

    if total_profit <= 0:
        return flags

    for session_name, stats in session_stats.items():
        if stats.trades < STAT_MIN_TRADES_PER_BUCKET:
            continue

        profit_share = (stats.profit / total_profit) * 100

        if profit_share >= STAT_MIN_SESSION_PROFIT_SHARE:
            flags.append(f"{session_name} session dominates with {profit_share:.1f}% of profit")

    return flags


def run_stat_explorer(
    pass1_results: List[dict],
    top_pass_params: dict,
    ex5_path: Path,
    symbol: str,
    timeframe: str,
    workflow_id: str,
    mt5_terminal_path: Path,
    mt5_data_path: Optional[Path] = None,
    step5_xml_path: Optional[Path] = None,
    timezone: str = STAT_EXPLORER_TIMEZONE
) -> StatExplorerResult:
    """
    Run Stat Explorer analysis on Pass 1 results.

    Args:
        pass1_results: List of Pass 1 optimization results
        top_pass_params: Parameter dict for top Pass 1 candidate
        ex5_path: Path to compiled EA
        symbol: Trading symbol
        timeframe: Trading timeframe (e.g., "H1")
        workflow_id: Workflow identifier
        mt5_terminal_path: Path to MT5 terminal
        mt5_data_path: Optional path to MT5 data directory
        step5_xml_path: Optional fallback to Step 5 trade list
        timezone: Timezone for session analysis

    Returns:
        StatExplorerResult with analysis data
    """
    try:
        # Create output directory
        analysis_dir = Path(RUNS_DIR) / "analysis" / workflow_id / "llm"
        analysis_dir.mkdir(parents=True, exist_ok=True)

        # Compute dates (same as Step 5: 4 years ending today, 3 in-sample, 1 forward)
        end_date = datetime.now(timezone=timezone.utc)
        start_date = end_date.replace(year=end_date.year - BACKTEST_YEARS)
        forward_date = end_date.replace(year=end_date.year - (BACKTEST_YEARS - IN_SAMPLE_YEARS))

        # Generate report name per PRD Section 8
        report_name = f"S8B_stat_{symbol}_{timeframe}_{workflow_id[:8]}"

        # Run backtest for top Pass 1 candidate
        config = BacktestConfig(
            expert=ex5_path.name,
            symbol=symbol,
            period=timeframe,
            from_date=start_date,
            to_date=end_date,
            forward_mode=2,  # Date-based
            forward_date=forward_date,
            model=DATA_MODEL,
            execution_mode=EXECUTION_LATENCY_MS,
            report=report_name,
            deposit=DEPOSIT,
            currency=CURRENCY,
            leverage=LEVERAGE,
            optimization=0,  # No optimization, just backtest
            input_params=top_pass_params
        )

        tester = MT5Tester(mt5_terminal_path, mt5_data_path)
        backtest_result = tester.run_backtest(config, timeout=3600)  # 1 hour timeout

        if not backtest_result.success or not backtest_result.xml_report:
            # Fallback to Step 5 trade list
            if step5_xml_path and step5_xml_path.exists():
                backtest_result.xml_report = step5_xml_path
                fallback = True
            else:
                return StatExplorerResult(
                    success=False,
                    error_message="Backtest failed and no Step 5 fallback available"
                )
        else:
            fallback = False

        # Parse trade history
        # Note: For now, we'll use placeholder logic since HTML parsing requires BeautifulSoup
        # In production, this would parse the HTML report to extract individual trades
        trades = _parse_trade_history_from_html(backtest_result.html_report) if backtest_result.html_report else []

        # If no trades extracted (parsing not implemented), use empty analysis
        if not trades:
            # Still compute parameter sensitivity from pass1_results
            param_sensitivity = _compute_parameter_sensitivity(pass1_results)

            result = StatExplorerResult(
                success=True,
                stat_explorer_path=str(analysis_dir / "stat_explorer.json"),
                backtest_xml_path=str(backtest_result.xml_report) if backtest_result.xml_report else None,
                trade_count=0,
                fallback_to_step5=fallback,
                parameter_sensitivity=param_sensitivity,
                error_message="Trade history parsing not yet implemented (requires HTML parsing)"
            )

            # Write stat_explorer.json
            with open(result.stat_explorer_path, 'w') as f:
                json.dump(result.to_dict(), f, indent=2)

            return result

        # Compute all statistics
        session_stats = _compute_session_stats(trades, timezone)
        hour_stats = _compute_hour_stats(trades)
        dow_stats = _compute_dow_stats(trades)
        duration_buckets = _compute_duration_buckets(trades)
        long_short = _compute_long_short_stats(trades)
        profit_concentration = _compute_profit_concentration(trades)
        param_sensitivity = _compute_parameter_sensitivity(pass1_results)

        # Calculate total profit for bias detection
        total_profit = sum(t.get('profit', 0.0) for t in trades)
        session_bias_flags = _identify_session_bias(session_stats, total_profit)

        result = StatExplorerResult(
            success=True,
            stat_explorer_path=str(analysis_dir / "stat_explorer.json"),
            backtest_xml_path=str(backtest_result.xml_report) if backtest_result.xml_report else None,
            trade_count=len(trades),
            fallback_to_step5=fallback,
            session_stats=session_stats,
            hour_stats=hour_stats,
            dow_stats=dow_stats,
            trade_duration_buckets=duration_buckets,
            long_short=long_short,
            profit_concentration=profit_concentration,
            parameter_sensitivity=param_sensitivity,
            session_bias_flags=session_bias_flags
        )

        # Write stat_explorer.json
        with open(result.stat_explorer_path, 'w') as f:
            json.dump(result.to_dict(), f, indent=2)

        return result

    except Exception as e:
        return StatExplorerResult(
            success=False,
            error_message=f"Stat Explorer error: {str(e)}"
        )


def validate_stat_explorer(
    pass1_results: List[dict],
    top_pass_params: dict,
    ex5_path: Path,
    symbol: str,
    timeframe: str,
    workflow_id: str,
    mt5_terminal_path: Path,
    mt5_data_path: Optional[Path] = None,
    step5_xml_path: Optional[Path] = None
) -> StatExplorerResult:
    """Convenience function for running Stat Explorer."""
    return run_stat_explorer(
        pass1_results=pass1_results,
        top_pass_params=top_pass_params,
        ex5_path=ex5_path,
        symbol=symbol,
        timeframe=timeframe,
        workflow_id=workflow_id,
        mt5_terminal_path=mt5_terminal_path,
        mt5_data_path=mt5_data_path,
        step5_xml_path=step5_xml_path
    )
