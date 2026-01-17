"""
Step 1B: Inject OnTester Function

Purpose: Inject a custom optimization criterion function into the EA source code.

Requirements (PRD Section 3, Step 1B):
- Create a modified copy of the EA (never modify original)
- Inject custom OnTester() function if not present
- Function must return a custom fitness score for MT5's genetic optimizer

OnTester Criterion Formula:
    Score = Profit * R^2 * sqrt(trades/100) * DD_factor * PF_bonus

Where:
- Profit: TesterStatistics(STAT_PROFIT) - primary driver
- R^2: Equity curve linearity (0-1) via linear regression
- DD_factor: Soft drawdown penalty = 1 / (1 + maxDD / 50)
- PF_bonus: If Profit Factor > 1.5, multiply by (1 + (PF - 1.5) * 0.03)

Hardcoded Thresholds:
- trades < ONTESTER_MIN_TRADES (default: 10) -> return -1000
- profit <= 0 -> return -500
- < 10 deals in history -> Use fallback formula without R^2

Compatibility:
- If OnTester() already exists and was not injected by this system -> pause with conflict
- If OnTester() already exists with system marker -> treat as already_present
"""

import os
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class OnTesterResult:
    """Result of OnTester injection step."""

    status: str  # "injected", "already_present", "conflict", "error"
    modified_ea_path: Optional[str] = None
    original_ea_path: Optional[str] = None
    error_message: Optional[str] = None
    has_existing_ontester: bool = False
    existing_ontester_is_ours: bool = False

    def passed_gate(self) -> bool:
        """Gate: injection successful or already present (no conflict)."""
        return self.status in ("injected", "already_present")

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status,
            "modified_ea_path": self.modified_ea_path,
            "original_ea_path": self.original_ea_path,
            "error_message": self.error_message,
            "has_existing_ontester": self.has_existing_ontester,
            "existing_ontester_is_ours": self.existing_ontester_is_ours,
            "passed_gate": self.passed_gate()
        }


def inject_ontester(ea_path: str, output_dir: str, min_trades: int = 10) -> OnTesterResult:
    """
    Inject OnTester function into EA source code.

    Args:
        ea_path: Path to original EA source file
        output_dir: Directory to save modified EA
        min_trades: Minimum trades threshold for OnTester (default: 10)

    Returns:
        OnTesterResult with injection status
    """
    try:
        # Read original EA source
        with open(ea_path, 'r', encoding='utf-8', errors='ignore') as f:
            source = f.read()

        # Check for existing OnTester function
        system_marker = "// EA_STRESS_ONTESTER_INJECTED"
        has_marker = system_marker in source

        # Regex to detect OnTester function (not in comments)
        ontester_pattern = r'^\s*double\s+OnTester\s*\(\s*\)'
        has_ontester = False

        # Check line by line to avoid matching commented code
        for line in source.split('\n'):
            stripped = line.strip()
            if stripped.startswith('//'):
                continue
            if re.search(ontester_pattern, line, re.MULTILINE):
                has_ontester = True
                break

        # Determine status
        if has_ontester and has_marker:
            # Already injected by us
            return OnTesterResult(
                status="already_present",
                modified_ea_path=ea_path,
                original_ea_path=ea_path,
                has_existing_ontester=True,
                existing_ontester_is_ours=True
            )

        if has_ontester and not has_marker:
            # Conflict: OnTester exists but not injected by us
            return OnTesterResult(
                status="conflict",
                original_ea_path=ea_path,
                error_message="EA already has OnTester() function not injected by this system",
                has_existing_ontester=True,
                existing_ontester_is_ours=False
            )

        # Need to inject OnTester
        ontester_code = _generate_ontester_code(min_trades)

        # Create modified copy
        os.makedirs(output_dir, exist_ok=True)
        ea_filename = os.path.basename(ea_path)
        ea_stem = os.path.splitext(ea_filename)[0]
        modified_filename = f"{ea_stem}_ontester.mq5"
        modified_path = os.path.join(output_dir, modified_filename)

        # Insert OnTester at end of file (before any potential closing comments)
        modified_source = source + "\n\n" + ontester_code

        # Write modified EA
        with open(modified_path, 'w', encoding='utf-8') as f:
            f.write(modified_source)

        return OnTesterResult(
            status="injected",
            modified_ea_path=modified_path,
            original_ea_path=ea_path,
            has_existing_ontester=False,
            existing_ontester_is_ours=False
        )

    except Exception as e:
        return OnTesterResult(
            status="error",
            original_ea_path=ea_path,
            error_message=str(e)
        )


