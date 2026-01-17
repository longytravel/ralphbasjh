"""Step 2: Compile EA using MetaEditor64.

This step:
- Compiles the modified EA source file using MetaEditor64
- Validates compilation success (no errors)
- Returns executable path and compilation details
- Implements gate: error_count == 0
"""

from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional

from ...mt5.compiler import MT5Compiler, CompilationResult
from ...mt5.terminal import MT5Installation


@dataclass
class CompileStepResult:
    """Result of Step 2: Compile EA."""

    # Core results
    success: bool
    ex5_path: Optional[Path]
    error_count: int
    warning_count: int

    # Compilation details
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Metadata
    source_path: Optional[Path] = None
    exit_code: Optional[int] = None
    command: Optional[str] = None

    # Error tracking
    error_message: Optional[str] = None

    def passed_gate(self) -> bool:
        """
        Check if compilation passed the gate.

        Gate: error_count == 0

        Returns:
            True if no compilation errors
        """
        return self.error_count == 0

    def to_dict(self) -> dict:
        """Convert result to dictionary for JSON serialization."""
        return {
            'success': self.success,
            'ex5_path': str(self.ex5_path) if self.ex5_path else None,
            'error_count': self.error_count,
            'warning_count': self.warning_count,
            'errors': self.errors,
            'warnings': self.warnings,
            'source_path': str(self.source_path) if self.source_path else None,
            'exit_code': self.exit_code,
            'command': self.command,
            'error_message': self.error_message,
            'gate_passed': self.passed_gate()
        }


def compile_ea(
    source_path: Path,
    installation: MT5Installation,
    timeout: int = 120
) -> CompileStepResult:
    """
    Compile EA source file using MetaEditor64.

    This is Step 2 of the workflow. It compiles the modified EA source
    (with injected OnTester and safety guards) and validates that
    compilation succeeded with no errors.

    Args:
        source_path: Path to modified EA source file (.mq5)
        installation: MT5Installation object
        timeout: Compilation timeout in seconds (default: 120)

    Returns:
        CompileStepResult with compilation details

    Gate:
        error_count == 0

    Failure Behavior:
        If compilation fails, workflow should pause with AWAITING_EA_FIX status.
        Maximum 3 fix attempts allowed. After fix, re-run Step 1B and Step 1C
        on fresh copy, then re-run Step 2.

    Example:
        >>> from ea_stress.mt5.terminal import MT5Discovery
        >>> from pathlib import Path
        >>>
        >>> # Discover MT5 installation
        >>> discovery = MT5Discovery()
        >>> installations = discovery.find_terminals()
        >>> installation = installations[0]
        >>>
        >>> # Compile EA
        >>> source = Path("C:/path/to/MyEA_ontester_safety.mq5")
        >>> result = compile_ea(source, installation)
        >>>
        >>> if result.passed_gate():
        ...     print(f"Compilation successful: {result.ex5_path}")
        ...     # Proceed to Step 3
        ... else:
        ...     print(f"Compilation failed with {result.error_count} errors")
        ...     for error in result.errors:
        ...         print(f"  {error}")
        ...     # Pause workflow with AWAITING_EA_FIX
    """
    # Validate inputs
    if not source_path.exists():
        return CompileStepResult(
            success=False,
            ex5_path=None,
            error_count=1,
            warning_count=0,
            errors=[f"Source file not found: {source_path}"],
            source_path=source_path,
            error_message=f"Source file not found: {source_path}"
        )

    if source_path.suffix.lower() not in ['.mq5', '.mq4']:
        return CompileStepResult(
            success=False,
            ex5_path=None,
            error_count=1,
            warning_count=0,
            errors=[f"Invalid source file extension: {source_path.suffix}"],
            source_path=source_path,
            error_message=f"Invalid source file extension: {source_path.suffix}"
        )

    try:
        # Create compiler
        compiler = MT5Compiler(installation)

        # Compile EA
        compilation_result: CompilationResult = compiler.compile(
            source_path=source_path,
            timeout=timeout
        )

        # Convert compilation errors to string list
        errors = [str(e) for e in compilation_result.errors]
        warnings = [str(w) for w in compilation_result.warnings]

        # Build result
        result = CompileStepResult(
            success=compilation_result.success,
            ex5_path=compilation_result.ex5_path,
            error_count=compilation_result.error_count,
            warning_count=compilation_result.warning_count,
            errors=errors,
            warnings=warnings,
            source_path=source_path,
            exit_code=compilation_result.exit_code,
            command=compilation_result.command,
            error_message=errors[0] if errors else None
        )

        return result

    except Exception as e:
        return CompileStepResult(
            success=False,
            ex5_path=None,
            error_count=1,
            warning_count=0,
            errors=[str(e)],
            source_path=source_path,
            error_message=str(e)
        )


def validate_compilation(source_path: Path, installation: MT5Installation) -> bool:
    """
    Quick validation that an EA can be compiled.

    Args:
        source_path: Path to EA source file
        installation: MT5Installation object

    Returns:
        True if compilation succeeds, False otherwise
    """
    result = compile_ea(source_path, installation)
    return result.passed_gate()
