"""
EA Stress Test System - Configuration
Complete settings reference from PRD Section 12
"""

# ============================================
# BACKTEST SETTINGS
# ============================================

BACKTEST_YEARS = 4
"""Total period for backtesting (years)"""

IN_SAMPLE_YEARS = 3
"""Training period for optimization (years)"""

FORWARD_YEARS = 1
"""Out-of-sample testing period (years)"""

DATA_MODEL = 1
"""MT5 data model: 0=Every tick, 1=1-minute OHLC, 2=Open prices only"""

EXECUTION_LATENCY_MS = 10
"""Simulated execution latency in milliseconds"""

TICK_VALIDATION_DAYS = 30
"""Days to check for tick data coverage"""

FORWARD_MODE = 2
"""MT5 forward mode: 1=Period-based, 2=Date-based"""

DEPOSIT = 3000
"""Starting account balance"""

CURRENCY = "GBP"
"""Account currency"""

LEVERAGE = 100
"""Account leverage ratio"""


# ============================================
# GATE THRESHOLDS
# ============================================

MIN_PROFIT_FACTOR = 1.5
"""Minimum profit factor to pass gate"""

MAX_DRAWDOWN_PCT = 30.0
"""Maximum drawdown percentage to pass gate"""

MIN_TRADES = 50
"""Minimum number of trades required"""

ONTESTER_MIN_TRADES = 10
"""Minimum trades for OnTester function (optimization passes)"""

OPTIMIZATION_TIMEOUT = 36000
"""Optimization timeout in seconds (10 hours)"""

MC_ITERATIONS = 10000
"""Number of Monte Carlo simulation iterations"""

MC_CONFIDENCE_MIN = 70.0
"""Minimum Monte Carlo confidence percentage"""

MC_RUIN_MAX = 5.0
"""Maximum acceptable Monte Carlo ruin probability percentage"""


# ============================================
# SAFETY PARAMETERS
# ============================================

SAFETY_DEFAULT_MAX_SPREAD_PIPS = 3.0
"""Default maximum spread in pips for realistic trading"""

SAFETY_DEFAULT_MAX_SLIPPAGE_PIPS = 3.0
"""Default maximum slippage in pips for realistic trading"""

SAFETY_VALIDATION_MAX_SPREAD_PIPS = 500.0
"""Loose spread limit for Step 5 validation (maximize trades)"""

SAFETY_VALIDATION_MAX_SLIPPAGE_PIPS = 500.0
"""Loose slippage limit for Step 5 validation (maximize trades)"""


# ============================================
# RISK METRICS (TARGETS, NOT GATES)
# ============================================

MIN_SHARPE_RATIO = 1.0
"""Minimum target for Sharpe ratio"""

TARGET_SHARPE_RATIO = 2.0
"""Desired target for Sharpe ratio"""

MIN_SORTINO_RATIO = 1.5
"""Minimum target for Sortino ratio"""

TARGET_SORTINO_RATIO = 2.5
"""Desired target for Sortino ratio"""

MIN_CALMAR_RATIO = 1.0
"""Minimum target for Calmar ratio"""

TARGET_CALMAR_RATIO = 3.0
"""Desired target for Calmar ratio"""

MIN_RECOVERY_FACTOR = 2.0
"""Minimum recovery factor (profit/max_dd)"""

MIN_EXPECTED_PAYOFF = 5.0
"""Minimum expected payoff per trade"""

MIN_WIN_RATE = 40.0
"""Minimum win rate percentage"""

TARGET_WIN_RATE = 55.0
"""Target win rate percentage"""

RISK_FREE_RATE = 0.05
"""Risk-free rate for Sharpe ratio calculation"""


# ============================================
# SCORING SYSTEM
# ============================================

GO_LIVE_SCORE_WEIGHTS = {
    'consistency': 0.25,
    'total_profit': 0.25,
    'trade_count': 0.20,
    'profit_factor': 0.15,
    'max_drawdown': 0.15,
}
"""Component weights for Go Live Score calculation"""

GO_LIVE_SCORE_RANGES = {
    'total_profit': (0, 5000),
    'trade_count': (50, 200),
    'profit_factor': (1.0, 3.0),
    'max_drawdown': (0, 30),
    'consistency_min': (0, 2000),
}
"""Normalization ranges for Go Live Score components"""

