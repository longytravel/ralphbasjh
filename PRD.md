# EA Stress Test System - Product Requirements Document

**Version:** 2.0
**Status:** Production
**Platform:** MetaTrader 5 (Windows)

---

## 1. Executive Summary

The EA Stress Test System is a gated workflow engine that validates MetaTrader 5 Expert Advisors (EAs) through a comprehensive 14-step process. It includes a two-pass optimization loop with an evidence-driven LLM improvement stage and manual review between passes. The system determines whether an EA is suitable for live trading by applying objective, configurable pass/fail criteria at each stage.

The system outputs:
- Interactive HTML dashboards showing individual EA performance
- A global leaderboard ranking all tested EAs
- Multi-workflow comparison boards
- Persistent JSON state files for workflow resumption
- LLM analysis artifacts (Stat Explorer and proposal JSON)

---

## 2. Core Requirements

### 2.1 Workflow Architecture

The system MUST execute a sequential workflow with 14 primary steps and lettered substeps for the LLM improvement loop. Each step:
- Has defined inputs and outputs
- May have a pass/fail gate with configurable thresholds
- Persists state to JSON after completion
- Can be resumed from any checkpoint

Steps marked with gates MUST block workflow progression if the gate fails.
All optimization and backtest runs MUST include a forward split and produce back/forward metrics. If forward data is missing, the step fails.
LLM-proposed changes MUST be reviewed and approved manually before they are applied.

### 2.2 MT5 Integration

The system MUST:
- Interface with MetaTrader 5 Terminal via command-line operations
- Compile MQL5 source files using MetaEditor64.exe
- Execute backtests and optimizations via terminal command line with INI files
- Parse MT5 report outputs (XML/HTML)
- Support multiple MT5 terminal installations

### 2.3 Workflow Inputs and Discovery

The system MUST require explicit workflow inputs:
- `ea_path` (EA source file)
- `symbol`
- `timeframe`
- `mt5_terminal_path`

Resolution order for each input:
1. Explicit runner arguments
2. Workflow config file (if provided)
3. Environment variables
4. Autodiscovery (for MT5 terminals only)

If any required input is missing or multiple MT5 terminals are found, the workflow pauses with `AWAITING_CONFIG` until resolved.

### 2.4 Logging and Audit

The system MUST:
- Log every MT5 CLI invocation (command line, working directory, exit code, stdout/stderr)
- Persist a config snapshot for each workflow
- Store all LLM prompts and responses used in Steps 4 and 8C
- Store patch diffs with versioned filenames

Default locations:
- `runs/logs/<workflow_id>/`
- `runs/analysis/<workflow_id>/llm/`
- `runs/analysis/<workflow_id>/patches/`

---

## 3. Workflow Steps Specification

### Step 1: Load EA

**Purpose:** Verify EA source file exists and is accessible.

**Gate:**
- `file_exists == 1`

**Output:**
- Validated file path
- File existence status

---

### Step 1B: Inject OnTester Function

**Purpose:** Inject a custom optimization criterion function into the EA source code.

**Requirements:**
- Create a modified copy of the EA (never modify original)
- Inject custom `OnTester()` function if not present
- Function must return a custom fitness score for MT5's genetic optimizer

**Compatibility With Existing OnTester:**
- If `OnTester()` already exists and was not injected by this system, do not modify it automatically
- Set `on_tester_injection_status=conflict` and pause for manual resolution (`AWAITING_EA_FIX`)
- If `OnTester()` already exists with the system marker, treat as `already_present`

**OnTester Criterion Formula:**
```
Score = Profit * R^2 * sqrt(trades/100) * DD_factor * PF_bonus
```

Where:
- **Profit**: `TesterStatistics(STAT_PROFIT)` - primary driver
- **R^2**: Equity curve linearity (0-1) via linear regression
- **DD_factor**: Soft drawdown penalty = `1 / (1 + maxDD / 50)`
  - 0% DD = 1.0
  - 25% DD = 0.67
  - 50% DD = 0.5
  - 100% DD = 0.33
- **PF_bonus**: If Profit Factor > 1.5, multiply by `(1 + (PF - 1.5) * 0.03)`

**Hardcoded Thresholds in OnTester:**
| Condition | Return Value |
|-----------|--------------|
| trades < ONTESTER_MIN_TRADES (default: 10) | -1000 |
| profit <= 0 | -500 |
| < 10 deals in history | Use fallback formula without R^2 |

**R^2 Calculation:**
1. Build equity curve from deal history (cumulative profit per closed deal)
2. Perform linear regression: `y = mx + b`
3. Calculate: `R^2 = 1 - (SS_residual / SS_total)`
4. Clamp to [0, 1]

**Output:**
- Modified EA file path
- OnTester injection status (injected/already_present/conflict)

---

### Step 1C: Inject Safety Guards

**Purpose:** Add trade safety parameters to control spread and slippage during testing.

**Injected Parameters:**
| Parameter | Type | Default |
|-----------|------|---------|
| `EAStressSafety_MaxSpreadPips` | input double | 3.0 |
| `EAStressSafety_MaxSlippagePips` | input double | 3.0 |

**Injected Functions:**
- `EAStressSafety_PipSize()` - Calculate pip size based on broker digits
- `EAStressSafety_IsSpreadOk()` - Check current spread against limit
- `EAStressSafety_MaxDeviationPoints()` - Calculate max slippage in points
- `EAStressSafety_OrderSend()` - Wrapper that enforces spread/slippage checks

**Macro Overrides:**
```cpp
#define OrderSend EAStressSafety_OrderSend
#define OrderSendAsync EAStressSafety_OrderSendAsync
```

**Safety Parameter Behavior by Stage:**
| Stage | Max Spread | Max Slippage | Reason |
|-------|------------|--------------|--------|
| Step 5 (Validation) | 500.0 pips | 500.0 pips | Maximize trade generation |
| Post-validation runs (optimizations and backtests) | 10.0 pips | 10.0 pips | Realistic constraints |
| Optimization | Fixed (not optimized) | Fixed (not optimized) | Prevent gaming |

**Additional Safety Guards (defines):**
```cpp
#define STRESS_TEST_MODE true
#define FileOpen(a,b,c) INVALID_HANDLE
#define FileWrite(a,b) 0
#define FileDelete(a) false
#define WebRequest(a,b,c,d,e,f,g) false
```

