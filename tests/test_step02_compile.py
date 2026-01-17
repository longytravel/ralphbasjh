"""Tests for Step 2: Compile EA."""

import unittest
from pathlib import Path
import tempfile
import shutil
from unittest.mock import Mock, patch

from ea_stress.workflow.steps.step02_compile import (
    compile_ea,
    validate_compilation,
    CompileStepResult
)
from ea_stress.mt5.terminal import MT5Installation
from ea_stress.mt5.compiler import CompilationResult, CompilationError


class TestCompileStepResult(unittest.TestCase):
    """Test CompileStepResult dataclass."""

    def test_passed_gate_success(self):
        """Test gate passes with no errors."""
        result = CompileStepResult(
            success=True,
            ex5_path=Path("test.ex5"),
            error_count=0,
            warning_count=2
        )
        self.assertTrue(result.passed_gate())

    def test_passed_gate_failure(self):
        """Test gate fails with errors."""
        result = CompileStepResult(
            success=False,
            ex5_path=None,
            error_count=3,
            warning_count=1
        )
        self.assertFalse(result.passed_gate())

    def test_to_dict(self):
        """Test dictionary conversion."""
        result = CompileStepResult(
            success=True,
            ex5_path=Path("test.ex5"),
            error_count=0,
            warning_count=1,
            errors=[],
            warnings=["Warning: unused variable"],
            source_path=Path("test.mq5"),
            exit_code=0,
            command="metaeditor.exe /compile test.mq5",
            error_message=None
        )

        d = result.to_dict()
        self.assertEqual(d['success'], True)
        self.assertEqual(d['error_count'], 0)
        self.assertEqual(d['warning_count'], 1)
        self.assertEqual(d['gate_passed'], True)
        self.assertIn('ex5_path', d)
        self.assertIn('errors', d)


class TestCompileEA(unittest.TestCase):
    """Test compile_ea function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

        # Create mock MT5 installation
        self.installation = Mock(spec=MT5Installation)
        self.installation.metaeditor_path = Path("C:/MT5/metaeditor64.exe")
        self.installation.terminal_path = Path("C:/MT5/terminal64.exe")
        self.installation.data_path = Path("C:/MT5/MQL5")

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_source_file_not_found(self):
        """Test compilation with non-existent source file."""
        source = self.temp_path / "nonexistent.mq5"

        result = compile_ea(source, self.installation)

        self.assertFalse(result.success)
        self.assertFalse(result.passed_gate())
        self.assertEqual(result.error_count, 1)
        self.assertIsNone(result.ex5_path)
        self.assertIn("not found", result.error_message.lower())

    def test_invalid_file_extension(self):
        """Test compilation with invalid file extension."""
        source = self.temp_path / "test.txt"
        source.write_text("// test")

        result = compile_ea(source, self.installation)

        self.assertFalse(result.success)
        self.assertFalse(result.passed_gate())
        self.assertEqual(result.error_count, 1)
        self.assertIn("extension", result.error_message.lower())

    def test_valid_mq5_file(self):
        """Test compilation with valid .mq5 file."""
        source = self.temp_path / "test.mq5"
        source.write_text("""
//+------------------------------------------------------------------+
//| Test EA                                                           |
//+------------------------------------------------------------------+
#property copyright "Test"
#property version   "1.00"

input int Period = 14;

void OnTick()
{
    // Trading logic here
}
//+------------------------------------------------------------------+
""")

        # Mock successful compilation
        mock_result = CompilationResult(
            success=True,
            ex5_path=source.with_suffix('.ex5'),
            errors=[],
            warnings=[],
            stdout="Compilation successful",
            stderr="",
            exit_code=0,
            command="metaeditor64.exe /compile test.mq5"
        )

        with patch('ea_stress.workflow.steps.step02_compile.MT5Compiler') as MockCompiler:
            mock_compiler = MockCompiler.return_value
            mock_compiler.compile.return_value = mock_result

            result = compile_ea(source, self.installation)

            self.assertTrue(result.success)
            self.assertTrue(result.passed_gate())
            self.assertEqual(result.error_count, 0)
            self.assertEqual(result.source_path, source)
            self.assertIsNotNone(result.ex5_path)

    def test_valid_mq4_file(self):
        """Test compilation accepts .mq4 files."""
        source = self.temp_path / "test.mq4"
        source.write_text("""
//+------------------------------------------------------------------+
//| Test EA                                                           |
//+------------------------------------------------------------------+
#property copyright "Test"
#property version   "1.00"

extern int Period = 14;

