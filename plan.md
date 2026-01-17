# EA Stress Test System - Build Plan

## Objective
Build a complete 14-step workflow engine that validates MetaTrader 5 Expert Advisors through optimization, backtesting, Monte Carlo simulation, and LLM-guided improvements.

## Phase 1: Project Foundation
- [x] Create project structure (src/, tests/, runs/, reports/)
- [x] Set up configuration system with all settings from PRD Section 12
- [x] Create workflow state model (JSON persistence)
- [x] Implement workflow status enum and state transitions

## Phase 2: MT5 Integration
- [x] Implement MT5 terminal discovery (autodiscover installations)
- [x] Create MetaEditor compilation wrapper
- [x] Build backtest runner with INI file generation
- [x] Build optimization runner
- [x] Create MT5 XML report parser (Excel Spreadsheet ML format)

## Phase 3: Core Workflow Steps 1-5
- [x] Step 1: Load EA (file validation)
- [x] Step 1B: OnTester function injection with R^2 calculation
- [x] Step 1C: Safety guards injection (spread/slippage controls)
- [x] Step 2: Compile EA using MetaEditor64
- [ ] Step 3: Extract parameters (regex parser for input declarations)
- [ ] Step 4: Parameter analysis (LLM offline JSON flow)
- [ ] Step 5: Validate trades (run backtest with wide params)

## Phase 4: Optimization Loop (Steps 6-8)
- [ ] Step 6: Create optimization INI (Pass 1 - Wide)
- [ ] Step 7: Run optimization (genetic algorithm)
- [ ] Step 8: Parse optimization results
- [ ] Step 8B: Stat Explorer (session/hour/DOW analysis)
- [ ] Step 8C: LLM improvement proposal generation
- [ ] Step 8D: Manual review and patch application
- [ ] Step 8E: Recompile and re-validate patched EA
- [ ] Step 8F: Create optimization INI (Pass 2 - Refined)
- [ ] Step 8G: Run optimization Pass 2
- [ ] Step 8H: Parse Pass 2 results
- [ ] Step 8I: Select passes for backtesting

## Phase 5: Validation Steps (9-13)
- [ ] Step 9: Backtest top passes with gates
- [ ] Step 10: Monte Carlo simulation (10k iterations)
- [ ] Step 11: Generate HTML dashboards and leaderboard
- [ ] Step 12: Stress scenarios (time windows, latency, costs)
- [ ] Step 13: Forward window analysis

## Phase 6: Advanced Features
- [ ] Step 14: Multi-pair orchestration
- [ ] Go Live Score calculation
- [ ] Gate failure diagnosis system
- [ ] Workflow resume from any checkpoint

## Phase 7: CLI and Polish
- [ ] Command-line interface (run, resume, status)
- [ ] Logging and audit trail
- [ ] Error handling and retry logic
- [ ] Documentation

## Tech Stack
- Python 3.10+
- No external dependencies for core (stdlib only where possible)
- Chart.js for dashboard charts (CDN)
- JSON Schema validation

## File Structure Target
```
ea_stress/
  __init__.py
  config.py
  models.py
  workflow/
    runner.py
    state.py
    steps/
      step01_load.py
      step01b_ontester.py
      step01c_safety.py
      step02_compile.py
      step03_extract.py
      step04_analyze.py
      step05_validate.py
      step06_ini.py
      step07_optimize.py
      step08_parse.py
      step08b_stat_explorer.py
      step08c_llm_proposal.py
      step08d_review.py
      step08e_revalidate.py
      step08f_ini_pass2.py
      step08g_optimize2.py
      step08h_parse2.py
      step08i_select.py
      step09_backtest.py
      step10_montecarlo.py
      step11_reports.py
      step12_stress.py
      step13_forward.py
      step14_multipair.py
  mt5/
    terminal.py
    compiler.py
    tester.py
    parser.py
  analysis/
    monte_carlo.py
    stat_explorer.py
    scoring.py
  reports/
    dashboard.py
    leaderboard.py
    boards.py
  cli.py
runs/
reports/templates/
tests/
```
