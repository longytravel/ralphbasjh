"""MT5 Terminal Discovery and Management.

This module handles:
- Autodiscovery of MT5 terminal installations
- Terminal path validation
- Terminal version detection
"""

import os
import re
from pathlib import Path
from typing import List, Optional, Dict
from dataclasses import dataclass


@dataclass
class MT5Installation:
    """Represents a MetaTrader 5 installation."""
    terminal_path: Path
    data_path: Path
    version: Optional[str] = None

    def __post_init__(self):
        """Validate paths after initialization."""
        if not self.terminal_path.exists():
            raise ValueError(f"Terminal executable not found: {self.terminal_path}")
        if not self.data_path.exists():
            self.data_path.mkdir(parents=True, exist_ok=True)

    @property
    def metaeditor_path(self) -> Path:
        """Get path to MetaEditor64.exe."""
        metaeditor = self.terminal_path.parent / "metaeditor64.exe"
        if not metaeditor.exists():
            # Try 32-bit version as fallback
            metaeditor = self.terminal_path.parent / "metaeditor.exe"
        return metaeditor

    def __str__(self) -> str:
        version_str = f" (v{self.version})" if self.version else ""
        return f"MT5{version_str}: {self.terminal_path}"


class MT5Discovery:
    """Discovers and validates MetaTrader 5 installations."""

    # Common installation directories
    COMMON_PATHS = [
        Path("C:/Program Files/MetaTrader 5"),
        Path("C:/Program Files (x86)/MetaTrader 5"),
        Path(os.path.expandvars("%APPDATA%/MetaQuotes/Terminal")),
    ]

    # Broker-specific installation patterns
    BROKER_PATTERNS = [
        "C:/Program Files/*/MetaTrader 5",
        "C:/Program Files (x86)/*/MetaTrader 5",
    ]

    @staticmethod
    def find_terminals() -> List[MT5Installation]:
        """
        Autodiscover all MT5 terminal installations.

        Returns:
            List of MT5Installation objects found on the system.
        """
        installations = []
        seen_paths = set()

        # Search common installation paths
        for base_path in MT5Discovery.COMMON_PATHS:
            if base_path.exists():
                terminals = MT5Discovery._scan_directory(base_path)
                for terminal in terminals:
                    if terminal.terminal_path not in seen_paths:
                        installations.append(terminal)
                        seen_paths.add(terminal.terminal_path)

        # Search broker-specific patterns
        for pattern in MT5Discovery.BROKER_PATTERNS:
            import glob
            for path_str in glob.glob(pattern):
                path = Path(path_str)
                if path.exists():
                    terminals = MT5Discovery._scan_directory(path)
                    for terminal in terminals:
                        if terminal.terminal_path not in seen_paths:
                            installations.append(terminal)
                            seen_paths.add(terminal.terminal_path)

        # Sort by path for consistent ordering
        installations.sort(key=lambda x: str(x.terminal_path))

        return installations

    @staticmethod
    def _scan_directory(directory: Path) -> List[MT5Installation]:
        """
        Scan a directory for terminal64.exe.

        Args:
            directory: Directory to scan

        Returns:
            List of MT5Installation objects found in directory.
        """
        installations = []

        # Look for terminal64.exe in directory
        terminal_exe = directory / "terminal64.exe"
        if terminal_exe.exists():
            # Determine data path
            data_path = directory / "MQL5"
            if not data_path.exists():
                # Try common data location
                data_path = Path(os.path.expandvars("%APPDATA%/MetaQuotes/Terminal"))

            try:
                installation = MT5Installation(
                    terminal_path=terminal_exe,
                    data_path=data_path
                )
                # Try to detect version
                installation.version = MT5Discovery._detect_version(terminal_exe)
                installations.append(installation)
            except ValueError:
                pass  # Skip invalid installations

        # Also check subdirectories (one level deep)
        if directory.is_dir():
            for subdir in directory.iterdir():
                if subdir.is_dir():
                    terminal_exe = subdir / "terminal64.exe"
                    if terminal_exe.exists():
                        data_path = subdir / "MQL5"
                        if not data_path.exists():
                            data_path = Path(os.path.expandvars("%APPDATA%/MetaQuotes/Terminal"))

                        try:
                            installation = MT5Installation(
                                terminal_path=terminal_exe,
                                data_path=data_path
                            )
                            installation.version = MT5Discovery._detect_version(terminal_exe)
                            installations.append(installation)
                        except ValueError:
                            pass

        return installations

    @staticmethod
    def _detect_version(terminal_path: Path) -> Optional[str]:
        """
        Attempt to detect MT5 terminal version.

        Args:
            terminal_path: Path to terminal64.exe

        Returns:
            Version string if detected, None otherwise.
        """
        # Check for version.txt or similar files
        version_file = terminal_path.parent / "version.txt"
        if version_file.exists():
            try:
                content = version_file.read_text(encoding='utf-8', errors='ignore')
                match = re.search(r'\d+\.\d+', content)
                if match:
                    return match.group(0)
            except Exception:
                pass

        # Try to get version from file properties (Windows only)
        try:
            import win32api
            info = win32api.GetFileVersionInfo(str(terminal_path), '\\')
            ms = info['FileVersionMS']
            ls = info['FileVersionLS']
            version = f"{ms >> 16}.{ms & 0xFFFF}.{ls >> 16}.{ls & 0xFFFF}"
            return version
        except (ImportError, Exception):
            pass

        return None

    @staticmethod
    def validate_terminal(terminal_path: str) -> MT5Installation:
        """
        Validate a terminal path and return MT5Installation.

        Args:
            terminal_path: Path to terminal64.exe

        Returns:
            MT5Installation object

        Raises:
            ValueError: If terminal path is invalid
        """
        path = Path(terminal_path)

        if not path.exists():
            raise ValueError(f"Terminal executable not found: {terminal_path}")

        if not path.is_file():
            raise ValueError(f"Terminal path is not a file: {terminal_path}")

        if path.name.lower() not in ["terminal64.exe", "terminal.exe"]:
            raise ValueError(f"Invalid terminal executable name: {path.name}")

        # Determine data path
        data_path = path.parent / "MQL5"
        if not data_path.exists():
            data_path = Path(os.path.expandvars("%APPDATA%/MetaQuotes/Terminal"))

        installation = MT5Installation(
            terminal_path=path,
            data_path=data_path
        )
        installation.version = MT5Discovery._detect_version(path)

        return installation

    @staticmethod
    def resolve_terminal(explicit_path: Optional[str] = None,
                        env_var: str = "MT5_TERMINAL_PATH") -> MT5Installation:
        """
        Resolve MT5 terminal using priority order:
        1. Explicit path argument
        2. Environment variable
        3. Autodiscovery (must find exactly one)

        Args:
            explicit_path: Explicitly provided terminal path
            env_var: Environment variable name to check

        Returns:
            MT5Installation object

        Raises:
            ValueError: If no terminal found or multiple found without explicit choice
        """
        # Priority 1: Explicit path
        if explicit_path:
            return MT5Discovery.validate_terminal(explicit_path)

        # Priority 2: Environment variable
        env_path = os.environ.get(env_var)
        if env_path:
            return MT5Discovery.validate_terminal(env_path)

        # Priority 3: Autodiscovery
        installations = MT5Discovery.find_terminals()

        if len(installations) == 0:
            raise ValueError(
                "No MT5 terminal installations found. "
                f"Please provide explicit path or set {env_var} environment variable."
            )

        if len(installations) > 1:
            paths = "\n".join(f"  - {inst.terminal_path}" for inst in installations)
            raise ValueError(
                f"Multiple MT5 terminal installations found:\n{paths}\n"
                f"Please specify which one to use via explicit path or {env_var} environment variable."
            )

        return installations[0]


def get_terminal_info(installation: MT5Installation) -> Dict[str, str]:
    """
    Get detailed information about an MT5 installation.

    Args:
        installation: MT5Installation object

    Returns:
        Dictionary with terminal information
    """
    info = {
        "terminal_path": str(installation.terminal_path),
        "data_path": str(installation.data_path),
        "metaeditor_path": str(installation.metaeditor_path),
        "version": installation.version or "Unknown",
        "terminal_exists": installation.terminal_path.exists(),
        "metaeditor_exists": installation.metaeditor_path.exists(),
        "data_path_exists": installation.data_path.exists(),
    }
    return info
