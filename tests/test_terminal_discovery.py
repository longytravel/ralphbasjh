"""Tests for MT5 terminal discovery."""

import os
import tempfile
from pathlib import Path
import pytest

from ea_stress.mt5.terminal import (
    MT5Installation,
    MT5Discovery,
    get_terminal_info
)


class TestMT5Installation:
    """Test MT5Installation dataclass."""

    def test_installation_with_valid_paths(self, tmp_path):
        """Test creating installation with valid paths."""
        # Create mock terminal executable
        terminal_path = tmp_path / "terminal64.exe"
        terminal_path.touch()

        # Create data path
        data_path = tmp_path / "MQL5"
        data_path.mkdir()

        installation = MT5Installation(
            terminal_path=terminal_path,
            data_path=data_path
        )

        assert installation.terminal_path == terminal_path
        assert installation.data_path == data_path
        assert installation.version is None

    def test_installation_invalid_terminal_path(self, tmp_path):
        """Test that invalid terminal path raises error."""
        terminal_path = tmp_path / "nonexistent.exe"
        data_path = tmp_path / "MQL5"
        data_path.mkdir()

        with pytest.raises(ValueError, match="Terminal executable not found"):
            MT5Installation(
                terminal_path=terminal_path,
                data_path=data_path
            )

    def test_installation_creates_data_path(self, tmp_path):
        """Test that data path is created if missing."""
        terminal_path = tmp_path / "terminal64.exe"
        terminal_path.touch()

        data_path = tmp_path / "MQL5"

        installation = MT5Installation(
            terminal_path=terminal_path,
            data_path=data_path
        )

        assert installation.data_path.exists()

    def test_metaeditor_path_64bit(self, tmp_path):
        """Test MetaEditor path detection (64-bit)."""
        terminal_path = tmp_path / "terminal64.exe"
        terminal_path.touch()

        metaeditor_path = tmp_path / "metaeditor64.exe"
        metaeditor_path.touch()

        data_path = tmp_path / "MQL5"
        data_path.mkdir()

        installation = MT5Installation(
            terminal_path=terminal_path,
            data_path=data_path
        )

        assert installation.metaeditor_path == metaeditor_path

    def test_metaeditor_path_32bit_fallback(self, tmp_path):
        """Test MetaEditor path falls back to 32-bit."""
        terminal_path = tmp_path / "terminal64.exe"
        terminal_path.touch()

        # Only create 32-bit version
        metaeditor_path = tmp_path / "metaeditor.exe"
        metaeditor_path.touch()

        data_path = tmp_path / "MQL5"
        data_path.mkdir()

        installation = MT5Installation(
            terminal_path=terminal_path,
            data_path=data_path
        )

        assert installation.metaeditor_path == metaeditor_path

    def test_string_representation(self, tmp_path):
        """Test string representation."""
        terminal_path = tmp_path / "terminal64.exe"
        terminal_path.touch()
        data_path = tmp_path / "MQL5"
        data_path.mkdir()

        installation = MT5Installation(
            terminal_path=terminal_path,
            data_path=data_path,
            version="5.0.3770"
        )

        str_repr = str(installation)
        assert "MT5" in str_repr
        assert "5.0.3770" in str_repr
        assert str(terminal_path) in str_repr


