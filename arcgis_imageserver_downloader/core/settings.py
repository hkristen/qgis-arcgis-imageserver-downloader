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

    def _key(self, key: str) -> str: return f"{self.PREFIX}/{key}"

    def get(self, key: str, default: Any = None) -> Any: return self.settings.value(self._key(key), default)

    def set(self, key: str, value: Any): self.settings.setValue(self._key(key), value)

    def remove(self, key: str): self.settings.remove(self._key(key))

    def contains(self, key: str) -> bool: return self.settings.contains(self._key(key))

    # Convenience methods for common settings

    def get_last_output_dir(self) -> Optional[str]: return self.get('last_output_dir')
    def set_last_output_dir(self, path: str): self.set('last_output_dir', path)

    def get_last_server_url(self) -> Optional[str]: return self.get('last_server_url')
    def set_last_server_url(self, url: str): self.set('last_server_url', url)

    def get_default_epsg(self) -> int: return self.settings.value(self._key('default_epsg'), 32633, type=int)
    def set_default_epsg(self, epsg: int): self.set('default_epsg', epsg)

    def get_output_format(self) -> int: return self.settings.value(self._key('output_format'), 2, type=int)
    def set_output_format(self, value: int): self.set('output_format', value)

    def get_compression(self) -> str: return self.settings.value(self._key('compression'), 'LZW')
    def set_compression(self, value: str): self.set('compression', value)

    def get_add_to_canvas(self) -> bool: return self.settings.value(self._key('add_to_canvas'), True, type=bool)
    def set_add_to_canvas(self, value: bool): self.set('add_to_canvas', value)

    def get_max_retry(self) -> int: return self.settings.value(self._key('max_retry'), 5, type=int)
    def set_max_retry(self, value: int): self.set('max_retry', value)
