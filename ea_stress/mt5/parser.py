"""MT5 XML Report Parser.

This module handles parsing of MT5 optimization and backtest reports
in Excel Spreadsheet ML (Microsoft Office XML) format.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


# XML namespaces used by MT5 reports
NS = {
    'ss': 'urn:schemas-microsoft-com:office:spreadsheet',
    'o': 'urn:schemas-microsoft-com:office:office',
    'x': 'urn:schemas-microsoft-com:office:excel'
}


@dataclass
class OptimizationPass:
    """Single optimization pass result."""
    pass_number: int
    result: float  # OnTester return value
    profit: float
    profit_factor: float
    expected_payoff: float
    max_drawdown_pct: float
    total_trades: int
    sharpe_ratio: float
    recovery_factor: float
    win_rate: float

    # Parameter values for this pass
    parameters: Dict[str, Any] = field(default_factory=dict)

    # Forward metrics (if forward testing was enabled)
    forward_profit: Optional[float] = None
    forward_profit_factor: Optional[float] = None
    forward_total_trades: Optional[int] = None
    forward_drawdown_pct: Optional[float] = None
    forward_win_rate: Optional[float] = None


@dataclass
class BacktestMetrics:
    """Parsed backtest metrics from HTML or XML report."""
    profit: float
    profit_factor: float
    expected_payoff: float
    max_drawdown_pct: float
    total_trades: int
    sharpe_ratio: float
    recovery_factor: float
    win_rate: float

    # Additional metrics
    balance: float = 0.0
    equity: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0

    # Forward metrics (if available)
    forward_profit: Optional[float] = None
    forward_profit_factor: Optional[float] = None
    forward_total_trades: Optional[int] = None
    forward_drawdown_pct: Optional[float] = None
    forward_win_rate: Optional[float] = None


class MT5XMLParser:
    """Parser for MT5 XML reports in Excel Spreadsheet ML format."""

    def __init__(self, xml_path: Path):
        """Initialize parser.

        Args:
            xml_path: Path to MT5 XML report file
        """
        self.xml_path = Path(xml_path)
        if not self.xml_path.exists():
            raise FileNotFoundError(f"XML file not found: {xml_path}")

        self.tree = ET.parse(self.xml_path)
        self.root = self.tree.getroot()

    def parse_optimization_results(
        self,
        min_trades: int = 10
    ) -> List[OptimizationPass]:
        """Parse optimization results from XML.

        Args:
            min_trades: Minimum trades required to include a pass

        Returns:
            List of OptimizationPass objects, filtered by min_trades
        """
        passes = []

        # Find the worksheet containing optimization results
        worksheet = self._find_worksheet("Optimization Graph")
        if worksheet is None:
            # Try alternative names
            worksheet = self._find_worksheet("Optimization Results")
        if worksheet is None:
            worksheet = self._find_worksheet("Results")

        if worksheet is None:
            return passes

        # Find the table in the worksheet
        table = worksheet.find('.//ss:Table', NS)
        if table is None:
            return passes

        # Parse header row to get column indices
        rows = table.findall('.//ss:Row', NS)
        if not rows:
            return passes

        header_row = rows[0]
        column_map = self._parse_header_row(header_row)

        # Parse data rows
        for idx, row in enumerate(rows[1:], start=1):
            try:
                pass_data = self._parse_optimization_row(row, column_map)
                if pass_data is not None and pass_data.total_trades >= min_trades:
                    pass_data.pass_number = idx
                    passes.append(pass_data)
            except (ValueError, KeyError, TypeError) as e:
                # Skip malformed rows
                continue

        return passes

    def parse_backtest_metrics(self) -> Optional[BacktestMetrics]:
        """Parse single backtest metrics from XML.

        Returns:
            BacktestMetrics object or None if parsing fails
        """
        # Find the summary worksheet
        worksheet = self._find_worksheet("Result")
        if worksheet is None:
            worksheet = self._find_worksheet("Summary")

        if worksheet is None:
            return None

        # Extract metrics from key-value pairs
        table = worksheet.find('.//ss:Table', NS)
        if table is None:
            return None

        metrics = {}
        rows = table.findall('.//ss:Row', NS)

        for row in rows:
            cells = row.findall('.//ss:Cell', NS)
            if len(cells) >= 2:
                key_cell = cells[0].find('.//ss:Data', NS)
                value_cell = cells[1].find('.//ss:Data', NS)

                if key_cell is not None and value_cell is not None:
                    key = key_cell.text
                    value = value_cell.text
                    if key and value:
                        metrics[key.strip()] = value.strip()

        # Map to BacktestMetrics
        try:
            return BacktestMetrics(
                profit=self._parse_float(metrics.get("Total net profit", "0")),
                profit_factor=self._parse_float(metrics.get("Profit factor", "0")),
                expected_payoff=self._parse_float(metrics.get("Expected payoff", "0")),
                max_drawdown_pct=self._parse_float(metrics.get("Maximal drawdown", "0%").rstrip("%")),
                total_trades=self._parse_int(metrics.get("Total trades", "0")),
                sharpe_ratio=self._parse_float(metrics.get("Sharpe ratio", "0")),
                recovery_factor=self._parse_float(metrics.get("Recovery factor", "0")),
                win_rate=self._parse_float(metrics.get("Profit trades (% of total)", "0%").rstrip("%")),
                balance=self._parse_float(metrics.get("Balance", "0")),
                equity=self._parse_float(metrics.get("Equity", "0")),
                gross_profit=self._parse_float(metrics.get("Gross profit", "0")),
                gross_loss=self._parse_float(metrics.get("Gross loss", "0")),
                max_consecutive_wins=self._parse_int(metrics.get("Maximum consecutive wins", "0")),
                max_consecutive_losses=self._parse_int(metrics.get("Maximum consecutive losses", "0"))
            )
        except (KeyError, ValueError):
            return None

    def merge_forward_metrics(
        self,
        passes: List[OptimizationPass],
        forward_xml_path: Path
    ) -> List[OptimizationPass]:
        """Merge forward testing metrics into optimization passes.

        Args:
            passes: List of optimization passes from back period
            forward_xml_path: Path to forward period XML report

        Returns:
            Updated list of passes with forward metrics merged
        """
        if not forward_xml_path.exists():
            return passes

        try:
            forward_parser = MT5XMLParser(forward_xml_path)
            forward_passes = forward_parser.parse_optimization_results(min_trades=0)

            # Create a mapping of parameters to forward results
            forward_map = {}
            for fp in forward_passes:
                # Use parameter tuple as key
                param_key = tuple(sorted(fp.parameters.items()))
                forward_map[param_key] = fp

            # Merge forward metrics into back passes
            for pass_obj in passes:
                param_key = tuple(sorted(pass_obj.parameters.items()))
                if param_key in forward_map:
                    forward = forward_map[param_key]
                    pass_obj.forward_profit = forward.profit
                    pass_obj.forward_profit_factor = forward.profit_factor
                    pass_obj.forward_total_trades = forward.total_trades
                    pass_obj.forward_drawdown_pct = forward.max_drawdown_pct
                    pass_obj.forward_win_rate = forward.win_rate

            return passes

        except Exception:
            # If forward merge fails, return original passes
            return passes

    def _find_worksheet(self, name: str) -> Optional[ET.Element]:
        """Find worksheet by name.

        Args:
            name: Worksheet name

        Returns:
            Worksheet element or None
        """
        worksheets = self.root.findall('.//ss:Worksheet', NS)
        for ws in worksheets:
            ws_name = ws.get('{%s}Name' % NS['ss'])
            if ws_name == name:
                return ws
        return None

    def _parse_header_row(self, row: ET.Element) -> Dict[str, int]:
        """Parse header row to create column name to index mapping.

        Args:
            row: Header row element

        Returns:
            Dictionary mapping column names to indices
        """
        column_map = {}
        cells = row.findall('.//ss:Cell', NS)

        for idx, cell in enumerate(cells):
            data = cell.find('.//ss:Data', NS)
            if data is not None and data.text:
                column_map[data.text.strip()] = idx

        return column_map

    def _parse_optimization_row(
        self,
        row: ET.Element,
        column_map: Dict[str, int]
    ) -> Optional[OptimizationPass]:
        """Parse a single optimization result row.

        Args:
            row: Row element
            column_map: Column name to index mapping

        Returns:
            OptimizationPass object or None if parsing fails
        """
        cells = row.findall('.//ss:Cell', NS)
        if not cells:
            return None

        # Extract cell values
        def get_cell_value(col_name: str, default: str = "0") -> str:
            idx = column_map.get(col_name)
            if idx is not None and idx < len(cells):
                data = cells[idx].find('.//ss:Data', NS)
                if data is not None and data.text:
                    return data.text.strip()
            return default

        # Extract standard metrics
        try:
            pass_data = OptimizationPass(
                pass_number=0,  # Will be set by caller
                result=self._parse_float(get_cell_value("Result")),
                profit=self._parse_float(get_cell_value("Profit")),
                profit_factor=self._parse_float(get_cell_value("Profit Factor")),
                expected_payoff=self._parse_float(get_cell_value("Expected Payoff")),
                max_drawdown_pct=self._parse_float(get_cell_value("Drawdown %")),
                total_trades=self._parse_int(get_cell_value("Trades")),
                sharpe_ratio=self._parse_float(get_cell_value("Sharpe Ratio")),
                recovery_factor=self._parse_float(get_cell_value("Recovery Factor")),
                win_rate=self._parse_float(get_cell_value("Win %"))
            )

            # Extract parameter values (all columns not in standard metrics)
            standard_cols = {
                "Result", "Profit", "Profit Factor", "Expected Payoff",
                "Drawdown %", "Trades", "Sharpe Ratio", "Recovery Factor", "Win %",
                "Pass", "#"
            }

            for col_name, col_idx in column_map.items():
                if col_name not in standard_cols and col_idx < len(cells):
                    data = cells[col_idx].find('.//ss:Data', NS)
                    if data is not None and data.text:
                        # Try to parse as number, fallback to string
                        try:
                            value = float(data.text.strip())
                            if value.is_integer():
                                value = int(value)
                            pass_data.parameters[col_name] = value
                        except ValueError:
                            pass_data.parameters[col_name] = data.text.strip()

            return pass_data

        except (ValueError, KeyError):
            return None

    def _parse_float(self, value: str) -> float:
        """Parse string to float, handling MT5 formatting."""
        if not value or value == "-":
            return 0.0
        # Remove spaces and common formatting
        value = value.replace(" ", "").replace(",", "")
        return float(value)

    def _parse_int(self, value: str) -> int:
        """Parse string to int, handling MT5 formatting."""
        if not value or value == "-":
            return 0
        # Remove spaces and common formatting
        value = value.replace(" ", "").replace(",", "")
        return int(float(value))


def parse_optimization_xml(
    xml_path: Path,
    min_trades: int = 10,
    forward_xml_path: Optional[Path] = None
) -> List[OptimizationPass]:
    """Convenience function to parse optimization results.

    Args:
        xml_path: Path to optimization XML file
        min_trades: Minimum trades to include a pass
        forward_xml_path: Optional path to forward period XML

    Returns:
        List of OptimizationPass objects
    """
    parser = MT5XMLParser(xml_path)
    passes = parser.parse_optimization_results(min_trades=min_trades)

    if forward_xml_path:
        passes = parser.merge_forward_metrics(passes, forward_xml_path)

    return passes


def parse_backtest_xml(xml_path: Path) -> Optional[BacktestMetrics]:
    """Convenience function to parse single backtest metrics.

    Args:
        xml_path: Path to backtest XML file

    Returns:
        BacktestMetrics object or None
    """
    parser = MT5XMLParser(xml_path)
    return parser.parse_backtest_metrics()