BEST_PASS_SELECTION = "score"
"""Best pass selection mode: 'score' or 'profit'"""


# ============================================
# AUTOMATION SETTINGS
# ============================================

AUTO_STATS_ANALYSIS = True
"""Auto-select top passes instead of pausing for manual selection"""

AUTO_STATS_TOP_N = 20
"""Number of top passes to auto-select for backtesting"""

AUTO_RUN_FORWARD_WINDOWS = True
"""Automatically run Step 13 (Forward Windows Analysis)"""

AUTO_RUN_MULTI_PAIR = False
"""Automatically run Step 14 (Multi-Pair Orchestration)"""

AUTO_RUN_STRESS_SCENARIOS = True
"""Automatically run Step 12 (Stress Scenarios)"""

MULTI_PAIR_SYMBOLS = ["EURUSD", "USDJPY"]
"""Additional symbols for multi-pair testing"""

MULTI_PAIR_MODE = "external"
"""Multi-pair mode: 'external' (child workflows) or 'internal' (EA handles)"""

PASS1_COMPARE_ENABLED = True
"""Include top Pass 1 results in final backtest comparison"""

PASS1_COMPARE_TOP_N = 10
"""Number of top Pass 1 candidates to include in backtesting"""

LLM_IMPROVEMENT_ENABLED = True
"""Enable LLM improvement loop (Steps 8B-8E)"""

LLM_REVIEW_REQUIRED = True
"""Require manual approval for EA patches"""

LLM_ALLOW_NEW_LOGIC = True
"""Allow LLM to propose new indicators and logic"""

LLM_MAX_REFINEMENT_CYCLES = 1
"""Maximum review-driven LLM follow-up iterations"""

STAT_EXPLORER_TIMEZONE = "UTC"
"""Timezone for session/hour analysis"""

STAT_MIN_TRADES_PER_BUCKET = 30
"""Minimum trades required per statistical bucket"""

STAT_MIN_EFFECT_PCT = 10.0
"""Minimum effect size percentage vs baseline to flag patterns"""

STAT_MIN_SESSION_PROFIT_SHARE = 60.0
"""Minimum profit share percentage to flag session bias"""

PATCH_MAX_PROFIT_DROP_PCT = 20.0
"""Maximum allowed profit drop after patch vs baseline"""

PATCH_MAX_PF_DROP_PCT = 10.0
"""Maximum allowed profit factor drop after patch vs baseline"""

PATCH_MAX_TRADES_DROP_PCT = 20.0
"""Maximum allowed trade count drop after patch vs baseline"""


# ============================================
# STRESS TESTING
# ============================================

STRESS_WINDOW_ROLLING_DAYS = [7, 14, 30, 60, 90]
"""Rolling day windows for stress testing"""

STRESS_WINDOW_CALENDAR_MONTHS_AGO = [1, 2, 3]
"""Calendar months ago for stress testing"""

STRESS_WINDOW_MODELS = [1, 0]
"""MT5 models to test: 1=OHLC, 0=Every tick"""

STRESS_TICK_LATENCY_MS = [250, 5000]
"""Latency variants for tick-based stress tests (milliseconds)"""

STRESS_INCLUDE_OVERLAYS = True
"""Include cost overlays (spread/slippage) in stress testing"""

STRESS_OVERLAY_SPREAD_PIPS = [0.0, 1.0, 2.0, 3.0, 5.0]
"""Spread overlay values for stress testing (pips)"""

STRESS_OVERLAY_SLIPPAGE_PIPS = [0.0, 1.0, 3.0]
"""Slippage overlay values for stress testing (pips)"""

STRESS_OVERLAY_SLIPPAGE_SIDES = 2
"""Slippage application: 1=entry, 2=entry+exit"""


# ============================================
# OPTIMIZATION
# ============================================

OPTIMIZATION_CRITERION = 6
"""MT5 optimization criterion: 6=Custom (OnTester)"""

MAX_OPTIMIZATION_PASSES = 1000
"""Maximum number of optimization passes to keep"""

TOP_PASSES_DISPLAY = 20
"""Number of top passes to display in dashboards"""

TOP_PASSES_BACKTEST = 30
"""Maximum number of passes to backtest in Step 9"""


# ============================================
# PARAMETER STABILITY
# ============================================

