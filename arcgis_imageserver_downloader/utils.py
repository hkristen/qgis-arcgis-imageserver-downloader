import subprocess
import sys

from qgis.core import QgsMessageLog, Qgis

PLUGIN_TAG = 'ArcGIS ImageServer Downloader'

def log(message, level=Qgis.Info):
    QgsMessageLog.logMessage(message, PLUGIN_TAG, level)

def subprocess_run_kwargs():
    kwargs = {'check': True, 'capture_output': True, 'text': True}
    if sys.platform == 'win32':
        kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
    return kwargs