**Compatibility With Existing Safety Features:**
- If the EA already defines spread/slippage inputs or guard functions, do not inject duplicates
- If the EA already overrides `OrderSend`/`OrderSendAsync`, do not redefine macros
- If conflicts are detected, set `safety_injection_status=conflict` and pause for manual resolution (`AWAITING_EA_FIX`)

**Output:**
- Safety injection status (injected/already_present/skipped/conflict)

---

### Step 2: Compile

**Purpose:** Compile modified EA using MetaEditor64.

**Gate:**
- `error_count == 0`

**Output:**
- Executable (.ex5) path
- Compilation errors (if any)
- Compilation warnings

**Failure Behavior:** Workflow pauses with `AWAITING_EA_FIX` status. External process must provide fixed EA code. Maximum 3 fix attempts. After a fix, re-run Step 1B and Step 1C on a fresh copy, then re-run Step 2. If it still fails after max attempts, mark workflow FAILED.

---

### Step 3: Extract Parameters

**Purpose:** Parse EA source code to extract all input parameters.

**Gate:**
- `params_found >= 1`

**Parameter Detection Pattern:**
```regex
^\s*(sinput|input)\s+([\w\s]+?)\s+(\w+)\s*(?:=\s*([^;/]+?))?\s*;(?:\s*//\s*(.*))?$
```

**Parser Behavior:**
- Join multi-line declarations until a semicolon before applying the regex
- Ignore commented-out declarations (`//` and `/* */`)
- Skip code inside `#if 0 ... #endif` blocks

**Extracted Fields:**
| Field | Description |
|-------|-------------|
| name | Parameter identifier |
| type | MQL5 type (int, double, bool, string, datetime, color, ENUM_*) |
| base_type | Normalized type (int, double, bool, string, enum) |
| default | Default value as string |
| comment | Inline comment after `//` |
| line | Line number in source |
| optimizable | true if: `input` (not `sinput`) AND numeric type AND not `EAStressSafety_*` |

**Type Mappings:**
```
int, uint, long, ulong, short, ushort, char, uchar -> int
double, float -> double
bool -> bool
string -> string
datetime -> datetime
color -> color
ENUM_* or UPPERCASE -> enum
```

**Output:**
- Parameter list
- Count of total parameters
- Count of optimizable parameters
- Parameter usage map (function names and code snippets where each input is referenced)

**Pause Point:** Workflow pauses here with `AWAITING_PARAM_ANALYSIS` status. External process must provide:
1. `wide_validation_params` - Dict for Step 5 trade validation
2. `optimization_ranges` - List for Step 6 INI generation

---

### Step 4: Analyze Parameters

**Purpose:** Receive and validate parameter analysis from external process.

**Input Requirements:**
Analysis SHOULD use an LLM with the parameter usage map to avoid name-only heuristics.

If an LLM is used, it MUST return a single JSON object containing both `wide_validation_params` and `optimization_ranges`.

**Offline LLM Flow (No API):**
- System writes `runs/analysis/<workflow_id>/llm/step4_request.json`
- External LLM produces `step4_response.json` in the same folder
- Workflow resumes when the response file exists and validates

**Validation Schema (draft 2020-12):**
```json
{
    "type": "object",
    "required": ["wide_validation_params", "optimization_ranges"],
    "properties": {
        "wide_validation_params": {
            "type": "object",
            "additionalProperties": {
                "type": ["string", "number", "boolean"]
            }
        },
        "optimization_ranges": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "optimize"],
                "properties": {
                    "name": {"type": "string"},
                    "optimize": {"type": "boolean"},
                    "start": {"type": "number"},
                    "step": {"type": "number"},
                    "stop": {"type": "number"},
                    "default": {"type": "number"},
                    "category": {"type": "string"},
                    "rationale": {"type": "string"}
                }
            }
        }
    }
}
```

**`wide_validation_params`** (dict):
Purpose: Maximize trade generation for validation
```python
{
    "ParamName": value_or_range,  # Use loose values to encourage trading
}
```

**`optimization_ranges`** (list of dicts):
```python
[
    {
        "name": "ParamName",          # Required
        "optimize": True/False,        # Required
        "start": 10,                   # If optimize=True
        "step": 5,                     # If optimize=True
        "stop": 100,                   # If optimize=True
        "default": 50,                 # If optimize=False (fixed value)
        "category": "filter|signal|risk|timing|other",  # Optional
        "rationale": "Explanation"     # Optional
    }
]
```

**Automatic Behaviors:**
1. Safety params (`EAStressSafety_*`) are automatically:
   - Set to 500.0 for validation (Step 5)
   - Set to default (3.0) and fixed for optimization (Step 7)
2. Boolean toggles (`Use_*`, `Enable_*`) from `wide_validation_params` are automatically carried forward to optimization INI if missing from ranges
3. Step 4 ranges drive Pass 1; Pass 2 ranges are refined in Step 8C (if enabled)

---

### Step 5: Validate Trades

**Purpose:** Confirm EA generates sufficient trades with loose parameters.

**Gate:**
- `total_trades >= MIN_TRADES` (default: 50)

**Backtest Configuration:**
| Setting | Value | Notes |
|---------|-------|-------|
| Period | 4 years ending today | Dynamic calculation |
| In-Sample | 3 years | For optimization |
| Forward | 1 year | Out-of-sample |
| Model | 1 (1-minute OHLC) | Configurable |
| Execution Latency | 10ms | Configurable |
| Safety Limits | 500.0 pips | Loose for validation |
| Deposit | 3000 | Configurable |
| Currency | GBP | Configurable |
| Leverage | 100:1 | Configurable |

Forward split is required; store both back and forward metrics from this run.

**Report Naming Pattern:**
```
S5_validate_<symbol>_<timeframe>_<workflow_id[:8]>
```

**Output:**
- Total trades
- Net profit
- Profit factor
- Max drawdown %
- Win rate

**Revalidation Note:** This same backtest window must be reused for any LLM patch revalidation in Step 8E.

**Failure Behavior:** Workflow pauses with `AWAITING_EA_FIX`. External process must fix EA. Maximum 3 fix attempts.

---

### Step 6: Create Optimization INI (Pass 1 - Wide)

**Purpose:** Generate MT5 tester configuration file.
Uses the wide optimization ranges from Step 4.

