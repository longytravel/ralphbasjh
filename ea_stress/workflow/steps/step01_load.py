"""
Step 1: Load EA

Purpose: Verify EA source file exists and is accessible.

Gate:
- file_exists == 1

Output:
- Validated file path
- File existence status
"""

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class LoadResult:
    """Result of EA load step."""
    file_exists: bool
    file_path: str
    absolute_path: str
    file_size: int
    is_mq5: bool
    is_mq4: bool
    error: Optional[str] = None

    def passed_gate(self) -> bool:
        """Check if the gate condition is met."""
        return self.file_exists

    def to_dict(self):
        """Convert to dictionary for JSON serialization."""
        return {
            'file_exists': self.file_exists,
            'file_path': self.file_path,
            'absolute_path': self.absolute_path,
            'file_size': self.file_size,
            'is_mq5': self.is_mq5,
            'is_mq4': self.is_mq4,
            'error': self.error,
            'gate_passed': self.passed_gate()
        }


def load_ea(ea_path: str) -> LoadResult:
    """
    Load and validate EA source file.

    Args:
        ea_path: Path to EA source file (.mq5 or .mq4)

    Returns:
        LoadResult with validation status

    Gate:
        file_exists == 1
    """
    # Convert to Path object for robust handling
    path = Path(ea_path)

    # Check if file exists
    if not path.exists():
        return LoadResult(
            file_exists=False,
            file_path=ea_path,
            absolute_path=str(path.absolute()),
            file_size=0,
            is_mq5=False,
            is_mq4=False,
            error=f"File does not exist: {ea_path}"
        )

    # Check if it's a file (not a directory)
    if not path.is_file():
        return LoadResult(
            file_exists=False,
            file_path=ea_path,
            absolute_path=str(path.absolute()),
            file_size=0,
            is_mq5=False,
            is_mq4=False,
            error=f"Path is not a file: {ea_path}"
        )

    # Get file size
    try:
        file_size = path.stat().st_size
    except OSError as e:
        return LoadResult(
            file_exists=False,
            file_path=ea_path,
            absolute_path=str(path.absolute()),
            file_size=0,
            is_mq5=False,
            is_mq4=False,
            error=f"Cannot access file: {e}"
        )

    # Check if file is readable
    try:
        with open(path, 'r', encoding='utf-8') as f:
            # Try reading first few bytes to verify readability
            f.read(10)
    except (OSError, UnicodeDecodeError) as e:
        return LoadResult(
            file_exists=False,
            file_path=ea_path,
            absolute_path=str(path.absolute()),
            file_size=file_size,
            is_mq5=False,
            is_mq4=False,
            error=f"File is not readable: {e}"
        )

    # Determine file type
    suffix = path.suffix.lower()
    is_mq5 = suffix == '.mq5'
    is_mq4 = suffix == '.mq4'

    # Validate file extension
    if not (is_mq5 or is_mq4):
        return LoadResult(
            file_exists=False,
            file_path=ea_path,
            absolute_path=str(path.absolute()),
            file_size=file_size,
            is_mq5=False,
            is_mq4=False,
            error=f"Invalid file extension: {suffix} (expected .mq5 or .mq4)"
        )

    # Success
    return LoadResult(
        file_exists=True,
        file_path=ea_path,
        absolute_path=str(path.absolute()),
        file_size=file_size,
        is_mq5=is_mq5,
        is_mq4=is_mq4,
        error=None
    )


def validate_ea_path(ea_path: str) -> tuple[bool, str]:
    """
    Quick validation helper for EA path.

    Args:
        ea_path: Path to EA source file

    Returns:
        Tuple of (is_valid, error_message)
    """
    result = load_ea(ea_path)
    return result.file_exists, result.error or ""
