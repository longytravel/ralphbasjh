"""
Step 1C: Inject Safety Guards
Adds trade safety parameters to control spread and slippage during testing.
"""

import os
import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class SafetyResult:
    """Result of safety guard injection."""
    status: str  # injected, already_present, skipped, conflict, error
    output_path: Optional[str]
    message: str

    def passed_gate(self) -> bool:
        """Check if safety injection succeeded or was already present."""
        return self.status in ('injected', 'already_present', 'skipped')

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'status': self.status,
            'output_path': self.output_path,
            'message': self.message,
            'passed_gate': self.passed_gate()
        }


def inject_safety_guards(ea_path: str, output_path: Optional[str] = None,
                        max_spread_pips: float = 3.0,
                        max_slippage_pips: float = 3.0) -> SafetyResult:
    """
    Inject safety guard functions and parameters into EA source.

    Args:
        ea_path: Path to EA source file
        output_path: Optional output path (defaults to ea_path with _safety suffix)
        max_spread_pips: Default max spread in pips
        max_slippage_pips: Default max slippage in pips

    Returns:
        SafetyResult with injection status
    """
    try:
        # Validate input file
        if not os.path.exists(ea_path):
            return SafetyResult('error', None, f'EA file not found: {ea_path}')

        # Read source code
        try:
            with open(ea_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(ea_path, 'r', encoding='utf-16') as f:
                content = f.read()

        # Check if already injected by this system
        if 'EA_STRESS_SAFETY_INJECTED' in content:
            return SafetyResult('already_present', ea_path,
                              'Safety guards already injected by this system')

        # Remove comments before checking for conflicts
        # Remove multiline comments /* ... */
        content_no_comments = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        # Remove single-line comments // ...
        content_no_comments = re.sub(r'//[^\n]*', '', content_no_comments)

        # Check for conflicts with existing safety features
        conflicts = []

        # Check for existing safety parameters
        if re.search(r'\binput\s+double\s+.*MaxSpread', content_no_comments, re.IGNORECASE):
            conflicts.append('Existing MaxSpread parameter detected')
        if re.search(r'\binput\s+double\s+.*MaxSlippage', content_no_comments, re.IGNORECASE):
            conflicts.append('Existing MaxSlippage parameter detected')

        # Check for existing safety functions
        if re.search(r'\b(bool|double)\s+.*IsSpreadOk\s*\(', content_no_comments):
            conflicts.append('Existing IsSpreadOk function detected')

        # Check for OrderSend macro override
        if re.search(r'#define\s+OrderSend\s+', content_no_comments):
            conflicts.append('OrderSend macro already defined')

        if conflicts:
            return SafetyResult('conflict', None,
                              f'Safety conflicts detected: {"; ".join(conflicts)}')

        # Prepare output path
        if output_path is None:
            base, ext = os.path.splitext(ea_path)
            output_path = f"{base}_safety{ext}"

        # Build injection code
        injection = f'''
//+------------------------------------------------------------------+
//| EA Stress Test System - Safety Guards                            |
//| Marker: EA_STRESS_SAFETY_INJECTED                                 |
//+------------------------------------------------------------------+

// Safety parameters
input double EAStressSafety_MaxSpreadPips = {max_spread_pips};
input double EAStressSafety_MaxSlippagePips = {max_slippage_pips};

// Calculate pip size based on broker digits
double EAStressSafety_PipSize()
{{
   int digits = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   if(digits == 2 || digits == 3)
      return 0.01;
   else if(digits == 4 || digits == 5)
      return 0.0001;
   else
      return 0.00001;
}}

// Check if current spread is acceptable
bool EAStressSafety_IsSpreadOk()
{{
   if(EAStressSafety_MaxSpreadPips <= 0)
      return true;  // No limit

   double spread = SymbolInfoDouble(_Symbol, SYMBOL_ASK) - SymbolInfoDouble(_Symbol, SYMBOL_BID);
   double spreadPips = spread / EAStressSafety_PipSize();

   return spreadPips <= EAStressSafety_MaxSpreadPips;
}}

// Calculate max deviation in points for slippage control
ulong EAStressSafety_MaxDeviationPoints()
{{
   if(EAStressSafety_MaxSlippagePips <= 0)
      return 0;  // No limit

   double pipSize = EAStressSafety_PipSize();
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);

   if(point <= 0)
      return 0;

   return (ulong)((EAStressSafety_MaxSlippagePips * pipSize) / point);
}}

// Safe OrderSend wrapper with spread and slippage checks
bool EAStressSafety_OrderSend(MqlTradeRequest &request, MqlTradeResult &result)
{{
   // Check spread before trading
   if(!EAStressSafety_IsSpreadOk())
   {{
      result.retcode = TRADE_RETCODE_INVALID_PRICE;
      result.comment = "Spread too wide";
      return false;
   }}

   // Set slippage limit
   if(request.deviation == 0)
      request.deviation = EAStressSafety_MaxDeviationPoints();

   // Execute trade
   return OrderSend(request, result);
}}

// Async version (rarely used, but include for completeness)
bool EAStressSafety_OrderSendAsync(MqlTradeRequest &request, MqlTradeResult &result)
{{
   if(!EAStressSafety_IsSpreadOk())
   {{
      result.retcode = TRADE_RETCODE_INVALID_PRICE;
      result.comment = "Spread too wide";
      return false;
   }}

   if(request.deviation == 0)
      request.deviation = EAStressSafety_MaxDeviationPoints();

   return OrderSendAsync(request, result);
}}

// File operation blockers for stress test mode
#define STRESS_TEST_MODE true
#define FileOpen(a,b,c) INVALID_HANDLE
#define FileWrite(a,b) 0
#define FileDelete(a) false
#define WebRequest(a,b,c,d,e,f,g) false

//+------------------------------------------------------------------+
'''

        # Find injection point (after #property directives, before OnInit)
        # Look for the first function definition or the end of properties
        lines = content.split('\n')
        injection_index = 0
        in_comment_block = False

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Track multiline comments
            if '/*' in stripped:
                in_comment_block = True
            if '*/' in stripped:
                in_comment_block = False
                continue

            if in_comment_block:
                continue

            # Skip single-line comments
            if stripped.startswith('//'):
                continue

            # Found a function definition - inject before this
            if re.match(r'^(int|void|double|bool|string|datetime)\s+\w+\s*\(', stripped):
                injection_index = i
                break

            # Found OnInit or OnTick - inject before this
            if re.match(r'^(int\s+)?On(Init|Tick|Deinit|Trade|Timer|ChartEvent)', stripped):
                injection_index = i
                break

        # If no function found, inject at the end
        if injection_index == 0:
            injection_index = len(lines)

        # Insert injection code
        lines.insert(injection_index, injection)
        modified_content = '\n'.join(lines)

        # Write modified EA
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(modified_content)
        except Exception as e:
            return SafetyResult('error', None, f'Failed to write output file: {e}')

        return SafetyResult('injected', output_path,
                          f'Safety guards injected successfully into {output_path}')

    except Exception as e:
        return SafetyResult('error', None, f'Injection failed: {str(e)}')


def validate_safety_injection(ea_path: str) -> bool:
    """
    Validate that safety guards are present in EA.

    Args:
        ea_path: Path to EA source file

    Returns:
        True if safety guards are present
    """
    try:
        with open(ea_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return 'EA_STRESS_SAFETY_INJECTED' in content
    except:
        return False
