"""
Main dock widget for ArcGIS ImageServer Downloader
"""
import os
from pathlib import Path
from typing import Optional, Tuple

from qgis.PyQt.QtCore import Qt, QCoreApplication
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
)
from qgis.gui import QgsDockWidget, QgsProjectionSelectionWidget
from qgis.core import (
    QgsProject,
    QgsRectangle,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
)

from ..core.service_manager import ServiceManager
from ..core.settings import PluginSettings
from .service_browser import ServiceBrowserWidget
from .bbox_tool import BBoxMapTool
from .server_management import ServerManagerMixin, custom_servers_path
from .download_controller import DownloadControllerMixin


class ArcGISImageServerDockWidget(QgsDockWidget, ServerManagerMixin, DownloadControllerMixin):
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
        csp = custom_servers_path()
        if csp.exists():
            self.service_manager.load_custom_servers(csp)

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
        return QCoreApplication.translate('ArcGISImageServerDownloader', message)

    def _init_ui(self):
        main_widget = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(self._build_server_section())
        layout.addWidget(self._build_services_section())
        layout.addWidget(self._build_bbox_section())
        layout.addWidget(self._build_output_section())
        layout.addWidget(self._build_progress_section())
        layout.addLayout(self._build_action_buttons())
        layout.addStretch()
        main_widget.setLayout(layout)
        self.setWidget(main_widget)
        self._populate_server_combo()

    def _build_server_section(self):
        group = QGroupBox(self.tr('Server'))
        row = QHBoxLayout()
        row.addWidget(QLabel(self.tr('Server:')))

        self.server_combo = QComboBox()
        self.server_combo.currentIndexChanged.connect(self._on_server_changed)
        row.addWidget(self.server_combo, 1)

        self.add_server_btn = QPushButton('+')
        self.add_server_btn.setMaximumWidth(30)
        self.add_server_btn.setToolTip(self.tr('Add custom server'))
        self.add_server_btn.clicked.connect(self._add_custom_server)
        row.addWidget(self.add_server_btn)

        self.edit_server_btn = QPushButton(self.tr('Edit'))
        self.edit_server_btn.setToolTip(self.tr('Edit or copy server settings'))
        self.edit_server_btn.clicked.connect(self._edit_server)
        self.edit_server_btn.setEnabled(False)
        row.addWidget(self.edit_server_btn)

        layout = QVBoxLayout()
        layout.addLayout(row)
        group.setLayout(layout)
        return group

    def _build_services_section(self):
        group = QGroupBox(self.tr('Services'))
        layout = QVBoxLayout()
        self.service_browser = ServiceBrowserWidget()
        self.service_browser.serviceSelected.connect(self._on_service_selected)
        layout.addWidget(self.service_browser)
        group.setLayout(layout)
        return group

    def _build_bbox_section(self):
        group = QGroupBox(self.tr('Bounding Box'))
        layout = QVBoxLayout()

        self.bbox_button_group = QButtonGroup()
        self.bbox_draw_radio = QRadioButton(self.tr('Draw on canvas'))
        self.bbox_layer_radio = QRadioButton(self.tr('From active layer extent'))
        self.bbox_manual_radio = QRadioButton(self.tr('Manual coordinates'))
        for btn in (self.bbox_draw_radio, self.bbox_layer_radio, self.bbox_manual_radio):
            self.bbox_button_group.addButton(btn)
            layout.addWidget(btn)

        # Connect toggled signals after setChecked to avoid stealing map tool on init
        self.bbox_draw_radio.setChecked(True)
        self.bbox_draw_radio.toggled.connect(self._on_bbox_method_changed)
        self.bbox_layer_radio.toggled.connect(self._on_bbox_method_changed)
        self.bbox_manual_radio.toggled.connect(self._on_bbox_method_changed)

        # Manual coordinate inputs (initially hidden)
        self.bbox_manual_widget = QWidget()
        manual_layout = QVBoxLayout()
        manual_layout.setContentsMargins(20, 0, 0, 0)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel(self.tr('Min X:')))
        self.bbox_minx = QLineEdit()
        row1.addWidget(self.bbox_minx)
        row1.addWidget(QLabel(self.tr('Min Y:')))
        self.bbox_miny = QLineEdit()
        row1.addWidget(self.bbox_miny)
        manual_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel(self.tr('Max X:')))
        self.bbox_maxx = QLineEdit()
        row2.addWidget(self.bbox_maxx)
        row2.addWidget(QLabel(self.tr('Max Y:')))
        self.bbox_maxy = QLineEdit()
        row2.addWidget(self.bbox_maxy)
        manual_layout.addLayout(row2)

        self.bbox_manual_widget.setLayout(manual_layout)
        self.bbox_manual_widget.setVisible(False)
        layout.addWidget(self.bbox_manual_widget)

        self.bbox_label = QLabel(self.tr('No bounding box selected'))
        self.bbox_label.setStyleSheet('color: gray; font-style: italic;')
        layout.addWidget(self.bbox_label)

        group.setLayout(layout)
        return group

    def _build_output_section(self):
        group = QGroupBox(self.tr('Output Settings'))
        layout = QVBoxLayout()

        crs_row = QHBoxLayout()
        crs_row.addWidget(QLabel(self.tr('Output CRS:')))
        self.crs_selector = QgsProjectionSelectionWidget()
        self.crs_selector.setCrs(QgsCoordinateReferenceSystem('EPSG:32633'))
        crs_row.addWidget(self.crs_selector, 1)
        layout.addLayout(crs_row)

        layout.addWidget(QLabel(self.tr('Output Format:')))
        self.output_format_group = QButtonGroup()

        self.tiles_only_radio = QRadioButton(self.tr('Tiles only (no merge)'))
        self.tiles_only_radio.setToolTip(self.tr('Download individual tiles without merging'))
        self.output_format_group.addButton(self.tiles_only_radio, 0)
        layout.addWidget(self.tiles_only_radio)

        self.merge_uncompressed_radio = QRadioButton(self.tr('Merge uncompressed (fast, large file)'))
        self.merge_uncompressed_radio.setToolTip(self.tr('Merge tiles into single GeoTIFF without compression - fastest but largest file'))
        self.output_format_group.addButton(self.merge_uncompressed_radio, 1)
        layout.addWidget(self.merge_uncompressed_radio)

        self.merge_compressed_radio = QRadioButton(self.tr('Merge compressed (recommended)'))
        self.merge_compressed_radio.setToolTip(self.tr('Merge tiles with LZW compression, tiling, and overviews - best balance of speed, size, and performance'))
        self.merge_compressed_radio.setChecked(True)
        self.output_format_group.addButton(self.merge_compressed_radio, 2)
        layout.addWidget(self.merge_compressed_radio)

        self.add_to_canvas_checkbox = QCheckBox(self.tr('Add to canvas'))
        self.add_to_canvas_checkbox.setChecked(True)
        layout.addWidget(self.add_to_canvas_checkbox)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel(self.tr('Output:')))
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setPlaceholderText(self.tr('Select output directory...'))
        path_row.addWidget(self.output_path_edit, 1)
        self.browse_btn = QPushButton('...')
        self.browse_btn.setMaximumWidth(30)
        self.browse_btn.clicked.connect(self._browse_output_dir)
        path_row.addWidget(self.browse_btn)
        layout.addLayout(path_row)

        group.setLayout(layout)
        return group

    def _build_progress_section(self):
        group = QGroupBox(self.tr('Progress'))
        layout = QVBoxLayout()
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)
        self.status_label = QLabel(self.tr('Ready'))
        self.status_label.setStyleSheet('color: gray; font-style: italic;')
        layout.addWidget(self.status_label)
        group.setLayout(layout)
        return group

    def _build_action_buttons(self):
        layout = QHBoxLayout()
        layout.addStretch()
        self.download_btn = QPushButton(self.tr('Download'))
        self.download_btn.clicked.connect(self._start_download)
        layout.addWidget(self.download_btn)
        self.cancel_btn = QPushButton(self.tr('Cancel'))
        self.cancel_btn.clicked.connect(self._cancel_download)
        self.cancel_btn.setEnabled(False)
        layout.addWidget(self.cancel_btn)
        return layout

    def _load_settings(self):
        """Load saved settings."""
        # Load last output directory
        last_output_dir = self.settings.get_last_output_dir()
        if last_output_dir:
            self.output_path_edit.setText(last_output_dir)

        # Load last server
        last_server_url = self.settings.get_last_server_url()
        if last_server_url:
            self._select_combo_by(last_server_url)

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
        preset = self.server_combo.itemData(index)
        if preset:
            self.current_preset = preset

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
        self.selected_service = service

    def _on_bbox_method_changed(self, checked: bool):
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

    def _deactivate_bbox_tool(self):
        """Deactivate bbox drawing tool."""
        if self.bbox_tool:
            if self.canvas.mapTool() == self.bbox_tool:
                self.canvas.unsetMapTool(self.bbox_tool)
            self.bbox_tool.cleanup()
            self.bbox_tool = None

    def _on_bbox_drawn(self, rect: QgsRectangle):
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

    def _update_bbox_from_layer(self):
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

    def _update_bbox_label(self):
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
        current_dir = self.output_path_edit.text() or os.path.expanduser('~')
        output_dir = QFileDialog.getExistingDirectory(
            self,
            self.tr('Select Output Directory'),
            current_dir
        )

        if output_dir:
            self.output_path_edit.setText(output_dir)

    def closeEvent(self, event):
        self._save_settings()
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
