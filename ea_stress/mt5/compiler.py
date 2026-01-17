"""MT5 MetaEditor Compilation Wrapper.

This module handles:
- MQL5 source file compilation using MetaEditor64.exe
- Compilation result parsing (errors, warnings)
- .ex5 file validation
"""

import subprocess
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from .terminal import MT5Installation


@dataclass
class CompilationError:
    """Represents a compilation error or warning."""
    file: str
    line: int
    column: int
    severity: str  # 'error' or 'warning'
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.file}({self.line},{self.column}): {self.severity} {self.code}: {self.message}"


@dataclass
class CompilationResult:
    """Result of a compilation operation."""
    success: bool
    ex5_path: Optional[Path]
    errors: List[CompilationError]
    warnings: List[CompilationError]
    stdout: str
    stderr: str
    exit_code: int
    command: str

    @property
    def error_count(self) -> int:
        """Number of compilation errors."""
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        """Number of compilation warnings."""
        return len(self.warnings)

    def __str__(self) -> str:
        status = "SUCCESS" if self.success else "FAILED"
        return (f"Compilation {status}: "
                f"{self.error_count} errors, {self.warning_count} warnings")


class MT5Compiler:
    """Handles MQL5 source code compilation."""

    # MetaEditor error/warning pattern
    # Example: MyEA.mq5(123,45) : error 001: 'unexpected token'
    ERROR_PATTERN = re.compile(
        r'^(.+?)\((\d+),(\d+)\)\s*:\s*(error|warning)\s+(\d+)\s*:\s*(.+)$',
        re.IGNORECASE | re.MULTILINE
    )

    def __init__(self, installation: MT5Installation):
        """
        Initialize compiler with MT5 installation.

        Args:
            installation: MT5Installation object

        Raises:
            ValueError: If MetaEditor executable not found
        """
        self.installation = installation
        self.metaeditor_path = installation.metaeditor_path

        if not self.metaeditor_path.exists():
            raise ValueError(
                f"MetaEditor not found at {self.metaeditor_path}. "
                "Cannot compile MQL5 files."
            )

    def compile(self,
                source_path: Path,
                include_path: Optional[Path] = None,
                timeout: int = 120) -> CompilationResult:
        """
        Compile an MQL5 source file.

        Args:
            source_path: Path to .mq5 source file
            include_path: Optional additional include directory
            timeout: Compilation timeout in seconds (default: 120)

        Returns:
            CompilationResult object with compilation details

        Raises:
            FileNotFoundError: If source file doesn't exist
            ValueError: If source file is not .mq5 or .mq4
        """
        # Validate source file
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        if source_path.suffix.lower() not in ['.mq5', '.mq4']:
            raise ValueError(f"Invalid source file extension: {source_path.suffix}")

        # Build command
        cmd = [str(self.metaeditor_path), '/compile', str(source_path)]

        if include_path:
            cmd.extend(['/include', str(include_path)])

        # Log mode (suppresses GUI)
        cmd.append('/log')

        # Execute compilation
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(source_path.parent)
            )

            stdout = result.stdout
            stderr = result.stderr
            exit_code = result.returncode

        except subprocess.TimeoutExpired:
            return CompilationResult(
                success=False,
                ex5_path=None,
                errors=[CompilationError(
                    file=str(source_path),
                    line=0,
                    column=0,
                    severity='error',
                    code='TIMEOUT',
                    message=f'Compilation timed out after {timeout} seconds'
                )],
                warnings=[],
                stdout='',
                stderr='',
                exit_code=-1,
                command=' '.join(cmd)
            )

        # Parse errors and warnings from output
        errors, warnings = self._parse_output(stdout + '\n' + stderr)

        # Determine expected .ex5 path
        ex5_path = source_path.with_suffix('.ex5')

        # Check if compilation was successful
        success = (exit_code == 0 and
                   len(errors) == 0 and
                   ex5_path.exists())

        return CompilationResult(
            success=success,
            ex5_path=ex5_path if ex5_path.exists() else None,
            errors=errors,
            warnings=warnings,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            command=' '.join(cmd)
        )

    def _parse_output(self, output: str) -> Tuple[List[CompilationError], List[CompilationError]]:
        """
        Parse compilation output for errors and warnings.

        Args:
            output: Combined stdout and stderr from MetaEditor

        Returns:
            Tuple of (errors, warnings)
        """
        errors = []
        warnings = []

        for match in self.ERROR_PATTERN.finditer(output):
            file_path = match.group(1).strip()
            line_num = int(match.group(2))
            col_num = int(match.group(3))
            severity = match.group(4).lower()
            error_code = match.group(5)
            message = match.group(6).strip()

            error_obj = CompilationError(
                file=file_path,
                line=line_num,
                column=col_num,
                severity=severity,
                code=error_code,
                message=message
            )

            if severity == 'error':
                errors.append(error_obj)
            else:
                warnings.append(error_obj)

        return errors, warnings

    def validate_ex5(self, ex5_path: Path) -> bool:
        """
        Validate that an .ex5 file exists and is not empty.

        Args:
            ex5_path: Path to .ex5 file

        Returns:
            True if file is valid, False otherwise
        """
        if not ex5_path.exists():
            return False

        if not ex5_path.is_file():
            return False

        # Check file is not empty
        if ex5_path.stat().st_size == 0:
            return False

        return True

    def get_compiled_path(self, source_path: Path) -> Path:
        """
        Get expected .ex5 path for a source file.

        Args:
            source_path: Path to .mq5 source file

        Returns:
            Expected path to compiled .ex5 file
        """
        return source_path.with_suffix('.ex5')


def compile_ea(installation: MT5Installation,
               source_path: Path,
               include_path: Optional[Path] = None,
               timeout: int = 120) -> CompilationResult:
    """
    Convenience function to compile an EA.

    Args:
        installation: MT5Installation object
        source_path: Path to .mq5 source file
        include_path: Optional additional include directory
        timeout: Compilation timeout in seconds

    Returns:
        CompilationResult object
    """
    compiler = MT5Compiler(installation)
    return compiler.compile(source_path, include_path, timeout)