PARAM_STABILITY_RANGE = 0.10
"""Parameter value variation range for stability testing"""

PARAM_STABILITY_MIN_RETENTION = 0.70
"""Minimum retention rate for parameter stability"""


# ============================================
# CORRELATION
# ============================================

MAX_EA_CORRELATION = 0.70
"""Maximum correlation allowed between EAs in portfolio"""

CORRELATION_LOOKBACK_DAYS = 252
"""Days to look back for correlation calculation"""


# ============================================
# RE-OPTIMIZATION
# ============================================

REOPT_TOGGLE_THRESHOLD = 0.70
"""Threshold for re-optimization toggle detection"""

REOPT_CLUSTERING_CV_THRESHOLD = 0.20
"""Coefficient of variation threshold for clustering"""

REOPT_MIN_VALID_PASSES = 50
"""Minimum valid passes required for re-optimization"""

REOPT_MAX_ITERATIONS = 2
"""Maximum re-optimization iterations"""


# ============================================
# PATHS
# ============================================

RUNS_DIR = "runs"
"""Base directory for all workflow outputs"""

DASHBOARDS_DIR = "runs/dashboards"
"""Directory for workflow dashboards"""

LEADERBOARD_DIR = "runs/leaderboard"
"""Directory for global leaderboard"""

LOGS_DIR = "runs/logs"
"""Directory for workflow logs"""

ANALYSIS_DIR = "runs/analysis"
"""Directory for analysis artifacts (LLM, patches, stat explorer)"""

WORKFLOWS_DIR = "runs/workflows"
"""Directory for workflow state JSON files"""

REPORTS_DIR = "runs/reports"
"""Directory for MT5 reports"""

BOARDS_DIR = "runs/boards"
"""Directory for multi-workflow comparison boards"""

TEMPLATES_DIR = "reports/templates"
"""Directory for HTML report templates"""

MT5_TERMINAL_PATH = "C:/Path/To/terminal64.exe"
"""Default MT5 terminal path (autodiscovery preferred)"""


# ============================================
# SESSION WINDOWS (for Stat Explorer)
# ============================================

SESSION_WINDOWS = {
    'Asia': (0, 6, 59),      # 00:00-06:59
    'London': (7, 15, 59),   # 07:00-15:59
    'NewYork': (13, 21, 59), # 13:00-21:59
}
"""Trading session windows in UTC (start_hour, end_hour, end_minute)"""


# ============================================
# WORKFLOW STATUS VALUES
# ============================================

STATUS_PENDING = "PENDING"
STATUS_IN_PROGRESS = "IN_PROGRESS"
STATUS_AWAITING_CONFIG = "AWAITING_CONFIG"
STATUS_AWAITING_PARAM_ANALYSIS = "AWAITING_PARAM_ANALYSIS"
STATUS_AWAITING_PATCH_REVIEW = "AWAITING_PATCH_REVIEW"
STATUS_AWAITING_STATS_ANALYSIS = "AWAITING_STATS_ANALYSIS"
STATUS_AWAITING_EA_FIX = "AWAITING_EA_FIX"
STATUS_COMPLETED = "COMPLETED"
STATUS_FAILED = "FAILED"


# ============================================
# MAX FIX ATTEMPTS
# ============================================

MAX_EA_FIX_ATTEMPTS = 3
"""Maximum attempts to fix EA compilation or validation failures"""


# ============================================
# ONTESTER FORMULA CONSTANTS
# ============================================

ONTESTER_DD_DENOMINATOR = 50
"""Denominator for drawdown factor calculation in OnTester"""

ONTESTER_PF_THRESHOLD = 1.5
"""Profit factor threshold for bonus in OnTester"""

ONTESTER_PF_MULTIPLIER = 0.03
"""Profit factor bonus multiplier in OnTester"""

ONTESTER_TRADES_DENOMINATOR = 100
"""Trade count denominator for normalization in OnTester"""

ONTESTER_MIN_DEALS_FOR_R2 = 10
"""Minimum deals required to calculate R^2 in OnTester"""

ONTESTER_RETURN_NO_TRADES = -1000
"""OnTester return value when trades < minimum"""

ONTESTER_RETURN_NO_PROFIT = -500
"""OnTester return value when profit <= 0"""