**INI Structure:**
```ini
[Tester]
Expert=<ea_name>.ex5
Symbol=<symbol>
Period=<timeframe_minutes>
FromDate=<start_date>
ToDate=<end_date>
ForwardMode=2
ForwardDate=<split_date>
Model=1
ExecutionMode=10
Optimization=2
OptimizationCriterion=6
Report=<deterministic_name>
ReplaceReport=1
UseLocal=1
Visual=0
ShutdownTerminal=1
Deposit=3000
Currency=GBP
Leverage=100

[TesterInputs]
<param_name>=<default>||<start>||<step>||<stop>||<Y/N>
```

**Parameter Line Format:**
- `Y` = optimize this parameter
- `N` = fixed value (not optimized)
- Boolean params: `value||0||0||0||N` (always fixed)

**Report Naming Pattern:**
```
<ea_stem>_S6_opt1_<symbol>_<timeframe>_<workflow_id[:8]>
```

---

### Step 7: Run Optimization (Pass 1 - Wide)

**Purpose:** Execute MT5 genetic optimization.

**Gate:**
- `passes_found >= 1`

**Optimization Settings:**
| Setting | Value |
|---------|-------|
| Algorithm | Genetic (Optimization=2) |
| Criterion | Custom (OptimizationCriterion=6, uses OnTester) |
| Timeout | 36,000 seconds (10 hours) |
| Max Passes Kept | 1,000 |

**Output:**
- XML results file path
- Total passes found
- Duration

---

### Step 8: Parse Results (Pass 1 - Wide)

**Purpose:** Parse MT5 optimization XML and filter valid passes.

**Gate:**
- `valid_passes >= 1`

**XML Format:** Excel Spreadsheet ML (Microsoft Office XML)

**Filtering:**
- Minimum trades: `ONTESTER_MIN_TRADES` (default: 10)

**Metrics Extracted:**
| Metric | MT5 Column |
|--------|------------|
| result | Result (OnTester return) |
| profit | Profit |
| profit_factor | Profit Factor |
| expected_payoff | Expected Payoff |
| max_drawdown_pct | Drawdown % |
| total_trades | Trades |
| sharpe_ratio | Sharpe Ratio |
| recovery_factor | Recovery Factor |
| win_rate | Win % |

**Forward Merge:** If forward report exists (`_fwd.xml`), merge forward-segment metrics.
Store back and forward metrics separately in pass records.

**Output:**
- pass1_results (for Stat Explorer and LLM analysis)
Pass 1 results are not used for final ranking; Pass 2 results drive selection and backtests.

---

### Step 8B: Stat Explorer (Pass 1)

**Purpose:** Build an evidence pack from Pass 1 results and representative trade lists for LLM-guided improvements.
This step is deterministic and does not use the LLM.

**Inputs:**
- pass1_results
- Step 5 trade list (fallback)
- Parameter usage map (from Step 3)
- Session windows based on STAT_EXPLORER_TIMEZONE (defaults: Asia 00:00-06:59, London 07:00-15:59, New York 13:00-21:59)

**Process:**
- Run a single backtest for the top Pass 1 candidate (highest OnTester) using the same window as Step 5
- If no trades are produced, fall back to the Step 5 trade list
- Compute session, hour, and day-of-week profitability and win rates
- Compute long vs short profitability and trade duration buckets
- Identify profit concentration (top X% trades vs total profit)
- Compute parameter sensitivity from Pass 1 (correlation of parameter values to result in top decile)

**Evidence Thresholds:**
- Ignore buckets with fewer than `STAT_MIN_TRADES_PER_BUCKET` trades
- Flag patterns only when effect size exceeds `STAT_MIN_EFFECT_PCT` vs overall baseline

**Output:**
- stat_explorer.json (metrics + evidence tables)
- session_bias flags (if any session dominates profitability)
- parameter_sensitivity summary

---

### Step 8C: LLM Improvement Proposal

**Purpose:** Use evidence from Stat Explorer to propose parameter refinements and EA enhancements/additions.

**Inputs:**
- pass1_results
- stat_explorer.json
- Parameter usage map
- EA source code (baseline)

**Offline LLM Flow (No API):**
- System writes `runs/analysis/<workflow_id>/llm/step8c_request.json`
- External LLM produces `step8c_response.json` in the same folder
- Workflow resumes when the response file exists and validates

**Output (llm_recommendations.json):**
```json
{
    "param_actions": [
        {
            "name": "FastMAPeriod",
            "action": "narrow_range|fix|remove",
            "rationale": "Evidence-based explanation",
            "evidence": ["param_sensitivity.FastMAPeriod corr=0.42"]
        }
    ],
    "range_refinements": [
        {
            "name": "FastMAPeriod",
            "start": 10,
            "step": 2,
            "stop": 40,
            "reason": "Top decile cluster"
        }
    ],
    "ea_patch": {
        "description": "Add London session lot multiplier",
        "diff": "<unified_diff_or_code_block>"
    },
    "expected_impact": [
        "Increase profit in London session where 62% of profit occurs"
    ],
    "risks": [
        "Higher drawdown if London volatility spikes"
    ],
    "review_required": true
}
```

**Rules:**
- Every recommendation MUST cite evidence from stat_explorer.json or pass1_results
- If evidence is weak, the LLM MUST return "no change" for that area
- New logic is allowed but MUST be tied to observed patterns (e.g., session bias)
- Session-based sizing changes require a clear profit concentration signal (>= STAT_MIN_SESSION_PROFIT_SHARE)
- LLM patches MUST NOT modify injected OnTester or safety guard code unless explicitly approved

---

### Step 8D: Manual Review and Apply Patch (Optional)

**Purpose:** Ensure all LLM changes are approved by a human before application.

**Pause Point:** Workflow pauses with `AWAITING_PATCH_REVIEW`.
Review is mandatory when `LLM_REVIEW_REQUIRED=True`.

**Review Package:**
- Patch diff
- Patch file path
- Evidence citations
- Expected impact and risks

**Behavior:**
- If approved, create a new EA version (do not modify the baseline file)
- If rejected, proceed with baseline EA and skip to Step 8F
- If reviewer requests follow-up, re-run Step 8C with reviewer feedback (max iterations: LLM_MAX_REFINEMENT_CYCLES)
- Apply the approved patch at the end of Step 8D, then proceed to Step 8E

**Output:**
- Approval decision
- Active EA version path

---

### Step 8E: Recompile and Re-Validate (If Patch Applied)

**Purpose:** Ensure the patched EA still trades using the same window as Step 5.

**Gate:**
- `error_count == 0`
- `total_trades >= MIN_TRADES`

