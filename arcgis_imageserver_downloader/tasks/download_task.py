"""
QgsTask for downloading raster tiles in background
"""
from pathlib import Path
from typing import List, Optional, Tuple

from qgis.core import QgsTask, QgsMessageLog, Qgis
from qgis.PyQt.QtCore import pyqtSignal

from ..core.arcgis_client import ArcGISClient


class TileDownloadTask(QgsTask):
    """Background task for downloading raster tiles from ArcGIS ImageServer."""

    # Signals
    downloadComplete = pyqtSignal(list)  # list of downloaded file paths
    downloadFailed = pyqtSignal(str)  # error message

    def __init__(
        self,
        service_url: str,
        service_name: str,
        output_dir: Path,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        epsg: int = 32633,
        max_retry: int = 5,
        description: str = 'Downloading tiles'
    ):
        """Initialize download task.

        Args:
            service_url: Base URL of the service
            service_name: Name of the service
            output_dir: Directory to save tiles
            bbox: Optional bounding box (minx, miny, maxx, maxy)
            epsg: EPSG code for output
            max_retry: Maximum retry attempts
            description: Task description
        """
        super().__init__(description, QgsTask.CanCancel)

        # Store parameters (make copies of mutable objects)
        self.service_url = service_url
        self.service_name = service_name
        self.output_dir = Path(output_dir)
        self.bbox = bbox
        self.epsg = epsg
        self.max_retry = max_retry

        # Task state
        self.downloaded_files = []
        self.error_message = None
        self.client = None
        self.tile_ids = []

    def _log(self, message: str, level: Qgis.MessageLevel = Qgis.Info):
        """Log message to QGIS message log."""
        QgsMessageLog.logMessage(
            message,
            'ArcGIS ImageServer Downloader',
            level
        )

    def run(self):
        """Execute the download task.

        Returns:
            True if successful, False otherwise
        """
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)

            # Create client
            self.client = ArcGISClient()

            # Query tiles
            self._log(f'Querying tiles from {self.service_name}...')
            self.setProgress(0)

            self.tile_ids = self.client.query_tiles(
                self.service_url,
                self.service_name,
                self.bbox,
                self.epsg,
                self.epsg
            )

            if not self.tile_ids:
                self.error_message = 'No tiles found matching the query'
                return False

            self._log(f'Found {len(self.tile_ids)} tiles to download')

            # Download service metadata
            metadata_path = self.output_dir / f'{self.service_name.replace("/", "_")}.json'
            self.client.get_service_metadata(
                self.service_url,
                self.service_name,
                metadata_path
            )

            # Download tiles
            total_tiles = len(self.tile_ids)
            for i, tile_id in enumerate(self.tile_ids):
                if self.isCanceled():
                    self._log('Download cancelled by user', Qgis.Warning)
                    return False

                # Update progress
                progress = int((i / total_tiles) * 100)
                self.setProgress(progress)

                try:
                    # Get tile info
                    tile_info = self.client.get_tile_info(
                        self.service_url,
                        self.service_name,
                        tile_id
                    )

                    raster_files = tile_info.get('rasterFiles', [])
                    if not raster_files:
                        self._log(f'No rasterFiles for tile {tile_id}, skipping', Qgis.Warning)
                        continue
                    tile_filepath = raster_files[0]['id']
                    filename = tile_filepath.split("\\")[-1]

                    # Skip overview tiles
                    if filename.startswith("Ov_"):
                        self._log(f'Skipping overview tile: {filename}')
                        continue

                    # Download tile
                    output_path = self.client.download_tile(
                        self.service_url,
                        self.service_name,
                        tile_id,
                        tile_filepath,
                        self.output_dir,
                        self.max_retry
                    )

                    self.downloaded_files.append(str(output_path))
                    self._log(f'Downloaded {i+1}/{total_tiles}: {filename}')

                    # Download tile metadata
                    metadata_path = self.output_dir / f'{output_path.stem}.json'
                    self.client.get_tile_metadata(
                        self.service_url,
                        self.service_name,
                        tile_id,
                        metadata_path
                    )

                except ValueError as e:
                    # Skip overview tiles
                    self._log(str(e))
                    continue
                except Exception as e:
                    self._log(
                        f'Failed to download tile {tile_id}: {str(e)}',
                        Qgis.Warning
                    )
                    continue

            self.setProgress(100)
            self._log(f'Successfully downloaded {len(self.downloaded_files)} tiles')
            return True

        except Exception as e:
            self.error_message = str(e)
            self._log(f'Download task failed: {str(e)}', Qgis.Critical)
            return False

    def finished(self, result: bool):
        """Called when task finishes.

        Args:
            result: True if task completed successfully
        """
        if result:
            self._log(f'Download complete: {len(self.downloaded_files)} files')
            self.downloadComplete.emit(self.downloaded_files)
        else:
            error = self.error_message or 'Unknown error'
            self._log(f'Download failed: {error}', Qgis.Critical)
            self.downloadFailed.emit(error)

    def cancel(self):
        """Cancel the task."""
        self._log('Cancelling download task...', Qgis.Warning)
        super().cancel()
