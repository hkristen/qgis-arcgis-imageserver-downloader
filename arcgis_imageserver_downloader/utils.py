from qgis.core import QgsMessageLog, Qgis

PLUGIN_TAG = 'ArcGIS ImageServer Downloader'

def log(message, level=Qgis.Info):
    QgsMessageLog.logMessage(message, PLUGIN_TAG, level)
