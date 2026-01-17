"""
Tests for Step 1C: Safety Guards Injection
"""

import os
import tempfile
import unittest
from ea_stress.workflow.steps.step01c_safety import (
    inject_safety_guards,
    validate_safety_injection,
    SafetyResult
)


class TestSafetyInjection(unittest.TestCase):
    """Test safety guard injection functionality."""

    def setUp(self):
        """Create temporary directory for test files."""
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        """Clean up temporary files."""
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def create_test_ea(self, content: str) -> str:
        """Create a test EA file with given content."""
        ea_path = os.path.join(self.temp_dir, "test_ea.mq5")
        with open(ea_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return ea_path

    def test_inject_basic_ea(self):
        """Test injection into basic EA."""
        ea_content = """
//+------------------------------------------------------------------+
//| Test EA                                                           |
//+------------------------------------------------------------------+
#property copyright "Test"
#property version   "1.00"

input int MagicNumber = 12345;

int OnInit()
{
   return INIT_SUCCEEDED;
}

void OnTick()
{
   // Trading logic
}
"""
        ea_path = self.create_test_ea(ea_content)
        result = inject_safety_guards(ea_path)

        self.assertEqual(result.status, 'injected')
        self.assertTrue(result.passed_gate())
        self.assertIsNotNone(result.output_path)
        self.assertTrue(os.path.exists(result.output_path))

        # Verify injection marker present
        self.assertTrue(validate_safety_injection(result.output_path))

    def test_inject_with_custom_values(self):
        """Test injection with custom spread and slippage values."""
        ea_content = """
#property version "1.00"

void OnTick() {}
"""
        ea_path = self.create_test_ea(ea_content)
        output_path = os.path.join(self.temp_dir, "custom_output.mq5")

        result = inject_safety_guards(ea_path, output_path,
                                     max_spread_pips=5.0,
                                     max_slippage_pips=2.5)

        self.assertEqual(result.status, 'injected')
        self.assertEqual(result.output_path, output_path)

        # Verify custom values in output
        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertIn('EAStressSafety_MaxSpreadPips = 5.0', content)
            self.assertIn('EAStressSafety_MaxSlippagePips = 2.5', content)

    def test_already_injected(self):
        """Test detection of already-injected safety guards."""
        ea_content = """
#property version "1.00"

// EA_STRESS_SAFETY_INJECTED

input double EAStressSafety_MaxSpreadPips = 3.0;

void OnTick() {}
"""
        ea_path = self.create_test_ea(ea_content)
        result = inject_safety_guards(ea_path)

        self.assertEqual(result.status, 'already_present')
        self.assertTrue(result.passed_gate())
        self.assertEqual(result.output_path, ea_path)

    def test_conflict_existing_maxspread_param(self):
        """Test conflict detection with existing MaxSpread parameter."""
        ea_content = """
#property version "1.00"

input double MaxSpreadPips = 5.0;

void OnTick() {}
"""
        ea_path = self.create_test_ea(ea_content)
        result = inject_safety_guards(ea_path)

        self.assertEqual(result.status, 'conflict')
        self.assertFalse(result.passed_gate())
        self.assertIn('MaxSpread', result.message)

    def test_conflict_existing_maxslippage_param(self):
        """Test conflict detection with existing MaxSlippage parameter."""
        ea_content = """
#property version "1.00"

input double MaxSlippagePips = 2.0;

void OnTick() {}
"""
        ea_path = self.create_test_ea(ea_content)
        result = inject_safety_guards(ea_path)

        self.assertEqual(result.status, 'conflict')
        self.assertFalse(result.passed_gate())
        self.assertIn('MaxSlippage', result.message)

    def test_conflict_existing_isspreadok_function(self):
        """Test conflict detection with existing IsSpreadOk function."""
        ea_content = """
#property version "1.00"

bool IsSpreadOk()
{
   return true;
}

void OnTick() {}
"""
        ea_path = self.create_test_ea(ea_content)
        result = inject_safety_guards(ea_path)

        self.assertEqual(result.status, 'conflict')
        self.assertFalse(result.passed_gate())
        self.assertIn('IsSpreadOk', result.message)

    def test_conflict_ordersend_macro(self):
        """Test conflict detection with existing OrderSend macro."""
        ea_content = """
#property version "1.00"

#define OrderSend CustomOrderSend

void OnTick() {}
"""
        ea_path = self.create_test_ea(ea_content)
        result = inject_safety_guards(ea_path)

        self.assertEqual(result.status, 'conflict')
        self.assertFalse(result.passed_gate())
        self.assertIn('OrderSend macro', result.message)

    def test_injection_preserves_structure(self):
        """Test that injection preserves EA structure."""
        ea_content = """
//+------------------------------------------------------------------+
//| Test EA                                                           |
//+------------------------------------------------------------------+
#property copyright "Test"
#property version   "1.00"

input int FastPeriod = 10;
input int SlowPeriod = 20;

int OnInit()
{
   Print("EA initialized");
   return INIT_SUCCEEDED;
}

void OnTick()
{
   // Trading logic here
}

void OnDeinit(const int reason)
{
   Print("EA deinitialized");
}
"""
        ea_path = self.create_test_ea(ea_content)
        result = inject_safety_guards(ea_path)

        self.assertEqual(result.status, 'injected')

        # Verify structure preserved
        with open(result.output_path, 'r', encoding='utf-8') as f:
            content = f.read()

            # Original code should still be present
            self.assertIn('FastPeriod = 10', content)
            self.assertIn('SlowPeriod = 20', content)
            self.assertIn('EA initialized', content)
            self.assertIn('EA deinitialized', content)

            # Safety code should be present
            self.assertIn('EA_STRESS_SAFETY_INJECTED', content)
            self.assertIn('EAStressSafety_IsSpreadOk', content)
            self.assertIn('EAStressSafety_MaxDeviationPoints', content)
            self.assertIn('STRESS_TEST_MODE', content)

            # Safety code should come before OnInit
            safety_pos = content.find('EA_STRESS_SAFETY_INJECTED')
            oninit_pos = content.find('int OnInit()')
            self.assertLess(safety_pos, oninit_pos)

    def test_injection_includes_all_guards(self):
        """Test that injection includes all required safety guards."""
        ea_content = """
#property version "1.00"
void OnTick() {}
"""
        ea_path = self.create_test_ea(ea_content)
        result = inject_safety_guards(ea_path)

        with open(result.output_path, 'r', encoding='utf-8') as f:
            content = f.read()

            # Check parameters
            self.assertIn('input double EAStressSafety_MaxSpreadPips', content)
            self.assertIn('input double EAStressSafety_MaxSlippagePips', content)

            # Check functions
            self.assertIn('double EAStressSafety_PipSize()', content)
            self.assertIn('bool EAStressSafety_IsSpreadOk()', content)
            self.assertIn('ulong EAStressSafety_MaxDeviationPoints()', content)
            self.assertIn('bool EAStressSafety_OrderSend_Impl(', content)
            self.assertIn('bool EAStressSafety_OrderSendAsync_Impl(', content)

            # Check macro overrides
            self.assertIn('#define OrderSend EAStressSafety_OrderSend_Impl', content)
            self.assertIn('#define OrderSendAsync EAStressSafety_OrderSendAsync_Impl', content)

            # Check macros
            self.assertIn('#define STRESS_TEST_MODE true', content)
            self.assertIn('#define FileOpen(a,b,c) INVALID_HANDLE', content)
            self.assertIn('#define FileWrite(a,b) 0', content)
            self.assertIn('#define FileDelete(a) false', content)
            self.assertIn('#define WebRequest(a,b,c,d,e,f,g) false', content)

    def test_file_not_found(self):
        """Test handling of non-existent file."""
        result = inject_safety_guards("nonexistent.mq5")

        self.assertEqual(result.status, 'error')
        self.assertFalse(result.passed_gate())
        self.assertIn('not found', result.message)

    def test_unicode_content(self):
        """Test handling of Unicode content in EA."""
        ea_content = """
//+------------------------------------------------------------------+
//| Test EA with Unicode: © ® ™ ♠ ♣                                  |
//+------------------------------------------------------------------+
#property copyright "Test © 2024"
#property version   "1.00"

void OnTick()
{
   Comment("Unicode test: α β γ δ");
}
"""
        ea_path = self.create_test_ea(ea_content)
        result = inject_safety_guards(ea_path)

        self.assertEqual(result.status, 'injected')
        self.assertTrue(os.path.exists(result.output_path))

        # Verify Unicode preserved
        with open(result.output_path, 'r', encoding='utf-8') as f:
            content = f.read()
            self.assertIn('©', content)
            self.assertIn('α β γ δ', content)

    def test_validate_safety_injection_true(self):
        """Test validation returns True for injected EA."""
        ea_content = """
// EA_STRESS_SAFETY_INJECTED
void OnTick() {}
"""
        ea_path = self.create_test_ea(ea_content)
        self.assertTrue(validate_safety_injection(ea_path))

    def test_validate_safety_injection_false(self):
        """Test validation returns False for non-injected EA."""
        ea_content = """
void OnTick() {}
"""
        ea_path = self.create_test_ea(ea_content)
        self.assertFalse(validate_safety_injection(ea_path))

    def test_to_dict(self):
        """Test SafetyResult serialization."""
        result = SafetyResult('injected', '/path/to/ea_safety.mq5',
                            'Safety guards injected successfully')
        result_dict = result.to_dict()

        self.assertEqual(result_dict['status'], 'injected')
        self.assertEqual(result_dict['output_path'], '/path/to/ea_safety.mq5')
        self.assertIn('Safety guards injected', result_dict['message'])
        self.assertTrue(result_dict['passed_gate'])

    def test_multiline_comment_skip(self):
        """Test that code in multiline comments is not detected as conflict."""
        ea_content = """
#property version "1.00"

/*
   Commented out code:
   input double MaxSpreadPips = 5.0;
   bool IsSpreadOk() { return true; }
*/

void OnTick() {}
"""
        ea_path = self.create_test_ea(ea_content)
        result = inject_safety_guards(ea_path)

        # Should succeed since conflicting code is commented out
        self.assertEqual(result.status, 'injected')
        self.assertTrue(result.passed_gate())


if __name__ == '__main__':
    unittest.main()
