"""
Service preset management
"""
import json
from pathlib import Path
from typing import Dict, List, Optional

from qgis.core import Qgis

from ..utils import log


class ServicePreset:
    """Represents a pre-configured ArcGIS ImageServer endpoint."""

    def __init__(
        self,
        name: str,
        url: str,
        default_epsg: int = 32633,
        description: str = ""
    ):
        """Initialize service preset.

        Args:
            name: Display name for the preset
            url: Base URL of the ArcGIS REST endpoint
            default_epsg: Default EPSG code for output
            description: Optional description
        """
        self.name = name
        self.url = url
        self.default_epsg = default_epsg
        self.description = description

    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            'name': self.name,
            'url': self.url,
            'default_epsg': self.default_epsg,
            'description': self.description
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'ServicePreset':
        """Create preset from dictionary."""
        return cls(
            name=data['name'],
            url=data['url'],
            default_epsg=data.get('default_epsg', 32633),
            description=data.get('description', '')
        )


class ServiceManager:
    """Manages service presets and custom servers."""

    def __init__(self, plugin_dir: Optional[Path] = None):
        """Initialize service manager.

        Args:
            plugin_dir: Path to plugin directory (for loading built-in presets)
        """
        self.plugin_dir = plugin_dir
        self._presets: Dict[str, ServicePreset] = {}
        self._custom_servers: List[ServicePreset] = []

        # Load built-in presets
        if plugin_dir:
            self._load_builtin_presets()

    def _load_builtin_presets(self):
        if not self.plugin_dir:
            return

        presets_dir = self.plugin_dir / 'presets'
        if not presets_dir.exists():
            return

        for preset_file in presets_dir.glob('*.json'):
            try:
                with open(preset_file, 'r') as f:
                    data = json.load(f)

                # Support both single preset and list of presets
                if isinstance(data, list):
                    for preset_data in data:
                        preset = ServicePreset.from_dict(preset_data)
                        self._presets[preset.name] = preset
                else:
                    preset = ServicePreset.from_dict(data)
                    self._presets[preset.name] = preset

                log(f"Loaded preset from {preset_file.name}")

            except Exception as e:
                log(f"Failed to load preset from {preset_file}: {e}", Qgis.Warning)

    def get_preset(self, name: str) -> Optional[ServicePreset]:
        """Get preset by name.

        Args:
            name: Preset name

        Returns:
            ServicePreset or None if not found
        """
        return self._presets.get(name)

    def get_all_presets(self) -> List[ServicePreset]:
        """Get all available presets.

        Returns:
            List of ServicePreset objects
        """
        return list(self._presets.values())

    def add_custom_server(self, preset: ServicePreset):
        """Add a custom server configuration.

        Args:
            preset: ServicePreset to add
        """
        # Check if already exists
        for existing in self._custom_servers:
            if existing.url == preset.url:
                # Update existing
                existing.name = preset.name
                existing.default_epsg = preset.default_epsg
                existing.description = preset.description
                return

        self._custom_servers.append(preset)

    def remove_custom_server(self, url: str) -> bool:
        """Remove a custom server by URL.

        Args:
            url: Server URL to remove

        Returns:
            True if removed, False if not found
        """
        for i, preset in enumerate(self._custom_servers):
            if preset.url == url:
                self._custom_servers.pop(i)
                return True
        return False

    def get_custom_servers(self) -> List[ServicePreset]:
        """Get all custom servers.

        Returns:
            List of custom ServicePreset objects
        """
        return self._custom_servers

    def get_all_servers(self) -> List[ServicePreset]:
        """Get all servers (presets + custom).

        Returns:
            List of all ServicePreset objects
        """
        return self.get_all_presets() + self.get_custom_servers()

    def save_custom_servers(self, filepath: Path):
        """Save custom servers to JSON file.

        Args:
            filepath: Path to save JSON file
        """
        data = [preset.to_dict() for preset in self._custom_servers]
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)

    def load_custom_servers(self, filepath: Path):
        """Load custom servers from JSON file.

        Args:
            filepath: Path to JSON file
        """
        if not filepath.exists():
            return

        try:
            with open(filepath, 'r') as f:
                data = json.load(f)

            self._custom_servers = [ServicePreset.from_dict(item) for item in data]
            log(f"Loaded {len(self._custom_servers)} custom servers")

        except Exception as e:
            log(f"Failed to load custom servers: {e}", Qgis.Warning)