**Regression Gate (vs baseline Step 5):**
- `net_profit >= baseline_net_profit * (1 - PATCH_MAX_PROFIT_DROP_PCT/100)`
- `profit_factor >= baseline_profit_factor * (1 - PATCH_MAX_PF_DROP_PCT/100)`
- `total_trades >= baseline_total_trades * (1 - PATCH_MAX_TRADES_DROP_PCT/100)`

**Failure Behavior:** Revert to baseline EA and continue with Step 8F.

---

### Step 8F: Create Optimization INI (Pass 2 - Refined)

**Purpose:** Generate Pass 2 optimization INI using refined ranges.
Uses the same INI structure as Step 6.
If no refinements are provided, reuse the Step 6 ranges.

**Report Naming Pattern:**
```
<ea_stem>_S8F_opt2_<symbol>_<timeframe>_<workflow_id[:8]>
```

---

### Step 8G: Run Optimization (Pass 2 - Refined)

**Purpose:** Execute MT5 genetic optimization on the active EA version.

**Gate:**
- `passes_found >= 1`

**Output:**
- XML results file path
- Total passes found
- Duration

---

### Step 8H: Parse Results (Pass 2 - Refined)

**Purpose:** Parse Pass 2 optimization XML and filter valid passes.
Uses the same extraction fields as Step 8.
Forward merge applies to Pass 2 results as well.
Store back and forward metrics separately in pass records.

**Gate:**
- `valid_passes >= 1`

**Output:**
- pass2_results

---

### Step 8I: Select Passes (Final)

**Purpose:** Select top passes for detailed backtesting using Pass 2 results.

**Selection Modes:**

**Auto-Selection** (if `AUTO_STATS_ANALYSIS=True`):
- Score all passes using Go Live Score formula
- Select top N passes (default: 20)
If `PASS1_COMPARE_ENABLED=True`, also include top `PASS1_COMPARE_TOP_N` passes from Pass 1 for comparison.

**Manual Selection:**
- Workflow pauses with `AWAITING_STATS_ANALYSIS`
- External process provides selected pass numbers

**Output:**
- List of selected pass numbers with source (pass1/pass2)

---

### Step 9: Backtest Top Passes

**Purpose:** Run detailed backtests of selected passes (Pass 1 and/or Pass 2) and apply all gates.
Backtests use the same forward split window as Step 5 and always record back and forward metrics.

**Gate (per pass):**
| Gate | Operator | Threshold (Default) |
|------|----------|---------------------|
| profit_factor | >= | 1.5 |
| max_drawdown | <= | 30% |
| minimum_trades | >= | 50 |

**Overall Gate:**
- `successful_passes >= 1`

**Best Pass Selection:**
| Mode | Primary | Secondary |
|------|---------|-----------|
| `score` (default) | Highest Go Live Score | Highest profit |
| `profit` | Highest profit | Highest score |

**Report Naming Pattern:**
```
S9_bt_pass<pass_num>_<symbol>_<timeframe>_<workflow_id[:8]>
```

**Output:**
- Per-pass back and forward metrics (profit, profit_factor, drawdown, trades)
- Best pass id and source (pass1/pass2)

---

### Step 10: Monte Carlo Simulation

**Purpose:** Test robustness via trade sequence shuffling.

**Gates:**
| Gate | Operator | Threshold (Default) |
|------|----------|---------------------|
| mc_confidence | >= | 70% |
| mc_ruin | <= | 5% |

**Simulation Parameters:**
| Parameter | Value |
|-----------|-------|
| Iterations | 10,000 |
| Initial Balance | 10,000 |
| Ruin Threshold | 50% drawdown |

**Algorithm:**
1. Extract trade list from best pass backtest
2. For each iteration:
   - Shuffle trade order randomly
   - Simulate account balance
   - Track final profit and max drawdown
3. Calculate percentiles

**Metrics Output:**
| Metric | Description |
|--------|-------------|
| confidence | % of profitable sequences (0-100) |
| ruin_probability | % hitting 50% drawdown (0-100) |
| expected_profit | Mean final profit |
| median_profit | 50th percentile |
| worst_case | 5th percentile |
| best_case | 95th percentile |
| max_drawdown_median | Median max DD |
| max_drawdown_worst | 95th percentile max DD |

---

### Step 11: Generate Reports

**Purpose:** Create visualization dashboards and global leaderboard.

**Gate:** None (always runs)

**Report Types:**

**1. Workflow Dashboard**
- Location: `runs/dashboards/<workflow_id>/index.html`
- Single-page application with embedded JSON
- Sections:
  - Header (EA name, symbol, timeframe, status)
  - Go Live Score gauge (0-10)
  - Gate results (pass/fail visualization)
  - Best pass metrics
  - Equity curve chart (in-sample vs forward)
  - Monte Carlo results
  - Stress scenario results (if run)
  - Forward window analysis (if run)
  - LLM improvement summary and EA version history (if run)
  - Pass comparison table (sortable)

**2. Leaderboard**
- Location: `runs/leaderboard/index.html`
- All workflows ranked by Go Live Score
- Columns: Workflow ID, EA Name, Symbol, Timeframe, Profit, PF, DD%, Trades, Score, Stress Pass Rate
- Sortable by any column

**3. Boards**
- Location: `runs/boards/index.html`
- Multi-workflow comparison view
- Falls back to Step 5 metrics if workflow failed later

---

### Step 12: Stress Scenarios

**Purpose:** Test robustness across execution conditions.

**Gate:** None (informational)

**Scenario Generation:**

**Time Windows:**
| Type | Values (Default) |
|------|------------------|
| Rolling Days | [7, 14, 30, 60, 90] |
| Calendar Months Ago | [1, 2, 3] |

**Models per Window:**
| Model | Value |
|-------|-------|
| OHLC (1-minute) | 1 |
| Every Tick | 0 |

**Tick-Only Latency Variants:**
| Latency | Value |
|---------|-------|
| High Latency | 250ms |
| Very High Latency | 5000ms |

**Cost Overlays (post-hoc from trade list):**
| Overlay | Values (Default) |
|---------|------------------|
| Spread (pips) | [0, 1, 2, 3, 5] |
| Slippage (pips) | [0, 1, 3] |
| Slippage Application | 2 (entry + exit) |

**Tick Validation:**
- Include tick-file coverage check
- Surface history quality % from MT5

---

