from datetime import datetime
from pathlib import Path

from qgis.PyQt.QtWidgets import QMessageBox
from qgis.core import QgsProject, QgsRasterLayer, QgsApplication, Qgis

from ..utils import log
from ..tasks.download_task import TileDownloadTask
from ..tasks.processing_task import COGProcessingTask


class DownloadControllerMixin:

    def _validate_inputs(self) -> bool:
        selected_service = self.service_browser.get_selected_service()
        checks = [
            (not self.current_preset, 'Please select a server.'),
            (not selected_service, 'Please select a service.'),
            (selected_service is not None and not selected_service.get('base_url'), 'Selected service has no server URL. Please re-select a server.'),
            (not self._get_bbox(), 'Please select a bounding box.'),
            (not self.output_path_edit.text(), 'Please select an output directory.'),
        ]
        for failed, msg in checks:
            if failed:
                QMessageBox.warning(self, self.tr('Validation Error'), self.tr(msg))
                return False
        return True

    def _start_download(self):
        if not self._validate_inputs():
            return

        self._save_settings()

        selected_service = self.service_browser.get_selected_service()
        service_url = selected_service['base_url']
        service_name = selected_service['name']
        bbox = self._get_bbox()
        output_dir = Path(self.output_path_edit.text())
        epsg = self.crs_selector.crs().postgisSrid()

        service_output_dir = output_dir / service_name.replace('/', '_')
        self.service_output_dir = service_output_dir

        self.download_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self.status_label.setText(self.tr('Starting download...'))

        self.download_task = TileDownloadTask(
            service_url=service_url,
            service_name=service_name,
            output_dir=service_output_dir,
            bbox=bbox,
            epsg=epsg,
            max_retry=self.settings.get_max_retry()
        )

        self.download_task.progressChanged.connect(self._on_download_progress)
        self.download_task.downloadComplete.connect(self._on_download_complete)
        self.download_task.downloadFailed.connect(self._on_download_failed)
        self.download_task.taskCompleted.connect(lambda: setattr(self, 'download_task', None))
        self.download_task.taskTerminated.connect(lambda: setattr(self, 'download_task', None))

        QgsApplication.taskManager().addTask(self.download_task)
        log(f'Starting download for service: {service_name}')

        # Restore service selection in case addTask event processing changed it
        self.service_browser.restore_selection(service_name)

    def _cancel_download(self):
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
        self.progress_bar.setValue(int(progress))
        self.status_label.setText(self.tr('Downloading tiles... {progress}%').format(progress=int(progress)))

    def _on_download_complete(self, tile_files: list):
        self.download_task = None
        log(f'Download complete: {len(tile_files)} tiles downloaded')
        self.status_label.setText(self.tr('Download complete: {count} tiles').format(count=len(tile_files)))

        output_format = self.output_format_group.checkedId()
        if output_format == 0:
            self._finish_processing(tile_files)
        elif output_format in [1, 2] and tile_files:
            self._start_cog_processing(tile_files, output_format)
        else:
            self._finish_processing(tile_files)

    def _on_download_failed(self, error: str):
        self._task_failed('download_task', error, self.tr('Download Failed'))

    def _task_failed(self, task_attr, error, title):
        setattr(self, task_attr, None)
        log(f'{title}: {error}', Qgis.Critical)
        self.status_label.setText(f'{title}: {error}')
        self.progress_bar.setValue(0)
        self.download_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        QMessageBox.critical(self, title, error)

    def _start_cog_processing(self, tile_files: list, output_format: int):
        format_names = {1: self.tr('uncompressed'), 2: self.tr('compressed')}
        format_name = format_names.get(output_format, self.tr('merged'))

        self.status_label.setText(self.tr('Creating {format} GeoTIFF...').format(format=format_name))
        self.progress_bar.setValue(0)

        if not self.service_output_dir:
            log('Error: service output directory not set', Qgis.Critical)
            return

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        folder_name = self.service_output_dir.name
        output_cog = self.service_output_dir / f'{folder_name}_merged_{timestamp}.tif'
        epsg = self.crs_selector.crs().postgisSrid()

        compression = self._compression_options[self.compression_combo.currentIndex()][1] if output_format == 2 else 'LZW'

        self.processing_task = COGProcessingTask(
            tile_files=[Path(f) for f in tile_files],
            output_cog=output_cog,
            epsg=epsg,
            output_format=output_format,
            compression=compression
        )

        self.processing_task.progressChanged.connect(self._on_processing_progress)
        self.processing_task.processingComplete.connect(self._on_processing_complete)
        self.processing_task.processingFailed.connect(self._on_processing_failed)
        self.processing_task.taskCompleted.connect(lambda: setattr(self, 'processing_task', None))
        self.processing_task.taskTerminated.connect(lambda: setattr(self, 'processing_task', None))

        QgsApplication.taskManager().addTask(self.processing_task)

    def _on_processing_progress(self, progress: float):
        self.progress_bar.setValue(int(progress))
        self.status_label.setText(self.tr('Creating COG... {progress}%').format(progress=int(progress)))

    def _on_processing_complete(self, output_file: str):
        self.processing_task = None
        log(f'COG creation complete: {output_file}')
        self.status_label.setText(self.tr('Processing complete'))
        self.progress_bar.setValue(100)
        self._finish_processing([output_file])

    def _on_processing_failed(self, error: str):
        self._task_failed('processing_task', error, self.tr('Processing Failed'))

    def _finish_processing(self, output_files: list):
        self.download_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setValue(100)
        self.status_label.setText(self.tr('Complete!'))

        if self.add_to_canvas_checkbox.isChecked() and output_files:
            for output_file in output_files:
                output_path = Path(output_file)
                if output_path.exists() and output_path.suffix.lower() in ['.tif', '.tiff']:
                    layer_name = output_path.stem
                    layer = QgsRasterLayer(str(output_path), layer_name)
                    if layer.isValid():
                        QgsProject.instance().addMapLayer(layer)
                        self.iface.messageBar().pushMessage(
                            self.tr('Success'),
                            self.tr('Added layer: {name}').format(name=layer_name),
                            level=Qgis.Success,
                            duration=3
                        )
                    else:
                        log(f'Failed to load layer: {output_path}', Qgis.Warning)
                        log(f'Layer error: {layer.error().message()}', Qgis.Warning)
                elif not output_path.exists():
                    log(f'Output file does not exist: {output_path}', Qgis.Warning)

        if output_files:
            completion_msg = self.tr('Download and processing completed successfully!\n\nOutput saved to:\n{path}').format(path=output_files[0])
        else:
            completion_msg = self.tr('Download and processing completed successfully!')

        QMessageBox.information(self, self.tr('Complete'), completion_msg)

        # Restore service selection after modal dialog returns focus to the dock
        if self.selected_service:
            self.service_browser.restore_selection(self.selected_service['name'])
