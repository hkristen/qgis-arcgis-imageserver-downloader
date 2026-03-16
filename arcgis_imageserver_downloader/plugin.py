"""
Main plugin class for ArcGIS ImageServer Downloader
"""
import os
from pathlib import Path

from qgis.PyQt.QtCore import QCoreApplication, QTranslator, QSettings
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsApplication

from .processing.provider import ArcGISImageServerProvider


class ArcGISImageServerDownloaderPlugin:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        Args:
            iface: A QGIS interface instance.
        """
        self.iface = iface
        self.plugin_dir = Path(__file__).parent
        self.actions = []
        self.menu = self.tr('&ArcGIS ImageServer Downloader')
        self.toolbar = None
        self.dock_widget = None
        self.provider = None

        # Initialize translator
        self.translator = None
        locale = (QSettings().value('locale/userLocale', 'en') or 'en')[0:2]
        locale_path = self.plugin_dir / 'i18n' / f'arcgis_imageserver_downloader_{locale}.qm'

        if locale_path.exists():
            self.translator = QTranslator()
            self.translator.load(str(locale_path))
            QCoreApplication.installTranslator(self.translator)

    def tr(self, message):
        return QCoreApplication.translate('ArcGISImageServerDownloader', message)

    def initProcessing(self):
        self.provider = ArcGISImageServerProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def initGui(self):
        # Initialize processing provider
        self.initProcessing()

        # Create action to open dock widget
        icon_path = str(self.plugin_dir / 'icon.svg')
        self.add_action(
            icon_path,
            text=self.tr('ArcGIS ImageServer Downloader'),
            callback=self.run,
            parent=self.iface.mainWindow()
        )

    def unload(self):
        # Remove processing provider
        if self.provider is not None:
            QgsApplication.processingRegistry().removeProvider(self.provider)

        # Remove menu and toolbar
        for action in self.actions:
            self.iface.removePluginRasterMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)

        # Remove dock widget
        if self.dock_widget is not None:
            self.iface.removeDockWidget(self.dock_widget)
            self.dock_widget.deleteLater()
            self.dock_widget = None

        # Remove translator
        if self.translator is not None:
            QCoreApplication.removeTranslator(self.translator)

    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None
    ):
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)
        action.setCheckable(True)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToRasterMenu(self.menu, action)

        self.actions.append(action)
        return action

    def run(self):
        # Import here to avoid circular imports and load GUI only when needed
        from .gui.main_dialog import ArcGISImageServerDockWidget

        if self.dock_widget is None:
            self.dock_widget = ArcGISImageServerDockWidget(self.iface)
            self.iface.addDockWidget(self.dock_widget.location, self.dock_widget)
            self.dock_widget.visibilityChanged.connect(self.actions[0].setChecked)

        self.dock_widget.setVisible(not self.dock_widget.isVisible())