### Step 13: Forward Windows

**Purpose:** Time-series analysis of best pass performance.

**Gate:** None (informational)

**Analysis (no MT5 runs - pure trade list analysis):**
| Window Type | Description |
|-------------|-------------|
| Full Period | All trades |
| In-Sample | Trades before split date |
| Forward | Trades after split date |
| Rolling | 7/14/30/60/90 day windows |
| Calendar Months | Per-month breakdown |
| Yearly | Per-year breakdown |

**Metrics per Window:**
- Trade count
- Net profit
- Profit factor
- Max drawdown %
- Win rate

---

### Step 14: Multi-Pair (Optional)

**Purpose:** Prepare for running same EA on additional symbols.

**Gate:** None (orchestration)

**Configuration:**
- `MULTI_PAIR_SYMBOLS` (default: ["EURUSD", "USDJPY"])
- `MULTI_PAIR_MODE` (default: "external")
- Filters out parent symbol

**Modes:**
- external: create child workflows per symbol using the same EA and parameters
- internal: EA is multi-symbol; keep a single workflow and let the EA handle extra symbols

**Internal Mode Notes:**
- Gates apply to the aggregated trade list unless per-symbol trade data is available
- If per-symbol metrics are required, the EA must expose symbol in the trade list

**Output:**
- List of symbols for child workflows
- Parent parameters for reuse

---

## 4. Scoring System

### 4.1 Go Live Score

**Purpose:** Answer "Should I trade this live<="

**Scale:** 0-10 (higher = more confident to deploy)

**Components:**
| Component | Weight | Description |
|-----------|--------|-------------|
| consistency | 25% | Both back + forward positive |
| total_profit | 25% | Actual money made |
| trade_count | 20% | Statistical confidence |
| profit_factor | 15% | Edge sustainability |
| max_drawdown | 15% | Risk tolerance (inverted) |

**Normalization Ranges:**
| Component | Min | Max | Notes |
|-----------|-----|-----|-------|
| total_profit | 0 | 5000 | Currency units |
| trade_count | 50 | 200 | Trades |
| profit_factor | 1.0 | 3.0 | Ratio |
| max_drawdown | 0 | 30 | % (inverted) |
| consistency_min | 0 | 2000 | min(back, forward) |

**Consistency Scoring:**
- Both positive: `normalize(min(back, forward))` = full credit
- One positive: `normalize(positive) * 0.25` = partial credit
- Both negative: 0

**Formula:**
```python
score = (
    consistency_score * 0.25 +
    profit_score * 0.25 +
    trades_score * 0.20 +
    pf_score * 0.15 +
    dd_score * 0.15
) * 10
```

---

## 5. Configuration Parameters

### 5.1 Backtest Settings

| Parameter | Default | Description |
|-----------|---------|-------------|
| BACKTEST_YEARS | 4 | Total period |
| IN_SAMPLE_YEARS | 3 | Training period |
| FORWARD_YEARS | 1 | Out-of-sample |
| DATA_MODEL | 1 | 0=Tick, 1=OHLC, 2=Open only |
| EXECUTION_LATENCY_MS | 10 | Simulated slippage |
| FORWARD_MODE | 2 | 1=Period-based, 2=Date-based |
| DEPOSIT | 3000 | Starting balance |
| CURRENCY | "GBP" | Account currency |
| LEVERAGE | 100 | Account leverage |

### 5.2 Gate Thresholds

| Parameter | Default | Description |
|-----------|---------|-------------|
| MIN_PROFIT_FACTOR | 1.5 | Minimum PF gate |
| MAX_DRAWDOWN_PCT | 30.0 | Maximum DD gate |
| MIN_TRADES | 50 | Minimum trade count |
| ONTESTER_MIN_TRADES | 10 | For optimization |
| MC_CONFIDENCE_MIN | 70.0 | Monte Carlo confidence % |
| MC_RUIN_MAX | 5.0 | Monte Carlo ruin % |
| OPTIMIZATION_TIMEOUT | 36000 | 10 hours |

### 5.3 Safety Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| SAFETY_DEFAULT_MAX_SPREAD_PIPS | 3.0 | Default spread limit |
| SAFETY_DEFAULT_MAX_SLIPPAGE_PIPS | 3.0 | Default slippage limit |
| SAFETY_VALIDATION_MAX_SPREAD_PIPS | 500.0 | Loose for Step 5 |
| SAFETY_VALIDATION_MAX_SLIPPAGE_PIPS | 500.0 | Loose for Step 5 |

### 5.4 Monte Carlo

| Parameter | Default | Description |
|-----------|---------|-------------|
| MC_ITERATIONS | 10000 | Simulation count |
| Initial Balance | 10000 | Starting equity |
| Ruin Threshold | 50% | Drawdown for ruin |

### 5.5 Scoring

| Parameter | Default | Description |
|-----------|---------|-------------|
| GO_LIVE_SCORE_WEIGHTS | See Section 4.1 | Component weights |
| GO_LIVE_SCORE_RANGES | See Section 4.1 | Normalization ranges |
| BEST_PASS_SELECTION | "score" | "score" or "profit" |

### 5.6 Automation

| Parameter | Default | Description |
|-----------|---------|-------------|
| AUTO_STATS_ANALYSIS | True | Auto-select passes |
| AUTO_STATS_TOP_N | 20 | Passes to select |
| AUTO_RUN_FORWARD_WINDOWS | True | Run Step 13 |
| AUTO_RUN_STRESS_SCENARIOS | True | Run Step 12 |
| AUTO_RUN_MULTI_PAIR | False | Run Step 14 |
| MULTI_PAIR_SYMBOLS | ["EURUSD", "USDJPY"] | Additional symbols |
| MULTI_PAIR_MODE | "external" | external=create child workflows, internal=EA handles symbols |
| PASS1_COMPARE_ENABLED | True | Include top Pass 1 results in final backtest pool |
| PASS1_COMPARE_TOP_N | 10 | Pass 1 candidates to backtest |
| LLM_IMPROVEMENT_ENABLED | True | Enable LLM improvement loop |
| LLM_REVIEW_REQUIRED | True | Manual approval required for EA patches |
| LLM_ALLOW_NEW_LOGIC | True | Allow new indicators/logic in patches |
| LLM_MAX_REFINEMENT_CYCLES | 1 | Max review-driven LLM follow-ups |
| STAT_EXPLORER_TIMEZONE | "UTC" | Time zone for session/hour analysis |
| STAT_MIN_TRADES_PER_BUCKET | 30 | Minimum trades per stat bucket |
| STAT_MIN_EFFECT_PCT | 10.0 | Minimum effect size vs baseline |
| STAT_MIN_SESSION_PROFIT_SHARE | 60.0 | Minimum profit share for session bias |
| PATCH_MAX_PROFIT_DROP_PCT | 20.0 | Max allowed net profit drop vs baseline |
| PATCH_MAX_PF_DROP_PCT | 10.0 | Max allowed PF drop vs baseline |
| PATCH_MAX_TRADES_DROP_PCT | 20.0 | Max allowed trade count drop vs baseline |

