"""
ArcGIS ImageServer Downloader Plugin
"""


def classFactory(iface):
    """Load ArcGISImageServerDownloaderPlugin class.

    Args:
        iface: A QGIS interface instance.
    """
    from .plugin import ArcGISImageServerDownloaderPlugin
    return ArcGISImageServerDownloaderPlugin(iface)
