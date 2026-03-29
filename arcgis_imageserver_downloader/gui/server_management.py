from pathlib import Path

from qgis.PyQt.QtCore import QCoreApplication, QUrl
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
)
from .compat import DialogOk, DialogCancel, DialogAccepted
from qgis.core import QgsApplication

from ..core.service_manager import ServicePreset


def custom_servers_path():
    return Path(QgsApplication.qgisSettingsDirPath()) / 'arcgis_imageserver_custom_servers.json'


class ServerDialog(QDialog):
    """Dialog for adding or editing server configurations."""

    def __init__(self, parent=None, title='Server Configuration', name='', url=''):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(400)

        layout = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setText(name)
        self.name_edit.setPlaceholderText(self.tr('e.g., My Custom Server'))
        layout.addRow(self.tr('Server Name:'), self.name_edit)

        self.url_edit = QLineEdit()
        self.url_edit.setText(url)
        self.url_edit.setPlaceholderText(self.tr('e.g., https://example.com/arcgis/rest/services'))
        layout.addRow(self.tr('Server URL:'), self.url_edit)

        button_box = QDialogButtonBox(DialogOk | DialogCancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

        self.setLayout(layout)

    def tr(self, message):
        return QCoreApplication.translate('ArcGISImageServerDownloader', message)

    def get_values(self):
        name = self.name_edit.text().strip()
        url = self.url_edit.text().strip()

        if not (name and url):
            return None, None

        parsed = QUrl(url)
        if not parsed.isValid() or parsed.scheme() not in ('http', 'https'):
            return name, None

        return name, url


class ServerManagerMixin:

    def _populate_server_combo(self):
        self.server_combo.clear()
        self.server_combo.addItem(self.tr('-- Select a server --'), None)

        for preset in self.service_manager.get_all_presets():
            self.server_combo.addItem(preset.name, preset)

        if self.service_manager.get_custom_servers():
            self.server_combo.insertSeparator(self.server_combo.count())
            for preset in self.service_manager.get_custom_servers():
                self.server_combo.addItem(self.tr('{name} (Custom)').format(name=preset.name), preset)

    def _select_combo_by(self, url, name=None):
        for i in range(self.server_combo.count()):
            preset = self.server_combo.itemData(i)
            if preset and preset.url == url and (name is None or preset.name == name):
                self.server_combo.setCurrentIndex(i)
                break

    def _show_server_input_error(self, name):
        if name:
            QMessageBox.warning(self, self.tr('Invalid Input'), self.tr('URL must be a valid http or https address.'))
        else:
            QMessageBox.warning(self, self.tr('Invalid Input'), self.tr('Both server name and URL are required.'))

    def _add_custom_server(self):
        dialog = ServerDialog(parent=self, title=self.tr('Add Custom Server'))

        if dialog.exec() == DialogAccepted:
            name, url = dialog.get_values()

            if name and url:
                preset = ServicePreset(
                    name=name,
                    url=url,
                    default_epsg=self.crs_selector.crs().postgisSrid()
                )
                self.service_manager.add_custom_server(preset)
                self.service_manager.save_custom_servers(custom_servers_path())
                self._populate_server_combo()
                self._select_combo_by(url=preset.url, name=preset.name)
            else:
                self._show_server_input_error(name)

    def _edit_server(self):
        if not self.current_preset:
            return

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

        if dialog.exec() == DialogAccepted:
            name, url = dialog.get_values()

            if name and url:
                if is_custom:
                    self.current_preset.name = name
                    self.current_preset.url = url
                    self.current_preset.default_epsg = self.crs_selector.crs().postgisSrid()
                else:
                    new_preset = ServicePreset(
                        name=name,
                        url=url,
                        default_epsg=self.crs_selector.crs().postgisSrid(),
                        description=self.tr('Copy of {name}').format(name=self.current_preset.name)
                    )
                    self.service_manager.add_custom_server(new_preset)
                    self.current_preset = new_preset

                self.service_manager.save_custom_servers(custom_servers_path())
                self._populate_server_combo()
                self._select_combo_by(url=url, name=name)
            else:
                self._show_server_input_error(name)