### 5.7 Stress Testing

| Parameter | Default | Description |
|-----------|---------|-------------|
| STRESS_WINDOW_ROLLING_DAYS | [7, 14, 30, 60, 90] | Day windows |
| STRESS_WINDOW_CALENDAR_MONTHS_AGO | [1, 2, 3] | Month windows |
| STRESS_WINDOW_MODELS | [1, 0] | OHLC and Tick |
| STRESS_TICK_LATENCY_MS | [250, 5000] | Latency variants |
| STRESS_OVERLAY_SPREAD_PIPS | [0, 1, 2, 3, 5] | Spread overlays |
| STRESS_OVERLAY_SLIPPAGE_PIPS | [0, 1, 3] | Slippage overlays |
| STRESS_OVERLAY_SLIPPAGE_SIDES | 2 | Entry + exit |

### 5.8 Optimization

| Parameter | Default | Description |
|-----------|---------|-------------|
| OPTIMIZATION_CRITERION | 6 | 6 = Custom (OnTester) |
| MAX_OPTIMIZATION_PASSES | 1000 | Max passes to keep |
| TOP_PASSES_DISPLAY | 20 | Dashboard display |
| TOP_PASSES_BACKTEST | 30 | Passes to backtest |

### 5.9 Risk Metrics (Targets, not gates)

| Parameter | Min | Target | Description |
|-----------|-----|--------|-------------|
| SHARPE_RATIO | 1.0 | 2.0 | Risk-adjusted return |
| SORTINO_RATIO | 1.5 | 2.5 | Downside-adjusted |
| CALMAR_RATIO | 1.0 | 3.0 | Return/max DD |
| RECOVERY_FACTOR | 2.0 | - | Profit/max DD |
| WIN_RATE | 40% | 55% | Win percentage |
| EXPECTED_PAYOFF | 5.0 | - | Avg profit/trade |
| RISK_FREE_RATE | 0.05 | - | For Sharpe calc |

---

## 6. Data Models

### 6.1 Workflow State

```json
{
    "workflow_id": "abc123xyz",
    "ea_name": "MyEA.mq5",
    "ea_path": "/path/to/MyEA.mq5",
    "symbol": "EURUSD",
    "timeframe": "H1",
    "status": "in_progress|completed|failed|awaiting_*",
    "created_at": "2024-01-15T10:30:00",
    "updated_at": "2024-01-15T11:45:00",
    "current_step": "7_run_optimization",
    "steps": {
        "<step_name>": {
            "step_name": "<name>",
            "passed": true|false,
            "result": {},
            "timestamp": "ISO8601",
            "error": null|"message"
        }
    },
    "ea_versions": [
        {
            "version": "v1",
            "path": "/path/to/MyEA.mq5",
            "source": "baseline|llm_patch",
            "approved": true,
            "created_at": "ISO8601"
        }
    ],
    "active_ea_version": "v1",
    "llm": {
        "stat_explorer_path": "/path/to/stat_explorer.json",
        "proposal_path": "/path/to/llm_recommendations.json",
        "review": {
            "approved": true,
            "notes": "Optional reviewer notes",
            "timestamp": "ISO8601"
        }
    },
    "metrics": {},
    "gates": {}
}
```

**Status Values:**
- PENDING
- IN_PROGRESS
- AWAITING_CONFIG (missing inputs or MT5 selection)
- AWAITING_PARAM_ANALYSIS (after Step 3)
- AWAITING_PATCH_REVIEW (after Step 8C)
- AWAITING_STATS_ANALYSIS (after Step 8I)
- AWAITING_EA_FIX (after Step 5 failure)
- COMPLETED
- FAILED

### 6.2 Parameter Format

```json
{
    "name": "FastMAPeriod",
    "type": "int",
    "base_type": "int",
    "default": "20",
    "comment": "Fast MA period",
    "line": 15,
    "optimizable": true
}
```

### 6.3 Pass Format

```json
{
    "result": 12345.67,
    "profit": 1234.56,
    "profit_factor": 1.8,
    "max_drawdown_pct": 15.2,
    "total_trades": 85,
    "win_rate": 55.3,
    "sharpe_ratio": 1.45,
    "expected_payoff": 14.53,
    "source": "pass1|pass2",
    "back": {
        "profit": 1200.00,
        "profit_factor": 1.7,
        "total_trades": 60
    },
    "forward": {
        "profit": 34.56,
        "profit_factor": 1.3,
        "total_trades": 25
    },
    "params": {
        "Pass": 42,
        "FastMAPeriod": 25,
        "Back Result": 1200.00,
        "Forward Result": 34.56
    }
}
```

### 6.4 Gate Result

```json
{
    "name": "profit_factor",
    "passed": true,
    "value": 1.8,
    "threshold": 1.5,
    "operator": ">=",
    "message": "PASS: profit_factor = 1.8 (>= 1.5)"
}
```

### 6.5 Monte Carlo Result

```json
{
    "iterations": 10000,
    "confidence": 85.3,
    "ruin_probability": 2.1,
    "expected_profit": 1250.00,
    "median_profit": 1180.00,
    "worst_case": -450.00,
    "best_case": 3200.00,
    "max_drawdown_median": 18.5,
    "max_drawdown_worst": 42.3
}
```

### 6.6 Stat Explorer Output

