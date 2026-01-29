"""
Settings management using QgsSettings
"""
from typing import Any, Optional

from qgis.core import QgsSettings


class PluginSettings:
    """Wrapper for QgsSettings with plugin-specific paths."""

    PREFIX = 'arcgis_imageserver_downloader'

    def __init__(self):
        """Initialize settings."""
        self.settings = QgsSettings()

    def _key(self, key: str) -> str:
        """Generate full settings key with plugin prefix.

        Args:
            key: Setting key

        Returns:
            Full settings key
        """
        return f"{self.PREFIX}/{key}"

    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value.

        Args:
            key: Setting key
            default: Default value if not set

        Returns:
            Setting value or default
        """
        return self.settings.value(self._key(key), default)

    def set(self, key: str, value: Any):
        """Set a setting value.

        Args:
            key: Setting key
            value: Value to set
        """
        self.settings.setValue(self._key(key), value)

    def remove(self, key: str):
        """Remove a setting.

        Args:
            key: Setting key to remove
        """
        self.settings.remove(self._key(key))

    def contains(self, key: str) -> bool:
        """Check if a setting exists.

        Args:
            key: Setting key

        Returns:
            True if setting exists
        """
        return self.settings.contains(self._key(key))

    # Convenience methods for common settings

    def get_last_output_dir(self) -> Optional[str]:
        """Get last used output directory."""
        return self.get('last_output_dir')

    def set_last_output_dir(self, path: str):
        """Set last used output directory."""
        self.set('last_output_dir', path)

    def get_last_server_url(self) -> Optional[str]:
        """Get last used server URL."""
        return self.get('last_server_url')

    def set_last_server_url(self, url: str):
        """Set last used server URL."""
        self.set('last_server_url', url)

    def get_default_epsg(self) -> int:
        """Get default EPSG code."""
        return int(self.get('default_epsg', 32633))

    def set_default_epsg(self, epsg: int):
        """Set default EPSG code."""
        self.set('default_epsg', epsg)

    def get_output_format(self) -> int:
        """Get output format preference.

        Returns:
            0 = tiles only, 1 = uncompressed merge, 2 = compressed merge
        """
        return int(self.get('output_format', 2))

    def set_output_format(self, value: int):
        """Set output format preference."""
        self.set('output_format', value)

    def get_add_to_canvas(self) -> bool:
        """Get whether to add result to canvas by default."""
        return bool(self.get('add_to_canvas', True))

    def set_add_to_canvas(self, value: bool):
        """Set whether to add result to canvas by default."""
        self.set('add_to_canvas', value)

    def get_max_retry(self) -> int:
        """Get maximum retry attempts."""
        return int(self.get('max_retry', 5))

    def set_max_retry(self, value: int):
        """Set maximum retry attempts."""
        self.set('max_retry', value)
