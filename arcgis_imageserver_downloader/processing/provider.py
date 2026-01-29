"""
Processing provider for ArcGIS ImageServer algorithms
"""
from pathlib import Path

from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtGui import QIcon

from .algorithms.discover_services import DiscoverServicesAlgorithm
from .algorithms.download_tiles import DownloadTilesAlgorithm
from .algorithms.create_cog import CreateCOGAlgorithm


class ArcGISImageServerProvider(QgsProcessingProvider):
    """Processing provider for ArcGIS ImageServer operations."""

    def __init__(self):
        """Initialize provider."""
        super().__init__()

    def tr(self, string):
        """Get translation for a string."""
        return QCoreApplication.translate(self.__class__.__name__, string)

    def id(self):
        """Return provider ID."""
        return 'arcgis_imageserver'

    def name(self):
        """Return provider name."""
        return self.tr('ArcGIS ImageServer')

    def icon(self):
        """Return provider icon."""
        icon_path = Path(__file__).parent.parent / 'icon.svg'
        return QIcon(str(icon_path))

    def longName(self):
        """Return provider long name."""
        return self.tr('ArcGIS ImageServer Downloader')

    def loadAlgorithms(self):
        """Load all algorithms."""
        self.addAlgorithm(DiscoverServicesAlgorithm())
        self.addAlgorithm(DownloadTilesAlgorithm())
        self.addAlgorithm(CreateCOGAlgorithm())