```json
{
    "session_stats": {
        "Asia": {"trades": 120, "profit": 300, "pf": 1.2, "win_rate": 52.0},
        "London": {"trades": 180, "profit": 950, "pf": 1.8, "win_rate": 61.0},
        "NewYork": {"trades": 90, "profit": 120, "pf": 1.1, "win_rate": 49.0}
    },
    "hour_stats": {
        "07": {"trades": 30, "profit": 220, "pf": 1.9},
        "08": {"trades": 28, "profit": 180, "pf": 1.6}
    },
    "dow_stats": {
        "Mon": {"trades": 60, "profit": 140},
        "Tue": {"trades": 70, "profit": 280}
    },
    "trade_duration_buckets": {
        "0-30m": {"trades": 90, "profit": 120},
        "30-120m": {"trades": 150, "profit": 620}
    },
    "long_short": {
        "long": {"trades": 140, "profit": 500},
        "short": {"trades": 110, "profit": 240}
    },
    "profit_concentration": {
        "top_20pct_trade_profit_share": 0.62
    },
    "parameter_sensitivity": [
        {"name": "FastMAPeriod", "corr_to_result": 0.42, "top_decile_median": 18}
    ]
}
```

### 6.7 LLM Proposal Format

```json
{
    "param_actions": [
        {
            "name": "FastMAPeriod",
            "action": "narrow_range",
            "rationale": "Top decile cluster",
            "evidence": ["param_sensitivity.FastMAPeriod corr=0.42"]
        }
    ],
    "range_refinements": [
        {"name": "FastMAPeriod", "start": 10, "step": 2, "stop": 40}
    ],
    "ea_patch": {
        "description": "Add London session lot multiplier",
        "diff": "<unified_diff_or_code_block>"
    },
    "expected_impact": ["Improve London session profitability"],
    "risks": ["Higher drawdown during high volatility"],
    "review_required": true
}
```
`ea_patch` is optional; if omitted, only parameter refinements are applied.

**Validation Schema (draft 2020-12):**
```json
{
    "type": "object",
    "required": ["param_actions", "range_refinements", "expected_impact", "risks", "review_required"],
    "properties": {
        "param_actions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "action", "rationale", "evidence"],
                "properties": {
                    "name": {"type": "string"},
                    "action": {"type": "string"},
                    "rationale": {"type": "string"},
                    "evidence": {"type": "array", "items": {"type": "string"}}
                }
            }
        },
        "range_refinements": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "start", "step", "stop"],
                "properties": {
                    "name": {"type": "string"},
                    "start": {"type": "number"},
                    "step": {"type": "number"},
                    "stop": {"type": "number"},
                    "reason": {"type": "string"}
                }
            }
        },
        "ea_patch": {
            "type": ["object", "null"],
            "properties": {
                "description": {"type": "string"},
                "diff": {"type": "string"}
            }
        },
        "expected_impact": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "review_required": {"type": "boolean"}
    }
}
```

---

## 7. File Structure

```
runs/
+-- dashboards/
|   +-- <workflow_id>/
|       +-- index.html
+-- leaderboard/
|   +-- index.html
+-- boards/
|   +-- index.html
+-- analysis/
|   +-- <workflow_id>/
|       +-- llm/
|       +-- patches/
|       +-- stat_explorer.json
+-- logs/
|   +-- <workflow_id>/
+-- reports/
|   +-- <workflow_id>/
+-- workflows/
|   +-- <workflow_id>/
+-- workflow_<id>.json

reports/
+-- templates/
    +-- dashboard_spa.html
    +-- leaderboard_spa.html
    +-- boards_spa.html
```

Additional analysis artifacts (Stat Explorer and LLM proposals) are stored under `runs/analysis/<workflow_id>/`.


---

## 8. Report Naming Convention

All MT5 reports MUST use deterministic names to prevent collisions:

```
S<step_or_substep>_<descriptor>_<symbol>_<timeframe>_<workflow_id[:8]>
```

**Examples:**
- `S5_validate_EURUSD_H1_abc12345`
- `S6_opt1_rsidiv_EURUSD_H1_abc12345`
- `S8F_opt2_rsidiv_EURUSD_H1_abc12345`
- `S9_bt_pass42_EURUSD_H1_abc12345`

---

## 9. Dashboard Requirements

### 9.1 Visual Elements

**Header:**
- EA name and version
- Symbol and timeframe
- Workflow status badge
- Go Live Score gauge (0-10 with color coding)
- Navigation to Leaderboard and Boards

**Gate Checklist:**
- Visual pass/fail indicators for all gates
- Threshold values shown
- Actual values shown
- Failure diagnosis if not go-live ready

**Metrics Panel:**
- Net profit
- Profit factor
- Max drawdown %
- Total trades
- Win rate
- Sharpe ratio
- Expected payoff

**Equity Chart:**
- Interactive Chart.js chart
- In-sample period (blue)
- Forward period (green)
- Vertical line at split date
- Drawdown visualization

**Pass Table:**
- All backtested passes
- Sortable by any column
- Gate status per pass
- Score per pass

**Monte Carlo Panel:**
- Confidence %
- Ruin probability %
- Profit distribution percentiles
- Drawdown distribution percentiles

**Stress Results Panel (if run):**
- Window * Model matrix
- Pass/fail per scenario
- Cost overlay results

**Forward Windows Panel (if run):**
- Time-series performance breakdown
- Rolling window metrics

### 9.2 Interactivity

- All tables sortable by clicking column headers
- Charts zoomable/pannable
- Tooltips on data points
- Navigation between related reports

---

## 10. Integration Points

### 10.1 Pause Points

| After Step | Status | Required Input |
|------------|--------|----------------|
| Before Step 1 | AWAITING_CONFIG | ea_path, symbol, timeframe, mt5_terminal_path |
| Step 3 | AWAITING_PARAM_ANALYSIS | wide_validation_params, optimization_ranges |
| Step 5 (fail) | AWAITING_EA_FIX | Fixed EA code |
| Step 8C | AWAITING_PATCH_REVIEW | Approve/reject LLM proposal, optional feedback |
| Step 8I | AWAITING_STATS_ANALYSIS | Selected pass numbers (if auto=False) |

### 10.2 Resume Methods

```python
# Before Step 1
runner.configure_inputs(
    ea_path="C:/path/to/EA.mq5",
    symbol="EURUSD",
    timeframe="H1",
    mt5_terminal_path="C:/Path/To/terminal64.exe"
)

# After Step 3
runner.continue_with_params(wide_validation_params, optimization_ranges)

# After Step 5 failure
runner.retry_after_fix()

# After Step 8C (manual LLM review)
runner.review_llm_proposal(approved=True, feedback=None)
runner.review_llm_proposal(approved=False, feedback="Refine session-based idea only")

# After Step 8I (manual selection)
runner.continue_with_analysis(selected_passes, analysis)
```