int start()
{
    // Trading logic here
    return(0);
}
//+------------------------------------------------------------------+
""")

        # Mock successful compilation
        mock_result = CompilationResult(
            success=True,
            ex5_path=source.with_suffix('.ex5'),
            errors=[],
            warnings=[],
            stdout="Compilation successful",
            stderr="",
            exit_code=0,
            command="metaeditor64.exe /compile test.mq4"
        )

        with patch('ea_stress.workflow.steps.step02_compile.MT5Compiler') as MockCompiler:
            mock_compiler = MockCompiler.return_value
            mock_compiler.compile.return_value = mock_result

            result = compile_ea(source, self.installation)

            self.assertTrue(result.success)
            self.assertEqual(result.source_path, source)

    def test_compilation_with_timeout(self):
        """Test compilation with custom timeout."""
        source = self.temp_path / "test.mq5"
        source.write_text("// minimal EA\n")

        mock_result = CompilationResult(
            success=True,
            ex5_path=source.with_suffix('.ex5'),
            errors=[],
            warnings=[],
            stdout="",
            stderr="",
            exit_code=0,
            command="metaeditor64.exe /compile test.mq5"
        )

        with patch('ea_stress.workflow.steps.step02_compile.MT5Compiler') as MockCompiler:
            mock_compiler = MockCompiler.return_value
            mock_compiler.compile.return_value = mock_result

            result = compile_ea(source, self.installation, timeout=30)

            # Verify timeout was passed to compiler
            mock_compiler.compile.assert_called_once_with(
                source_path=source,
                timeout=30
            )
            self.assertIsNotNone(result)
            self.assertIsInstance(result, CompileStepResult)

    def test_result_includes_metadata(self):
        """Test result includes all metadata fields."""
        source = self.temp_path / "test.mq5"
        source.write_text("// test\n")

        mock_result = CompilationResult(
            success=True,
            ex5_path=source.with_suffix('.ex5'),
            errors=[],
            warnings=[CompilationError("test.mq5", 1, 1, "warning", "W001", "unused variable")],
            stdout="",
            stderr="",
            exit_code=0,
            command="metaeditor64.exe /compile test.mq5"
        )

        with patch('ea_stress.workflow.steps.step02_compile.MT5Compiler') as MockCompiler:
            mock_compiler = MockCompiler.return_value
            mock_compiler.compile.return_value = mock_result

            result = compile_ea(source, self.installation)

            # Verify all fields are present
            self.assertIsNotNone(result.source_path)
            self.assertIsInstance(result.error_count, int)
            self.assertIsInstance(result.warning_count, int)
            self.assertIsInstance(result.errors, list)
            self.assertIsInstance(result.warnings, list)
            self.assertEqual(result.warning_count, 1)


class TestValidateCompilation(unittest.TestCase):
    """Test validate_compilation convenience function."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

        self.installation = Mock(spec=MT5Installation)
        self.installation.metaeditor_path = Path("C:/MT5/metaeditor64.exe")

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_validate_returns_bool(self):
        """Test validate_compilation returns boolean."""
        source = self.temp_path / "test.mq5"
        source.write_text("// test\n")

        mock_result = CompilationResult(
            success=True,
            ex5_path=source.with_suffix('.ex5'),
            errors=[],
            warnings=[],
            stdout="",
            stderr="",
            exit_code=0,
            command="metaeditor64.exe /compile test.mq5"
        )

        with patch('ea_stress.workflow.steps.step02_compile.MT5Compiler') as MockCompiler:
            mock_compiler = MockCompiler.return_value
            mock_compiler.compile.return_value = mock_result

            result = validate_compilation(source, self.installation)

            self.assertIsInstance(result, bool)
            self.assertTrue(result)

    def test_validate_nonexistent_file(self):
        """Test validation fails for nonexistent file."""
        source = self.temp_path / "nonexistent.mq5"

        result = validate_compilation(source, self.installation)

        self.assertFalse(result)


class TestWorkflowIntegration(unittest.TestCase):
    """Test Step 2 workflow integration."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

        self.installation = Mock(spec=MT5Installation)
        self.installation.metaeditor_path = Path("C:/MT5/metaeditor64.exe")

    def tearDown(self):
        """Clean up test fixtures."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_step2_follows_step1c(self):
        """Test Step 2 can process Step 1C output."""
        # Simulate Step 1C output file
        source = self.temp_path / "MyEA_ontester_safety.mq5"
        source.write_text("""
//+------------------------------------------------------------------+
//| EA with injected code                                            |
//+------------------------------------------------------------------+
#property copyright "Test"
#property version   "1.00"

// EA_STRESS_ONTESTER_INJECTED
double OnTester()
{
    return TesterStatistics(STAT_PROFIT);
}

// EA_STRESS_SAFETY_INJECTED
input double EAStressSafety_MaxSpreadPips = 3.0;
input double EAStressSafety_MaxSlippagePips = 3.0;

void OnTick()
{
    // Trading logic
}
//+------------------------------------------------------------------+
""")

        mock_result = CompilationResult(
            success=True,
            ex5_path=source.with_suffix('.ex5'),
            errors=[],
            warnings=[],
            stdout="",
            stderr="",
            exit_code=0,
            command="metaeditor64.exe /compile MyEA_ontester_safety.mq5"
        )

        with patch('ea_stress.workflow.steps.step02_compile.MT5Compiler') as MockCompiler:
            mock_compiler = MockCompiler.return_value
            mock_compiler.compile.return_value = mock_result

            result = compile_ea(source, self.installation)

            # Verify result structure is correct for workflow
            self.assertIsNotNone(result)
            self.assertIsInstance(result.to_dict(), dict)

            # Verify gate check
            gate_passed = result.passed_gate()
            self.assertIsInstance(gate_passed, bool)
            self.assertTrue(gate_passed)

    def test_failed_gate_provides_details(self):
        """Test failed compilation provides error details for workflow."""
        # Use non-existent file to trigger failure
        source = self.temp_path / "missing.mq5"

        result = compile_ea(source, self.installation)

        self.assertFalse(result.passed_gate())
        self.assertGreater(result.error_count, 0)
        self.assertTrue(len(result.errors) > 0)
        self.assertIsNotNone(result.error_message)

        # Verify error details are serializable
        result_dict = result.to_dict()
        self.assertIn('errors', result_dict)
        self.assertIn('error_message', result_dict)


if __name__ == '__main__':
    unittest.main()
