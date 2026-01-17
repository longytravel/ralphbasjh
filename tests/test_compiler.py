"""Tests for MT5 compiler module."""

import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import subprocess

from ea_stress.mt5.compiler import (
    MT5Compiler,
    CompilationResult,
    CompilationError,
    compile_ea
)
from ea_stress.mt5.terminal import MT5Installation


class TestCompilationError(unittest.TestCase):
    """Test CompilationError dataclass."""

    def test_error_creation(self):
        """Test creating a compilation error."""
        error = CompilationError(
            file="MyEA.mq5",
            line=123,
            column=45,
            severity="error",
            code="001",
            message="unexpected token"
        )
        self.assertEqual(error.file, "MyEA.mq5")
        self.assertEqual(error.line, 123)
        self.assertEqual(error.severity, "error")

    def test_error_string(self):
        """Test error string representation."""
        error = CompilationError(
            file="MyEA.mq5",
            line=123,
            column=45,
            severity="error",
            code="001",
            message="unexpected token"
        )
        result = str(error)
        self.assertIn("MyEA.mq5", result)
        self.assertIn("123", result)
        self.assertIn("error", result)


class TestCompilationResult(unittest.TestCase):
    """Test CompilationResult dataclass."""

    def test_successful_compilation(self):
        """Test successful compilation result."""
        result = CompilationResult(
            success=True,
            ex5_path=Path("test.ex5"),
            errors=[],
            warnings=[],
            stdout="Compilation successful",
            stderr="",
            exit_code=0,
            command="metaeditor64.exe /compile test.mq5"
        )
        self.assertTrue(result.success)
        self.assertEqual(result.error_count, 0)
        self.assertEqual(result.warning_count, 0)

    def test_failed_compilation(self):
        """Test failed compilation result."""
        errors = [
            CompilationError("test.mq5", 10, 5, "error", "001", "syntax error")
        ]
        result = CompilationResult(
            success=False,
            ex5_path=None,
            errors=errors,
            warnings=[],
            stdout="",
            stderr="error",
            exit_code=1,
            command="metaeditor64.exe /compile test.mq5"
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error_count, 1)

    def test_result_string(self):
        """Test result string representation."""
        result = CompilationResult(
            success=True,
            ex5_path=Path("test.ex5"),
            errors=[],
            warnings=[],
            stdout="",
            stderr="",
            exit_code=0,
            command=""
        )
        result_str = str(result)
        self.assertIn("SUCCESS", result_str)
        self.assertIn("0 errors", result_str)


class TestMT5Compiler(unittest.TestCase):
    """Test MT5Compiler class."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_installation = Mock(spec=MT5Installation)
        self.mock_installation.metaeditor_path = Path("C:/MT5/metaeditor64.exe")

    def test_compiler_init_success(self):
        """Test compiler initialization with valid MetaEditor."""
        with patch.object(Path, 'exists', return_value=True):
            compiler = MT5Compiler(self.mock_installation)
            self.assertEqual(compiler.metaeditor_path, Path("C:/MT5/metaeditor64.exe"))

    def test_compiler_init_no_metaeditor(self):
        """Test compiler initialization fails without MetaEditor."""
        with patch.object(Path, 'exists', return_value=False):
            with self.assertRaises(ValueError) as ctx:
                MT5Compiler(self.mock_installation)
            self.assertIn("MetaEditor not found", str(ctx.exception))

    def test_parse_error_output(self):
        """Test parsing compilation errors from output."""
        with patch.object(Path, 'exists', return_value=True):
            compiler = MT5Compiler(self.mock_installation)

        output = """MyEA.mq5(123,45) : error 001: unexpected token
