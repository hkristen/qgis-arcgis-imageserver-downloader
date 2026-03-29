"""
Service browser widget for discovering and filtering ArcGIS services
"""
from typing import Optional, List, Dict

from qgis.PyQt.QtCore import Qt, pyqtSignal, QUrl, QCoreApplication
from .compat import UserRole, AscendingOrder, SelectRows, SingleSelection, NoEditTriggers, HeaderStretch, ResizeToContents, HeaderFixed
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QLineEdit,
    QLabel,
    QPushButton,
    QHeaderView,
    QMessageBox
)
from qgis.core import Qgis, QgsTask, QgsApplication

from ..core.arcgis_client import ArcGISClient
from ..utils import log


class ServiceFetchTask(QgsTask):
    """Background task for fetching services."""

    def __init__(self, base_url: str):
        super().__init__('Fetching services', QgsTask.CanCancel)
        self.base_url = base_url
        self.services = []
        self.error_message = None

    def run(self):
        try:
            client = ArcGISClient()
            self.services = client.get_services(self.base_url)
            return True
        except Exception as e:
            self.error_message = str(e)
            log(f'Failed to fetch services: {e}', Qgis.Critical)
            return False


class ServiceBrowserWidget(QWidget):
    """Widget for browsing and selecting ArcGIS ImageServer services."""

    # Signal emitted when service is selected
    serviceSelected = pyqtSignal(dict)  # service info dictionary

    def __init__(self, parent=None):
        """Initialize the service browser widget."""
        super().__init__(parent)

        self.services = []
        self.filtered_services = []
        self.current_base_url = None
        self.fetch_task = None

        self._init_ui()

    def tr(self, message):
        return QCoreApplication.translate('ArcGISImageServerDownloader', message)

    def _init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        # Filter box
        filter_layout = QHBoxLayout()
        filter_label = QLabel(self.tr('Filter:'))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(self.tr('Search services...'))
        self.filter_edit.textChanged.connect(self._filter_services)
        filter_layout.addWidget(filter_label)
        filter_layout.addWidget(self.filter_edit)
        layout.addLayout(filter_layout)

        # Service table
        self.service_table = QTableWidget()
        self.service_table.setColumnCount(4)
        self.service_table.setHorizontalHeaderLabels([
            self.tr('Service Name'),
            self.tr('Category'),
            self.tr('Year'),
            self.tr('Info')
        ])
        self.service_table.setSelectionBehavior(SelectRows)
        self.service_table.setSelectionMode(SingleSelection)
        self.service_table.setEditTriggers(NoEditTriggers)
        self.service_table.setSortingEnabled(True)

        # Set column widths
        header = self.service_table.horizontalHeader()
        header.setSectionResizeMode(0, HeaderStretch)
        header.setSectionResizeMode(1, ResizeToContents)
        header.setSectionResizeMode(2, ResizeToContents)
        header.setSectionResizeMode(3, HeaderFixed)
        header.resizeSection(3, 50)

        # Connect selection signal
        self.service_table.itemSelectionChanged.connect(self._on_service_selected)

        layout.addWidget(self.service_table)

        # Status label
        self.status_label = QLabel('')
        self.status_label.setStyleSheet('color: gray; font-style: italic;')
        layout.addWidget(self.status_label)

        self.setLayout(layout)

    def load_services(self, base_url: str):
        """Load services from ArcGIS REST endpoint."""
        self.current_base_url = base_url
        self.services = []
        self.filtered_services = []
        self.service_table.setRowCount(0)
        self.status_label.setText(self.tr('Loading services...'))

        # Cancel existing task if running
        if self.fetch_task:
            try:
                if self.fetch_task.status() == QgsTask.Running:
                    self.fetch_task.cancel()
            except RuntimeError:
                # Task object has been deleted by Qt - ignore
                pass

        # Create and run fetch task
        self.fetch_task = ServiceFetchTask(base_url)
        self.fetch_task.taskCompleted.connect(self._on_fetch_complete)
        self.fetch_task.taskTerminated.connect(self._on_fetch_failed)

        QgsApplication.taskManager().addTask(self.fetch_task)

    def _on_fetch_complete(self):
        task = self.fetch_task
        self.fetch_task = None
        if task:
            try:
                self.services = task.services
                self.filtered_services = self.services.copy()
                self._populate_table()
                self.status_label.setText(self.tr('Found {0} services').format(len(self.services)))
            except RuntimeError:
                # Task object has been deleted by Qt
                self.status_label.setText(self.tr('Failed to load services'))
                log('Task object was deleted before completion handler', Qgis.Warning)

    def _on_fetch_failed(self):
        task = self.fetch_task
        self.fetch_task = None
        if task:
            try:
                if task.error_message:
                    self.status_label.setText(self.tr('Failed to load services'))
                    QMessageBox.warning(
                        self,
                        self.tr('Error'),
                        self.tr('Failed to fetch services:\n\n{0}').format(task.error_message)
                    )
                else:
                    self.status_label.setText(self.tr('Service fetch cancelled'))
            except RuntimeError:
                self.status_label.setText(self.tr('Service fetch cancelled'))
        else:
            self.status_label.setText(self.tr('Service fetch cancelled'))

    def _populate_table(self):
        self.service_table.blockSignals(True)
        self.service_table.setSortingEnabled(False)
        self.service_table.setRowCount(len(self.filtered_services))

        for row, service in enumerate(self.filtered_services):
            # Service name
            name_item = QTableWidgetItem(service.get('service_name', ''))
            name_item.setData(UserRole, service)
            self.service_table.setItem(row, 0, name_item)

            # Category
            category_item = QTableWidgetItem(service.get('category', ''))
            self.service_table.setItem(row, 1, category_item)

            # Year
            year = service.get('year', '')
            year_item = QTableWidgetItem(str(year) if year else '')
            self.service_table.setItem(row, 2, year_item)

            # Info button
            info_btn = QPushButton('🔗')
            info_btn.setMaximumWidth(40)
            info_btn.setToolTip(self.tr('View service metadata in browser'))
            info_btn.clicked.connect(lambda checked, s=service: self._open_service_metadata(s))
            self.service_table.setCellWidget(row, 3, info_btn)

        self.service_table.setSortingEnabled(True)
        self.service_table.sortItems(0, AscendingOrder)
        self.service_table.blockSignals(False)

    def _filter_services(self, text: str):
        text = text.lower()

        if not text:
            self.filtered_services = self.services.copy()
        else:
            self.filtered_services = [
                s for s in self.services
                if text in s.get('service_name', '').lower()
                or text in s.get('category', '').lower()
                or text in str(s.get('year', '')).lower()
            ]

        self._populate_table()
        self.status_label.setText(
            self.tr('Showing {0} of {1} services').format(len(self.filtered_services), len(self.services))
        )

    def _on_service_selected(self):
        selected_items = self.service_table.selectedItems()
        if not selected_items:
            return

        # Get service data from first column
        row = selected_items[0].row()
        name_item = self.service_table.item(row, 0)
        if name_item:
            service = name_item.data(UserRole)
            if service:
                # Add base_url to service info (shallow copy to avoid mutating stored data)
                service = dict(service)
                service['base_url'] = self.current_base_url
                self.serviceSelected.emit(service)

    def _open_service_metadata(self, service: dict):
        if not self.current_base_url:
            return

        # Build the ImageServer URL
        service_name = service.get('name', '')
        metadata_url = f"{self.current_base_url}/{service_name}/ImageServer"

        # Open in default browser
        QDesktopServices.openUrl(QUrl(metadata_url))

    def get_selected_service(self) -> Optional[Dict]:
        """Get currently selected service."""
        selected_items = self.service_table.selectedItems()
        if not selected_items:
            return None

        row = selected_items[0].row()
        name_item = self.service_table.item(row, 0)
        if name_item:
            service = name_item.data(UserRole)
            if service:
                service = dict(service)
                service['base_url'] = self.current_base_url
                return service

        return None

    def restore_selection(self, service_name: str):
        """Re-select a row by its full service name without emitting serviceSelected."""
        for row in range(self.service_table.rowCount()):
            item = self.service_table.item(row, 0)
            if item:
                svc = item.data(UserRole)
                if svc and svc.get('name') == service_name:
                    self.service_table.blockSignals(True)
                    self.service_table.selectRow(row)
                    self.service_table.scrollToItem(item)
                    self.service_table.blockSignals(False)
                    return

    def clear(self):
        self.services = []
        self.filtered_services = []
        self.service_table.setRowCount(0)
        self.filter_edit.clear()
        self.status_label.setText('')