def _generate_ontester_code(min_trades: int) -> str:
    """
    Generate the OnTester function code.

    Formula:
        Score = Profit * R^2 * sqrt(trades/100) * DD_factor * PF_bonus

    Where:
    - Profit: TesterStatistics(STAT_PROFIT)
    - R^2: Equity curve linearity via linear regression
    - DD_factor: 1 / (1 + maxDD / 50)
    - PF_bonus: If PF > 1.5, multiply by (1 + (PF - 1.5) * 0.03)

    Hardcoded thresholds:
    - trades < min_trades -> return -1000
    - profit <= 0 -> return -500
    - < 10 deals -> fallback without R^2
    """
    return f"""
//+------------------------------------------------------------------+
//| EA_STRESS_ONTESTER_INJECTED
//| Custom optimization criterion with R^2 calculation
//|
//| Formula: Score = Profit * R^2 * sqrt(trades/100) * DD_factor * PF_bonus
//| Where:
//|   - Profit: TesterStatistics(STAT_PROFIT)
//|   - R^2: Equity curve linearity (0-1) via linear regression
//|   - DD_factor: 1 / (1 + maxDD / 50)
//|   - PF_bonus: If PF > 1.5, multiply by (1 + (PF - 1.5) * 0.03)
//|
//| Hardcoded thresholds:
//|   - trades < {min_trades} -> return -1000
//|   - profit <= 0 -> return -500
//|   - < 10 deals in history -> fallback formula without R^2
//+------------------------------------------------------------------+
double OnTester()
{{
    // Get basic statistics
    double profit = TesterStatistics(STAT_PROFIT);
    double profit_factor = TesterStatistics(STAT_PROFIT_FACTOR);
    double max_dd = TesterStatistics(STAT_EQUITY_DDREL_PERCENT);
    int total_trades = (int)TesterStatistics(STAT_TRADES);

    // Gate 1: Minimum trades
    if(total_trades < {min_trades})
        return -1000.0;

    // Gate 2: Profit must be positive
    if(profit <= 0.0)
        return -500.0;

    // Calculate R^2 from equity curve
    double r_squared = 0.0;
    if(HistoryDealsTotal() >= 10)
    {{
        r_squared = CalculateRSquared();
    }}
    else
    {{
        // Fallback: use profit factor as proxy for consistency
        r_squared = MathMin(profit_factor / 3.0, 1.0);
    }}

    // Clamp R^2 to [0, 1]
    r_squared = MathMax(0.0, MathMin(1.0, r_squared));

    // Calculate DD factor: 1 / (1 + maxDD / 50)
    double dd_factor = 1.0 / (1.0 + max_dd / 50.0);

    // Calculate PF bonus: if PF > 1.5, multiply by (1 + (PF - 1.5) * 0.03)
    double pf_bonus = 1.0;
    if(profit_factor > 1.5)
        pf_bonus = 1.0 + (profit_factor - 1.5) * 0.03;

    // Calculate trade count scaling: sqrt(trades/100)
    double trade_scale = MathSqrt(total_trades / 100.0);

    // Final score
    double score = profit * r_squared * trade_scale * dd_factor * pf_bonus;

    return score;
}}

//+------------------------------------------------------------------+
//| Calculate R^2 from equity curve using linear regression
//+------------------------------------------------------------------+
double CalculateRSquared()
{{
    int deals_total = HistoryDealsTotal();
    if(deals_total < 2)
        return 0.0;

    // Build equity curve from deal history
    double equity_curve[];
    ArrayResize(equity_curve, deals_total);

    double cumulative_profit = 0.0;
    for(int i = 0; i < deals_total; i++)
    {{
        ulong ticket = HistoryDealGetTicket(i);
        if(ticket > 0)
        {{
            double deal_profit = HistoryDealGetDouble(ticket, DEAL_PROFIT);
            double deal_commission = HistoryDealGetDouble(ticket, DEAL_COMMISSION);
            double deal_swap = HistoryDealGetDouble(ticket, DEAL_SWAP);

            cumulative_profit += deal_profit + deal_commission + deal_swap;
            equity_curve[i] = cumulative_profit;
        }}
    }}

    // Linear regression: y = mx + b
    int n = deals_total;
    double sum_x = 0.0, sum_y = 0.0, sum_xy = 0.0, sum_x2 = 0.0;

    for(int i = 0; i < n; i++)
    {{
        double x = (double)i;
        double y = equity_curve[i];

        sum_x += x;
        sum_y += y;
        sum_xy += x * y;
        sum_x2 += x * x;
    }}

    // Calculate slope (m) and intercept (b)
    double denom = n * sum_x2 - sum_x * sum_x;
    if(MathAbs(denom) < 0.000001)
        return 0.0;

    double m = (n * sum_xy - sum_x * sum_y) / denom;
    double b = (sum_y - m * sum_x) / n;

    // Calculate R^2 = 1 - (SS_residual / SS_total)
    double mean_y = sum_y / n;
    double ss_total = 0.0;
    double ss_residual = 0.0;

    for(int i = 0; i < n; i++)
    {{
        double y = equity_curve[i];
        double y_pred = m * i + b;

        ss_total += (y - mean_y) * (y - mean_y);
        ss_residual += (y - y_pred) * (y - y_pred);
    }}

    if(ss_total < 0.000001)
        return 0.0;

    double r_squared = 1.0 - (ss_residual / ss_total);

    // Clamp to [0, 1]
    return MathMax(0.0, MathMin(1.0, r_squared));
}}
"""


def validate_ontester_injection(ea_path: str) -> OnTesterResult:
    """
    Validate if EA has OnTester properly injected.

    Args:
        ea_path: Path to EA source file

    Returns:
        OnTesterResult with validation status
    """
    return inject_ontester(ea_path, os.path.dirname(ea_path))