MyEA.mq5(150,10) : warning 202: variable not used
"""
        errors, warnings = compiler._parse_output(output)

        self.assertEqual(len(errors), 1)
        self.assertEqual(len(warnings), 1)

        self.assertEqual(errors[0].file, "MyEA.mq5")
        self.assertEqual(errors[0].line, 123)
        self.assertEqual(errors[0].column, 45)
        self.assertEqual(errors[0].severity, "error")
        self.assertEqual(errors[0].code, "001")

        self.assertEqual(warnings[0].severity, "warning")
        self.assertEqual(warnings[0].line, 150)

    def test_parse_no_errors(self):
        """Test parsing output with no errors."""
        with patch.object(Path, 'exists', return_value=True):
            compiler = MT5Compiler(self.mock_installation)

        output = "Compilation successful\n0 error(s), 0 warning(s)"
        errors, warnings = compiler._parse_output(output)

        self.assertEqual(len(errors), 0)
        self.assertEqual(len(warnings), 0)

    @patch('subprocess.run')
    @patch.object(Path, 'exists')
    def test_compile_success(self, mock_exists, mock_run):
        """Test successful compilation."""
        # Setup mocks
        mock_exists.return_value = True
        mock_run.return_value = Mock(
            returncode=0,
            stdout="Compilation successful",
            stderr=""
        )

        compiler = MT5Compiler(self.mock_installation)
        source_path = Path("C:/MT5/MQL5/Experts/MyEA.mq5")

        result = compiler.compile(source_path)

        self.assertTrue(result.success)
        self.assertEqual(result.exit_code, 0)
        self.assertEqual(result.error_count, 0)
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_compile_with_errors(self, mock_run):
        """Test compilation with errors."""
        mock_run.return_value = Mock(
            returncode=1,
            stdout="MyEA.mq5(50,10) : error 001: syntax error",
            stderr=""
        )

        with patch.object(Path, 'exists') as mock_exists:
            # MetaEditor exists, source exists
            mock_exists.return_value = True
            compiler = MT5Compiler(self.mock_installation)
            source_path = Path("C:/MT5/MQL5/Experts/MyEA.mq5")

            # Override for ex5 file check - should not exist
            def exists_check():
                # Count how many times exists() was called
                if not hasattr(exists_check, 'call_count'):
                    exists_check.call_count = 0
                exists_check.call_count += 1
                # .ex5 file check is at the end, return False for it
                if exists_check.call_count > 2:
                    return False
                return True

            mock_exists.side_effect = exists_check
            result = compiler.compile(source_path)

        self.assertFalse(result.success)
        self.assertEqual(result.error_count, 1)
        self.assertEqual(result.errors[0].line, 50)

    @patch.object(Path, 'exists')
    def test_compile_source_not_found(self, mock_exists):
        """Test compilation with missing source file."""
        mock_exists.side_effect = lambda: mock_exists.call_count <= 1

        compiler = MT5Compiler(self.mock_installation)
        source_path = Path("C:/MT5/MQL5/Experts/Missing.mq5")

        with self.assertRaises(FileNotFoundError):
            compiler.compile(source_path)

    @patch.object(Path, 'exists')
    def test_compile_invalid_extension(self, mock_exists):
        """Test compilation with invalid file extension."""
        mock_exists.return_value = True

        compiler = MT5Compiler(self.mock_installation)
        source_path = Path("C:/MT5/MQL5/Experts/MyEA.txt")

        with self.assertRaises(ValueError) as ctx:
            compiler.compile(source_path)
        self.assertIn("Invalid source file extension", str(ctx.exception))

    @patch('subprocess.run')
    @patch.object(Path, 'exists')
    def test_compile_timeout(self, mock_exists, mock_run):
        """Test compilation timeout."""
        mock_exists.return_value = True
        mock_run.side_effect = subprocess.TimeoutExpired(cmd='metaeditor', timeout=10)

        compiler = MT5Compiler(self.mock_installation)
        source_path = Path("C:/MT5/MQL5/Experts/MyEA.mq5")

        result = compiler.compile(source_path, timeout=10)

        self.assertFalse(result.success)
        self.assertEqual(result.error_count, 1)
        self.assertIn("timed out", result.errors[0].message.lower())

    def test_validate_ex5_success(self):
        """Test validating existing .ex5 file."""
        with patch.object(Path, 'exists', return_value=True):
            with patch.object(Path, 'is_file', return_value=True):
                with patch.object(Path, 'stat') as mock_stat:
                    mock_stat.return_value.st_size = 1024

                    compiler = MT5Compiler(self.mock_installation)
                    ex5_path = Path("test.ex5")

                    result = compiler.validate_ex5(ex5_path)
                    self.assertTrue(result)

    def test_validate_ex5_not_exists(self):
        """Test validating non-existent .ex5 file."""
        with patch.object(Path, 'exists', return_value=True):
            compiler = MT5Compiler(self.mock_installation)
            ex5_path = Path("missing.ex5")

            with patch.object(Path, 'exists', return_value=False):
                result = compiler.validate_ex5(ex5_path)
                self.assertFalse(result)

    def test_validate_ex5_empty(self):
        """Test validating empty .ex5 file."""
        with patch.object(Path, 'exists', return_value=True):
            with patch.object(Path, 'is_file', return_value=True):
                with patch.object(Path, 'stat') as mock_stat:
                    mock_stat.return_value.st_size = 0

                    compiler = MT5Compiler(self.mock_installation)
                    ex5_path = Path("empty.ex5")

                    result = compiler.validate_ex5(ex5_path)
                    self.assertFalse(result)

    def test_get_compiled_path(self):
        """Test getting compiled path for source file."""
        with patch.object(Path, 'exists', return_value=True):
            compiler = MT5Compiler(self.mock_installation)
            source_path = Path("C:/MT5/MQL5/Experts/MyEA.mq5")

            ex5_path = compiler.get_compiled_path(source_path)

            self.assertEqual(ex5_path, Path("C:/MT5/MQL5/Experts/MyEA.ex5"))


class TestCompileEA(unittest.TestCase):
    """Test compile_ea convenience function."""

    @patch('ea_stress.mt5.compiler.MT5Compiler')
    def test_compile_ea_function(self, mock_compiler_class):
        """Test compile_ea convenience function."""
        mock_installation = Mock(spec=MT5Installation)
        mock_compiler = Mock()
        mock_compiler_class.return_value = mock_compiler

        mock_result = Mock(spec=CompilationResult)
        mock_compiler.compile.return_value = mock_result

        source_path = Path("test.mq5")
        result = compile_ea(mock_installation, source_path)

        mock_compiler_class.assert_called_once_with(mock_installation)
        mock_compiler.compile.assert_called_once()
        self.assertEqual(result, mock_result)


if __name__ == '__main__':
    unittest.main()