class TestMT5Discovery:
    """Test MT5Discovery class."""

    def test_validate_terminal_valid_path(self, tmp_path):
        """Test validating a valid terminal path."""
        terminal_path = tmp_path / "terminal64.exe"
        terminal_path.touch()
        data_path = tmp_path / "MQL5"
        data_path.mkdir()

        installation = MT5Discovery.validate_terminal(str(terminal_path))

        assert installation.terminal_path == terminal_path

    def test_validate_terminal_nonexistent(self, tmp_path):
        """Test validating nonexistent path raises error."""
        terminal_path = tmp_path / "nonexistent.exe"

        with pytest.raises(ValueError, match="Terminal executable not found"):
            MT5Discovery.validate_terminal(str(terminal_path))

    def test_validate_terminal_not_file(self, tmp_path):
        """Test validating directory raises error."""
        with pytest.raises(ValueError, match="not a file"):
            MT5Discovery.validate_terminal(str(tmp_path))

    def test_validate_terminal_wrong_name(self, tmp_path):
        """Test validating wrong executable name raises error."""
        wrong_exe = tmp_path / "wrong.exe"
        wrong_exe.touch()

        with pytest.raises(ValueError, match="Invalid terminal executable name"):
            MT5Discovery.validate_terminal(str(wrong_exe))

    def test_scan_directory_finds_terminal(self, tmp_path):
        """Test scanning directory finds terminal."""
        terminal_path = tmp_path / "terminal64.exe"
        terminal_path.touch()
        data_path = tmp_path / "MQL5"
        data_path.mkdir()

        installations = MT5Discovery._scan_directory(tmp_path)

        assert len(installations) == 1
        assert installations[0].terminal_path == terminal_path

    def test_scan_directory_finds_in_subdirectory(self, tmp_path):
        """Test scanning finds terminal in subdirectory."""
        subdir = tmp_path / "MetaTrader 5"
        subdir.mkdir()

        terminal_path = subdir / "terminal64.exe"
        terminal_path.touch()
        data_path = subdir / "MQL5"
        data_path.mkdir()

        installations = MT5Discovery._scan_directory(tmp_path)

        assert len(installations) == 1
        assert installations[0].terminal_path == terminal_path

    def test_scan_directory_empty(self, tmp_path):
        """Test scanning empty directory returns empty list."""
        installations = MT5Discovery._scan_directory(tmp_path)
        assert len(installations) == 0

    def test_resolve_terminal_explicit_path(self, tmp_path):
        """Test resolve uses explicit path first."""
        terminal_path = tmp_path / "terminal64.exe"
        terminal_path.touch()
        (tmp_path / "MQL5").mkdir()

        installation = MT5Discovery.resolve_terminal(
            explicit_path=str(terminal_path)
        )

        assert installation.terminal_path == terminal_path

    def test_resolve_terminal_env_var(self, tmp_path, monkeypatch):
        """Test resolve uses environment variable."""
        terminal_path = tmp_path / "terminal64.exe"
        terminal_path.touch()
        (tmp_path / "MQL5").mkdir()

        monkeypatch.setenv("TEST_MT5_PATH", str(terminal_path))

        installation = MT5Discovery.resolve_terminal(
            env_var="TEST_MT5_PATH"
        )

        assert installation.terminal_path == terminal_path

    def test_resolve_terminal_no_installations_found(self):
        """Test resolve raises error when no terminals found."""
        with pytest.raises(ValueError, match="No MT5 terminal installations found"):
            # This will fail in real environments with MT5 installed
            # but should work in clean test environment
            MT5Discovery.resolve_terminal()

    def test_find_terminals_returns_list(self):
        """Test find_terminals returns a list."""
        installations = MT5Discovery.find_terminals()
        assert isinstance(installations, list)
        # May be empty or contain installations depending on system


class TestGetTerminalInfo:
    """Test get_terminal_info function."""

    def test_get_terminal_info(self, tmp_path):
        """Test getting terminal information."""
        terminal_path = tmp_path / "terminal64.exe"
        terminal_path.touch()

        metaeditor_path = tmp_path / "metaeditor64.exe"
        metaeditor_path.touch()

        data_path = tmp_path / "MQL5"
        data_path.mkdir()

        installation = MT5Installation(
            terminal_path=terminal_path,
            data_path=data_path,
            version="5.0.3770"
        )

        info = get_terminal_info(installation)

        assert info["terminal_path"] == str(terminal_path)
        assert info["data_path"] == str(data_path)
        assert info["metaeditor_path"] == str(metaeditor_path)
        assert info["version"] == "5.0.3770"
        assert info["terminal_exists"] is True
        assert info["metaeditor_exists"] is True
        assert info["data_path_exists"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
