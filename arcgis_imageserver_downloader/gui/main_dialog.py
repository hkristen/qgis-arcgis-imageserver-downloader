"""
Main dock widget for ArcGIS ImageServer Downloader
"""
import os
from pathlib import Path
from typing import Optional, Tuple

from qgis.PyQt.QtCore import Qt, QCoreApplication, QUrl
from qgis.PyQt.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
    QLineEdit,
    QFileDialog,
    QRadioButton,
    QButtonGroup,
    QCheckBox,
    QProgressBar,
    QMessageBox,
    QGroupBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout
)
from qgis.gui import QgsDockWidget, QgsProjectionSelectionWidget
from qgis.core import (
    QgsProject,
    QgsRasterLayer,
    QgsRectangle,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsApplication,
    QgsMessageLog,
    Qgis
)

from ..core.service_manager import ServiceManager, ServicePreset
from ..core.settings import PluginSettings
from ..tasks.download_task import TileDownloadTask
from ..tasks.processing_task import COGProcessingTask
from .service_browser import ServiceBrowserWidget
from .bbox_tool import BBoxMapTool


class ServerDialog(QDialog):
    """Dialog for adding or editing server configurations."""

    def __init__(self, parent=None, title='Server Configuration', name='', url=''):
        """Initialize the server dialog.

        Args:
            parent: Parent widget
            title: Dialog title
            name: Initial server name
            url: Initial server URL
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(400)

        # Create form layout
        layout = QFormLayout()

        # Server name field
        self.name_edit = QLineEdit()
        self.name_edit.setText(name)
        self.name_edit.setPlaceholderText(self.tr('e.g., My Custom Server'))
        layout.addRow(self.tr('Server Name:'), self.name_edit)

        # Server URL field
        self.url_edit = QLineEdit()
        self.url_edit.setText(url)
        self.url_edit.setPlaceholderText(self.tr('e.g., https://example.com/arcgis/rest/services'))
        layout.addRow(self.tr('Server URL:'), self.url_edit)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

        self.setLayout(layout)

    def tr(self, message):
        """Get the translation for a string using the global QGIS locale.

        Args:
            message: String to be translated

        Returns:
            Translated string
        """
        return QCoreApplication.translate('ArcGISImageServerDownloader', message)

    def get_values(self):
        """Get the entered values.

        Returns:
            Tuple of (name, url) or (None, None) if invalid
        """
        name = self.name_edit.text().strip()
        url = self.url_edit.text().strip()

        if not (name and url):
            return None, None

        parsed = QUrl(url)
        if not parsed.isValid() or parsed.scheme() not in ('http', 'https'):
            return None, None

        return name, url


class ArcGISImageServerDockWidget(QgsDockWidget):
    """Dockable widget for ArcGIS ImageServer Downloader."""

    location = Qt.RightDockWidgetArea

    def __init__(self, iface):
        """Initialize the dock widget.

        Args:
            iface: QGIS interface
        """
        super().__init__('ArcGIS ImageServer Downloader')

        self.iface = iface
        self.canvas = iface.mapCanvas()

        # Initialize managers
        plugin_dir = Path(__file__).parent.parent
        self.service_manager = ServiceManager(plugin_dir)
        self.settings = PluginSettings()

        # Load custom servers
        custom_servers_path = Path(QgsApplication.qgisSettingsDirPath()) / 'arcgis_imageserver_custom_servers.json'
        if custom_servers_path.exists():
            self.service_manager.load_custom_servers(custom_servers_path)

        # State
        self.current_preset = None
        self.selected_service = None
        self.bbox = None
        self.bbox_tool = None
        self.download_task = None
        self.processing_task = None
        self.service_output_dir = None  # Track where tiles were saved

        # Create UI
        self._init_ui()
        self._load_settings()

    def tr(self, message):
        """Get the translation for a string using the global QGIS locale.

        Args:
            message: String to be translated

        Returns:
            Translated string
        """
        return QCoreApplication.translate('ArcGISImageServerDownloader', message)

    def _log(self, message: str, level: Qgis.MessageLevel = Qgis.Info):
        """Log message to QGIS message log."""
        QgsMessageLog.logMessage(message, 'ArcGIS ImageServer Downloader', level)

    def _init_ui(self):
        """Initialize the user interface."""
        # Main widget
        main_widget = QWidget()
        layout = QVBoxLayout()

        # Server selection section
        server_group = QGroupBox(self.tr('Server'))
        server_layout = QVBoxLayout()

        server_select_layout = QHBoxLayout()
        server_select_layout.addWidget(QLabel(self.tr('Server:')))
        self.server_combo = QComboBox()
        self.server_combo.currentIndexChanged.connect(self._on_server_changed)
        server_select_layout.addWidget(self.server_combo, 1)

        self.add_server_btn = QPushButton('+')
        self.add_server_btn.setMaximumWidth(30)
        self.add_server_btn.setToolTip(self.tr('Add custom server'))
        self.add_server_btn.clicked.connect(self._add_custom_server)
        server_select_layout.addWidget(self.add_server_btn)

        self.edit_server_btn = QPushButton(self.tr('Edit'))
        self.edit_server_btn.setToolTip(self.tr('Edit or copy server settings'))
        self.edit_server_btn.clicked.connect(self._edit_server)
        self.edit_server_btn.setEnabled(False)
        server_select_layout.addWidget(self.edit_server_btn)

        server_layout.addLayout(server_select_layout)
        server_group.setLayout(server_layout)
        layout.addWidget(server_group)

        # Service browser section
        services_group = QGroupBox(self.tr('Services'))
        services_layout = QVBoxLayout()

        self.service_browser = ServiceBrowserWidget()
        self.service_browser.serviceSelected.connect(self._on_service_selected)
        services_layout.addWidget(self.service_browser)

        services_group.setLayout(services_layout)
        layout.addWidget(services_group)

        # Bounding box section
        bbox_group = QGroupBox(self.tr('Bounding Box'))
        bbox_layout = QVBoxLayout()

        # Radio buttons for bbox selection method
        self.bbox_button_group = QButtonGroup()

        self.bbox_draw_radio = QRadioButton(self.tr('Draw on canvas'))
        self.bbox_button_group.addButton(self.bbox_draw_radio)
        bbox_layout.addWidget(self.bbox_draw_radio)

        self.bbox_layer_radio = QRadioButton(self.tr('From active layer extent'))
        self.bbox_button_group.addButton(self.bbox_layer_radio)
        bbox_layout.addWidget(self.bbox_layer_radio)

        self.bbox_manual_radio = QRadioButton(self.tr('Manual coordinates'))
        self.bbox_button_group.addButton(self.bbox_manual_radio)
        bbox_layout.addWidget(self.bbox_manual_radio)

        # Connect toggled signals after setChecked to avoid stealing map tool on init
        self.bbox_draw_radio.setChecked(True)
        self.bbox_draw_radio.toggled.connect(self._on_bbox_method_changed)
        self.bbox_layer_radio.toggled.connect(self._on_bbox_method_changed)
        self.bbox_manual_radio.toggled.connect(self._on_bbox_method_changed)

        # Manual bbox input (initially hidden)
        self.bbox_manual_widget = QWidget()
        bbox_manual_layout = QVBoxLayout()
        bbox_manual_layout.setContentsMargins(20, 0, 0, 0)

        bbox_coords_layout = QHBoxLayout()
        bbox_coords_layout.addWidget(QLabel(self.tr('Min X:')))
        self.bbox_minx = QLineEdit()
        bbox_coords_layout.addWidget(self.bbox_minx)
        bbox_coords_layout.addWidget(QLabel(self.tr('Min Y:')))
        self.bbox_miny = QLineEdit()
        bbox_coords_layout.addWidget(self.bbox_miny)
        bbox_manual_layout.addLayout(bbox_coords_layout)

        bbox_coords_layout2 = QHBoxLayout()
        bbox_coords_layout2.addWidget(QLabel(self.tr('Max X:')))
        self.bbox_maxx = QLineEdit()
        bbox_coords_layout2.addWidget(self.bbox_maxx)
        bbox_coords_layout2.addWidget(QLabel(self.tr('Max Y:')))
        self.bbox_maxy = QLineEdit()
        bbox_coords_layout2.addWidget(self.bbox_maxy)
        bbox_manual_layout.addLayout(bbox_coords_layout2)

        self.bbox_manual_widget.setLayout(bbox_manual_layout)
        self.bbox_manual_widget.setVisible(False)
        bbox_layout.addWidget(self.bbox_manual_widget)

        # Current bbox display
        self.bbox_label = QLabel(self.tr('No bounding box selected'))
        self.bbox_label.setStyleSheet('color: gray; font-style: italic;')
        bbox_layout.addWidget(self.bbox_label)

        bbox_group.setLayout(bbox_layout)
        layout.addWidget(bbox_group)

        # Output settings section
        output_group = QGroupBox(self.tr('Output Settings'))
        output_layout = QVBoxLayout()

        # CRS selection
        crs_layout = QHBoxLayout()
        crs_layout.addWidget(QLabel(self.tr('Output CRS:')))
        self.crs_selector = QgsProjectionSelectionWidget()
        self.crs_selector.setCrs(QgsCoordinateReferenceSystem('EPSG:32633'))
        crs_layout.addWidget(self.crs_selector, 1)
        output_layout.addLayout(crs_layout)

        # Output format options
        output_layout.addWidget(QLabel(self.tr('Output Format:')))

        self.output_format_group = QButtonGroup()

        self.tiles_only_radio = QRadioButton(self.tr('Tiles only (no merge)'))
        self.tiles_only_radio.setToolTip(self.tr('Download individual tiles without merging'))
        self.output_format_group.addButton(self.tiles_only_radio, 0)
        output_layout.addWidget(self.tiles_only_radio)

        self.merge_uncompressed_radio = QRadioButton(self.tr('Merge uncompressed (fast, large file)'))
        self.merge_uncompressed_radio.setToolTip(self.tr('Merge tiles into single GeoTIFF without compression - fastest but largest file'))
        self.output_format_group.addButton(self.merge_uncompressed_radio, 1)
        output_layout.addWidget(self.merge_uncompressed_radio)

        self.merge_compressed_radio = QRadioButton(self.tr('Merge compressed (recommended)'))
        self.merge_compressed_radio.setToolTip(self.tr('Merge tiles with LZW compression, tiling, and overviews - best balance of speed, size, and performance'))
        self.merge_compressed_radio.setChecked(True)
        self.output_format_group.addButton(self.merge_compressed_radio, 2)
        output_layout.addWidget(self.merge_compressed_radio)

        # Additional options
        self.add_to_canvas_checkbox = QCheckBox(self.tr('Add to canvas'))
        self.add_to_canvas_checkbox.setChecked(True)
        output_layout.addWidget(self.add_to_canvas_checkbox)

        # Output path
        output_path_layout = QHBoxLayout()
        output_path_layout.addWidget(QLabel(self.tr('Output:')))
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText(self.tr('Select output directory...'))
        output_path_layout.addWidget(self.output_path_edit, 1)

        self.browse_btn = QPushButton('...')
        self.browse_btn.setMaximumWidth(30)
        self.browse_btn.clicked.connect(self._browse_output_dir)
        output_path_layout.addWidget(self.browse_btn)

        output_layout.addLayout(output_path_layout)

        output_group.setLayout(output_layout)
        layout.addWidget(output_group)

        # Progress section
        progress_group = QGroupBox(self.tr('Progress'))
        progress_layout = QVBoxLayout()

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)

        self.status_label = QLabel(self.tr('Ready'))
        self.status_label.setStyleSheet('color: gray; font-style: italic;')
        progress_layout.addWidget(self.status_label)

        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)

        # Action buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.download_btn = QPushButton(self.tr('Download'))
        self.download_btn.clicked.connect(self._start_download)
        button_layout.addWidget(self.download_btn)

        self.cancel_btn = QPushButton(self.tr('Cancel'))
        self.cancel_btn.clicked.connect(self._cancel_download)
        self.cancel_btn.setEnabled(False)
        button_layout.addWidget(self.cancel_btn)

        layout.addLayout(button_layout)

        # Add stretch to push everything to top
        layout.addStretch()

        main_widget.setLayout(layout)
        self.setWidget(main_widget)

        # Populate server combo
        self._populate_server_combo()

    def _populate_server_combo(self):
        """Populate server combo box with presets and custom servers."""
        self.server_combo.clear()
        self.server_combo.addItem(self.tr('-- Select a server --'), None)

        # Add presets
        for preset in self.service_manager.get_all_presets():
            self.server_combo.addItem(preset.name, preset)

        # Add separator
        if self.service_manager.get_custom_servers():
            self.server_combo.insertSeparator(self.server_combo.count())

            # Add custom servers
            for preset in self.service_manager.get_custom_servers():
                self.server_combo.addItem(self.tr('{name} (Custom)').format(name=preset.name), preset)

    def _load_settings(self):
        """Load saved settings."""
        # Load last output directory
        last_output_dir = self.settings.get_last_output_dir()
        if last_output_dir:
            self.output_path_edit.setText(last_output_dir)

        # Load last server
        last_server_url = self.settings.get_last_server_url()
        if last_server_url:
            for i in range(self.server_combo.count()):
                preset = self.server_combo.itemData(i)
                if preset and preset.url == last_server_url:
                    self.server_combo.setCurrentIndex(i)
                    break

        # Load default EPSG
        default_epsg = self.settings.get_default_epsg()
        self.crs_selector.setCrs(QgsCoordinateReferenceSystem(f'EPSG:{default_epsg}'))

        # Load output format
        output_format = self.settings.get_output_format()
        if output_format == 0:
            self.tiles_only_radio.setChecked(True)
        elif output_format == 1:
            self.merge_uncompressed_radio.setChecked(True)
        else:
            # Default to compressed (format 2 or anything else)
            self.merge_compressed_radio.setChecked(True)

        # Load checkbox states
        self.add_to_canvas_checkbox.setChecked(self.settings.get_add_to_canvas())

    def _save_settings(self):
        """Save current settings."""
        # Save output directory
        output_dir = self.output_path_edit.text()
        if output_dir:
            self.settings.set_last_output_dir(output_dir)

        # Save current server
        if self.current_preset:
            self.settings.set_last_server_url(self.current_preset.url)

        # Save EPSG
        crs = self.crs_selector.crs()
        if crs.isValid():
            epsg = crs.postgisSrid()
            self.settings.set_default_epsg(epsg)

        # Save output format
        self.settings.set_output_format(self.output_format_group.checkedId())

        # Save checkbox states
        self.settings.set_add_to_canvas(self.add_to_canvas_checkbox.isChecked())

    def _on_server_changed(self, index: int):
        """Handle server selection change.

        Args:
            index: Combo box index
        """
        preset = self.server_combo.itemData(index)
        if preset:
            self.current_preset = preset
            self._log(f'Selected server: {preset.name}')

            # Update CRS if different
            if preset.default_epsg:
                self.crs_selector.setCrs(
                    QgsCoordinateReferenceSystem(f'EPSG:{preset.default_epsg}')
                )

            # Enable edit button for any valid server selection
            self.edit_server_btn.setEnabled(True)

            # Load services
            self.service_browser.load_services(preset.url)
        else:
            self.current_preset = None
            self.edit_server_btn.setEnabled(False)
            self.service_browser.clear()

    def _on_service_selected(self, service: dict):
        """Handle service selection.

        Args:
            service: Service information dictionary
        """
        self.selected_service = service
        self._log(f'Selected service: {service.get("name", "Unknown")}')

    def _on_bbox_method_changed(self, checked: bool):
        """Handle bbox selection method change.

        Args:
            checked: True if the radio button is now checked
        """
        # Only act on the checked signal, not the unchecked signal
        if not checked:
            return

        # Show/hide manual coordinates widget
        self.bbox_manual_widget.setVisible(self.bbox_manual_radio.isChecked())

        # Activate/deactivate draw tool
        if self.bbox_draw_radio.isChecked():
            self._activate_bbox_tool()
        else:
            self._deactivate_bbox_tool()

        # Update bbox from active layer if selected
        if self.bbox_layer_radio.isChecked():
            self._update_bbox_from_layer()

    def _activate_bbox_tool(self):
        """Activate bbox drawing tool."""
        if not self.bbox_tool:
            self.bbox_tool = BBoxMapTool(self.canvas)
            self.bbox_tool.bboxDrawn.connect(self._on_bbox_drawn)

        self.canvas.setMapTool(self.bbox_tool)
        self._log('Bbox drawing tool activated - draw a rectangle on the map')

    def _deactivate_bbox_tool(self):
        """Deactivate bbox drawing tool."""
        if self.bbox_tool:
            if self.canvas.mapTool() == self.bbox_tool:
                self.canvas.unsetMapTool(self.bbox_tool)
            self.bbox_tool.cleanup()
            self.bbox_tool = None

    def _on_bbox_drawn(self, rect: QgsRectangle):
        """Handle bbox drawn on canvas.

        Args:
            rect: Drawn rectangle
        """
        # Transform to output CRS if needed
        canvas_crs = self.canvas.mapSettings().destinationCrs()
        output_crs = self.crs_selector.crs()

        if canvas_crs != output_crs:
            transform = QgsCoordinateTransform(
                canvas_crs,
                output_crs,
                QgsProject.instance()
            )
            rect = transform.transformBoundingBox(rect)

        self.bbox = rect
        self._update_bbox_label()
        self._log(f'Bbox selected: {rect.asWktPolygon()}')

    def _update_bbox_from_layer(self):
        """Update bbox from active layer extent."""
        layer = self.iface.activeLayer()
        if not layer:
            QMessageBox.warning(
                self,
                self.tr('No Active Layer'),
                self.tr('Please select a layer to use its extent as bounding box.')
            )
            return

        # Get layer extent
        extent = layer.extent()

        # Transform to output CRS if needed
        layer_crs = layer.crs()
        output_crs = self.crs_selector.crs()

        if layer_crs != output_crs:
            transform = QgsCoordinateTransform(
                layer_crs,
                output_crs,
                QgsProject.instance()
            )
            extent = transform.transformBoundingBox(extent)

        self.bbox = extent
        self._update_bbox_label()
        self._log(f'Bbox from layer: {extent.asWktPolygon()}')

    def _update_bbox_label(self):
        """Update bbox display label."""
        if self.bbox:
            self.bbox_label.setText(
                self.tr('Bbox: ({minx:.2f}, {miny:.2f}) - ({maxx:.2f}, {maxy:.2f})').format(
                    minx=self.bbox.xMinimum(),
                    miny=self.bbox.yMinimum(),
                    maxx=self.bbox.xMaximum(),
                    maxy=self.bbox.yMaximum()
                )
            )
        else:
            self.bbox_label.setText(self.tr('No bounding box selected'))

    def _get_bbox(self) -> Optional[Tuple[float, float, float, float]]:
        """Get current bounding box.

        Returns:
            Tuple (minx, miny, maxx, maxy) or None
        """
        if self.bbox_manual_radio.isChecked():
            # Get manual coordinates
            try:
                minx = float(self.bbox_minx.text())
                miny = float(self.bbox_miny.text())
                maxx = float(self.bbox_maxx.text())
                maxy = float(self.bbox_maxy.text())
                return (minx, miny, maxx, maxy)
            except ValueError:
                return None

        elif self.bbox:
            return (
                self.bbox.xMinimum(),
                self.bbox.yMinimum(),
                self.bbox.xMaximum(),
                self.bbox.yMaximum()
            )

        return None

    def _browse_output_dir(self):
        """Browse for output directory."""
        current_dir = self.output_path_edit.text() or os.path.expanduser('~')
        output_dir = QFileDialog.getExistingDirectory(
            self,
            self.tr('Select Output Directory'),
            current_dir
        )

        if output_dir:
            self.output_path_edit.setText(output_dir)

    def _add_custom_server(self):
        """Add custom server."""
        dialog = ServerDialog(
            parent=self,
            title=self.tr('Add Custom Server'),
            name='',
            url=''
        )

        if dialog.exec() == QDialog.Accepted:
            name, url = dialog.get_values()

            if name and url:
                preset = ServicePreset(
                    name=name,
                    url=url,
                    default_epsg=self.crs_selector.crs().postgisSrid()
                )

                self.service_manager.add_custom_server(preset)

                # Save custom servers
                custom_servers_path = Path(QgsApplication.qgisSettingsDirPath()) / 'arcgis_imageserver_custom_servers.json'
                self.service_manager.save_custom_servers(custom_servers_path)

                # Refresh combo
                self._populate_server_combo()

                # Select new server
                for i in range(self.server_combo.count()):
                    if self.server_combo.itemData(i) == preset:
                        self.server_combo.setCurrentIndex(i)
                        break
            else:
                QMessageBox.warning(
                    self,
                    self.tr('Invalid Input'),
                    self.tr('Both server name and URL are required.')
                )

    def _edit_server(self):
        """Edit or copy the currently selected server."""
        if not self.current_preset:
            return

        # Check if it's a built-in or custom server
        is_custom = self.current_preset in self.service_manager.get_custom_servers()

        if is_custom:
            dialog_title = self.tr('Edit Custom Server')
            initial_name = self.current_preset.name
        else:
            dialog_title = self.tr('Copy Server Settings')
            initial_name = self.tr('{name} (Copy)').format(name=self.current_preset.name)

        dialog = ServerDialog(
            parent=self,
            title=dialog_title,
            name=initial_name,
            url=self.current_preset.url
        )

        if dialog.exec() == QDialog.Accepted:
            name, url = dialog.get_values()

            if name and url:
                if is_custom:
                    # Update existing custom server
                    self.current_preset.name = name
                    self.current_preset.url = url
                    self.current_preset.default_epsg = self.crs_selector.crs().postgisSrid()
                else:
                    # Create new custom server based on built-in preset
                    new_preset = ServicePreset(
                        name=name,
                        url=url,
                        default_epsg=self.crs_selector.crs().postgisSrid(),
                        description=self.tr('Copy of {name}').format(name=self.current_preset.name)
                    )
                    self.service_manager.add_custom_server(new_preset)
                    self.current_preset = new_preset

                # Save custom servers
                custom_servers_path = Path(QgsApplication.qgisSettingsDirPath()) / 'arcgis_imageserver_custom_servers.json'
                self.service_manager.save_custom_servers(custom_servers_path)

                # Refresh combo
                self._populate_server_combo()

                # Select the edited/new server
                for i in range(self.server_combo.count()):
                    preset = self.server_combo.itemData(i)
                    if preset and preset.url == url and preset.name == name:
                        self.server_combo.setCurrentIndex(i)
                        break
            else:
                QMessageBox.warning(
                    self,
                    self.tr('Invalid Input'),
                    self.tr('Both server name and URL are required.')
                )

    def _validate_inputs(self) -> bool:
        """Validate user inputs before starting download.

        Returns:
            True if valid
        """
        # Check server
        if not self.current_preset:
            QMessageBox.warning(self, self.tr('Validation Error'), self.tr('Please select a server.'))
            return False

        # Check service
        selected_service = self.service_browser.get_selected_service()
        if not selected_service:
            QMessageBox.warning(self, self.tr('Validation Error'), self.tr('Please select a service.'))
            return False
        if not selected_service.get('base_url'):
            QMessageBox.warning(self, self.tr('Validation Error'), self.tr('Selected service has no server URL. Please re-select a server.'))
            return False

        # Check bbox
        bbox = self._get_bbox()
        if not bbox:
            QMessageBox.warning(
                self,
                self.tr('Validation Error'),
                self.tr('Please select a bounding box.')
            )
            return False

        # Check output path
        output_path = self.output_path_edit.text()
        if not output_path:
            QMessageBox.warning(
                self,
                self.tr('Validation Error'),
                self.tr('Please select an output directory.')
            )
            return False

        return True

    def _start_download(self):
        """Start the download process."""
        if not self._validate_inputs():
            return

        # Save settings
        self._save_settings()

        # Get parameters
        selected_service = self.service_browser.get_selected_service()
        service_url = selected_service['base_url']
        service_name = selected_service['name']
        bbox = self._get_bbox()
        output_dir = Path(self.output_path_edit.text())
        epsg = self.crs_selector.crs().postgisSrid()

        # Create service-specific output directory
        service_output_dir = output_dir / service_name.replace('/', '_')
        self.service_output_dir = service_output_dir  # Store for COG creation

        # Update UI
        self.download_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.status_label.setText(self.tr('Starting download...'))

        # Create download task
        self.download_task = TileDownloadTask(
            service_url=service_url,
            service_name=service_name,
            output_dir=service_output_dir,
            bbox=bbox,
            epsg=epsg,
            max_retry=self.settings.get_max_retry()
        )

        # Connect signals
        self.download_task.progressChanged.connect(self._on_download_progress)
        self.download_task.downloadComplete.connect(self._on_download_complete)
        self.download_task.downloadFailed.connect(self._on_download_failed)
        self.download_task.taskCompleted.connect(lambda: setattr(self, 'download_task', None))
        self.download_task.taskTerminated.connect(lambda: setattr(self, 'download_task', None))

        # Add to task manager
        QgsApplication.taskManager().addTask(self.download_task)

        self._log(f'Starting download for service: {service_name}')

    def _cancel_download(self):
        """Cancel the current download."""
        if self.download_task:
            try:
                self.download_task.cancel()
            except RuntimeError:
                pass

        if self.processing_task:
            try:
                self.processing_task.cancel()
            except RuntimeError:
                pass

    def _on_download_progress(self, progress: float):
        """Handle download progress update.

        Args:
            progress: Progress percentage (0-100)
        """
        self.progress_bar.setValue(int(progress))
        self.status_label.setText(self.tr('Downloading tiles... {progress}%').format(progress=int(progress)))

    def _on_download_complete(self, tile_files: list):
        """Handle download completion.

        Args:
            tile_files: List of downloaded tile file paths
        """
        self.download_task = None
        self._log(f'Download complete: {len(tile_files)} tiles downloaded')
        self.status_label.setText(self.tr('Download complete: {count} tiles').format(count=len(tile_files)))

        # Get selected output format
        output_format = self.output_format_group.checkedId()

        # 0 = tiles only, 1 = uncompressed, 2 = compressed
        if output_format == 0:
            # Tiles only - no merge
            self._log('Tiles only mode - skipping merge')
            self._finish_processing(tile_files)
        elif output_format in [1, 2] and tile_files:
            # Start merge processing
            self._start_cog_processing(tile_files, output_format)
        else:
            self._finish_processing(tile_files)

    def _on_download_failed(self, error: str):
        """Handle download failure.

        Args:
            error: Error message
        """
        self.download_task = None
        self._log(f'Download failed: {error}', Qgis.Critical)
        self.status_label.setText(self.tr('Download failed: {error}').format(error=error))
        self.progress_bar.setValue(0)
        self.download_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

        QMessageBox.critical(
            self,
            self.tr('Download Failed'),
            self.tr('Failed to download tiles:\n\n{error}').format(error=error)
        )

    def _start_cog_processing(self, tile_files: list, output_format: int):
        """Start merge processing.

        Args:
            tile_files: List of tile file paths
            output_format: 1=uncompressed, 2=compressed
        """
        format_names = {1: self.tr('uncompressed'), 2: self.tr('compressed')}
        format_name = format_names.get(output_format, self.tr('merged'))

        self.status_label.setText(self.tr('Creating {format} GeoTIFF...').format(format=format_name))
        self.progress_bar.setValue(0)

        # Save merged file in the same folder as the tiles
        if not self.service_output_dir:
            self._log('Error: service output directory not set', Qgis.Critical)
            return

        # Generate meaningful filename: servicename_merged_YYYYMMDD_HHMMSS.tif
        from datetime import datetime
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        folder_name = self.service_output_dir.name
        output_filename = f'{folder_name}_merged_{timestamp}.tif'
        output_cog = self.service_output_dir / output_filename

        self._log(f'Output will be saved to: {output_cog}')

        epsg = self.crs_selector.crs().postgisSrid()

        # Create processing task
        self.processing_task = COGProcessingTask(
            tile_files=[Path(f) for f in tile_files],
            output_cog=output_cog,
            epsg=epsg,
            output_format=output_format
        )

        # Connect signals
        self.processing_task.progressChanged.connect(self._on_processing_progress)
        self.processing_task.processingComplete.connect(self._on_processing_complete)
        self.processing_task.processingFailed.connect(self._on_processing_failed)
        self.processing_task.taskCompleted.connect(lambda: setattr(self, 'processing_task', None))
        self.processing_task.taskTerminated.connect(lambda: setattr(self, 'processing_task', None))

        # Add to task manager
        QgsApplication.taskManager().addTask(self.processing_task)

        self._log(f'Starting {format_name} GeoTIFF creation')

    def _on_processing_progress(self, progress: float):
        """Handle processing progress update.

        Args:
            progress: Progress percentage (0-100)
        """
        self.progress_bar.setValue(int(progress))
        self.status_label.setText(self.tr('Creating COG... {progress}%').format(progress=int(progress)))

    def _on_processing_complete(self, output_file: str):
        """Handle processing completion.

        Args:
            output_file: Path to output COG file
        """
        self.processing_task = None
        self._log(f'COG creation complete: {output_file}')
        self.status_label.setText(self.tr('Processing complete'))
        self.progress_bar.setValue(100)

        self._finish_processing([output_file])

    def _on_processing_failed(self, error: str):
        """Handle processing failure.

        Args:
            error: Error message
        """
        self.processing_task = None
        self._log(f'COG processing failed: {error}', Qgis.Critical)
        self.status_label.setText(self.tr('Processing failed: {error}').format(error=error))
        self.progress_bar.setValue(0)
        self.download_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

        QMessageBox.critical(
            self,
            self.tr('Processing Failed'),
            self.tr('Failed to create COG:\n\n{error}').format(error=error)
        )

    def _finish_processing(self, output_files: list):
        """Finish processing and add result to canvas.

        Args:
            output_files: List of output file paths
        """
        # Reset UI
        self.download_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setValue(100)
        self.status_label.setText(self.tr('Complete!'))

        self._log(f'Finishing processing with {len(output_files)} output file(s)')

        # Add to canvas if requested
        if self.add_to_canvas_checkbox.isChecked() and output_files:
            self._log(f'Add to canvas is enabled, processing {len(output_files)} files')
            for output_file in output_files:
                output_path = Path(output_file)
                self._log(f'Checking output file: {output_path}')
                self._log(f'File exists: {output_path.exists()}')

                if output_path.exists() and output_path.suffix.lower() in ['.tif', '.tiff']:
                    # Create raster layer
                    layer_name = output_path.stem
                    self._log(f'Creating raster layer: {layer_name}')
                    layer = QgsRasterLayer(str(output_path), layer_name)

                    if layer.isValid():
                        QgsProject.instance().addMapLayer(layer)
                        self._log(f'Added layer to canvas: {layer_name}')
                        self.iface.messageBar().pushMessage(
                            self.tr('Success'),
                            self.tr('Added layer: {name}').format(name=layer_name),
                            level=Qgis.Success,
                            duration=3
                        )
                    else:
                        self._log(f'Failed to load layer: {output_path}', Qgis.Warning)
                        self._log(f'Layer error: {layer.error().message()}', Qgis.Warning)
                else:
                    if not output_path.exists():
                        self._log(f'Output file does not exist: {output_path}', Qgis.Warning)
                    else:
                        self._log(f'Skipping non-TIFF file: {output_path}', Qgis.Info)
        else:
            if not self.add_to_canvas_checkbox.isChecked():
                self._log('Add to canvas is disabled')
            if not output_files:
                self._log('No output files to add')

        # Show completion message with file location
        if output_files:
            completion_msg = self.tr('Download and processing completed successfully!\n\nOutput saved to:\n{path}').format(path=output_files[0])
        else:
            completion_msg = self.tr('Download and processing completed successfully!')

        QMessageBox.information(
            self,
            self.tr('Complete'),
            completion_msg
        )

    def closeEvent(self, event):
        """Handle widget close event.

        Args:
            event: Close event
        """
        # Deactivate and clean up bbox tool
        self._deactivate_bbox_tool()

        # Cancel any running tasks
        if self.download_task:
            try:
                self.download_task.cancel()
            except RuntimeError:
                # Task C++ object has already been deleted
                pass
        if self.processing_task:
            try:
                self.processing_task.cancel()
            except RuntimeError:
                # Task C++ object has already been deleted
                pass

        super().closeEvent(event)