### 10.3 Programmatic Usage

```python
from ea_stress.pipeline import WorkflowRunner

runner = WorkflowRunner(
    ea_path="C:/path/to/EA.mq5",
    symbol="EURUSD",
    timeframe="H1",
    mt5_terminal_path="C:/Path/To/terminal64.exe",
    auto_stats_analysis=True
)

# Run until pause point
runner.run(pause_for_analysis=True)

# Resume with parameters
runner.continue_with_params(wide_params, opt_ranges)

# Optionally approve LLM proposal
runner.review_llm_proposal(approved=True, feedback=None)
```

---

## 11. Failure Diagnosis

When gates fail, the system MUST provide actionable diagnosis:

| Failed Gate | Diagnosis |
|-------------|-----------|
| profit_factor < threshold | Analyze avg win vs avg loss ratio; suggest tighter stops or better exits |
| max_drawdown > threshold | Suggest position sizing, trailing stops, or exposure reduction |
| minimum_trades < threshold | EA too selective; suggest widening entry conditions |
| mc_confidence < threshold | Results luck-dependent; reduce market condition dependency |
| mc_ruin > threshold | High blowup risk; reduce position sizes or add circuit breakers |

---

## 12. Appendix: Complete Settings Reference

```python
# Backtest
BACKTEST_YEARS = 4
IN_SAMPLE_YEARS = 3
FORWARD_YEARS = 1
DATA_MODEL = 1
EXECUTION_LATENCY_MS = 10
TICK_VALIDATION_DAYS = 30
FORWARD_MODE = 2
DEPOSIT = 3000
CURRENCY = "GBP"
LEVERAGE = 100

# Gates
MIN_PROFIT_FACTOR = 1.5
MAX_DRAWDOWN_PCT = 30.0
MIN_TRADES = 50
ONTESTER_MIN_TRADES = 10
OPTIMIZATION_TIMEOUT = 36000
MC_ITERATIONS = 10000
MC_CONFIDENCE_MIN = 70.0
MC_RUIN_MAX = 5.0

# Safety
SAFETY_DEFAULT_MAX_SPREAD_PIPS = 3.0
SAFETY_DEFAULT_MAX_SLIPPAGE_PIPS = 3.0
SAFETY_VALIDATION_MAX_SPREAD_PIPS = 500.0
SAFETY_VALIDATION_MAX_SLIPPAGE_PIPS = 500.0

# Risk Targets
MIN_SHARPE_RATIO = 1.0
TARGET_SHARPE_RATIO = 2.0
MIN_SORTINO_RATIO = 1.5
TARGET_SORTINO_RATIO = 2.5
MIN_CALMAR_RATIO = 1.0
TARGET_CALMAR_RATIO = 3.0
MIN_RECOVERY_FACTOR = 2.0
MIN_EXPECTED_PAYOFF = 5.0
MIN_WIN_RATE = 40.0
TARGET_WIN_RATE = 55.0
RISK_FREE_RATE = 0.05

# Scoring
GO_LIVE_SCORE_WEIGHTS = {
    'consistency': 0.25,
    'total_profit': 0.25,
    'trade_count': 0.20,
    'profit_factor': 0.15,
    'max_drawdown': 0.15,
}
GO_LIVE_SCORE_RANGES = {
    'total_profit': (0, 5000),
    'trade_count': (50, 200),
    'profit_factor': (1.0, 3.0),
    'max_drawdown': (0, 30),
    'consistency_min': (0, 2000),
}
BEST_PASS_SELECTION = "score"

# Automation
AUTO_STATS_ANALYSIS = True
AUTO_STATS_TOP_N = 20
AUTO_RUN_FORWARD_WINDOWS = True
AUTO_RUN_MULTI_PAIR = False
AUTO_RUN_STRESS_SCENARIOS = True
MULTI_PAIR_SYMBOLS = ["EURUSD", "USDJPY"]
MULTI_PAIR_MODE = "external"
PASS1_COMPARE_ENABLED = True
PASS1_COMPARE_TOP_N = 10
LLM_IMPROVEMENT_ENABLED = True
LLM_REVIEW_REQUIRED = True
LLM_ALLOW_NEW_LOGIC = True
LLM_MAX_REFINEMENT_CYCLES = 1
STAT_EXPLORER_TIMEZONE = "UTC"
STAT_MIN_TRADES_PER_BUCKET = 30
STAT_MIN_EFFECT_PCT = 10.0
STAT_MIN_SESSION_PROFIT_SHARE = 60.0
PATCH_MAX_PROFIT_DROP_PCT = 20.0
PATCH_MAX_PF_DROP_PCT = 10.0
PATCH_MAX_TRADES_DROP_PCT = 20.0

# Stress Testing
STRESS_WINDOW_ROLLING_DAYS = [7, 14, 30, 60, 90]
STRESS_WINDOW_CALENDAR_MONTHS_AGO = [1, 2, 3]
STRESS_WINDOW_MODELS = [1, 0]
STRESS_TICK_LATENCY_MS = [250, 5000]
STRESS_INCLUDE_OVERLAYS = True
STRESS_OVERLAY_SPREAD_PIPS = [0.0, 1.0, 2.0, 3.0, 5.0]
STRESS_OVERLAY_SLIPPAGE_PIPS = [0.0, 1.0, 3.0]
STRESS_OVERLAY_SLIPPAGE_SIDES = 2

# Optimization
OPTIMIZATION_CRITERION = 6
MAX_OPTIMIZATION_PASSES = 1000
TOP_PASSES_DISPLAY = 20
TOP_PASSES_BACKTEST = 30

# Parameter Stability
PARAM_STABILITY_RANGE = 0.10
PARAM_STABILITY_MIN_RETENTION = 0.70

# Correlation
MAX_EA_CORRELATION = 0.70
CORRELATION_LOOKBACK_DAYS = 252

# Re-optimization
REOPT_TOGGLE_THRESHOLD = 0.70
REOPT_CLUSTERING_CV_THRESHOLD = 0.20
REOPT_MIN_VALID_PASSES = 50
REOPT_MAX_ITERATIONS = 2

# Paths
RUNS_DIR = "runs"
DASHBOARDS_DIR = "runs/dashboards"
LEADERBOARD_DIR = "runs/leaderboard"
MT5_TERMINAL_PATH = "C:/Path/To/terminal64.exe"
```

---

**Document Version:** 2.0
**Last Updated:** January 2025

