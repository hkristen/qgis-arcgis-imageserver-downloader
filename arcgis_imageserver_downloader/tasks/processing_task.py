"""
QgsTask for creating COG from tiles in background
"""
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import List, Optional

from qgis.core import QgsTask, Qgis

from ..utils import log, subprocess_run_kwargs
from qgis.PyQt.QtCore import pyqtSignal


class COGProcessingTask(QgsTask):
    """Background task for creating compressed, tiled GeoTIFF with overviews from tiles."""

    processingComplete = pyqtSignal(str)
    processingFailed = pyqtSignal(str)

    def __init__(
        self,
        tile_files: List[Path],
        output_cog: Path,
        epsg: int = 32633,
        nodata: Optional[float] = None,
        output_format: int = 2,
        compression: str = 'LZW',
        description: str = 'Creating GeoTIFF'
    ):
        """Initialize merge processing task."""
        super().__init__(description, QgsTask.CanCancel)

        self.tile_files = [Path(f) for f in tile_files]
        self.output_cog = Path(output_cog)
        self.epsg = epsg
        self.nodata = nodata
        self.output_format = output_format
        self.compression = compression
        self.error_message = None
        self.temp_dir = None

    def run(self):
        try:
            if not self.tile_files:
                self.error_message = 'No tile files provided'
                return False

            log(f'Creating merged GeoTIFF from {len(self.tile_files)} tiles...')

            self.temp_dir = tempfile.mkdtemp()
            temp_warped = str(Path(self.temp_dir) / 'temp_warped.tif')

            log(f'Warping {len(self.tile_files)} tiles to EPSG:{self.epsg}...')
            self.setProgress(25)

            try:
                subprocess.run(
                    ['gdalwarp', '-t_srs', f'EPSG:{self.epsg}',
                     '-multi', '-wo', 'NUM_THREADS=ALL_CPUS']
                    + [str(f) for f in self.tile_files]
                    + [temp_warped],
                    **subprocess_run_kwargs()
                )
            except subprocess.CalledProcessError as e:
                self.error_message = f'gdalwarp failed: {e.stderr}'
                log(self.error_message, Qgis.Critical)
                return False

            if self.isCanceled():
                return False

            format_names = {1: 'uncompressed', 2: self.compression}
            format_name = format_names.get(self.output_format, self.compression)
            log(f'Creating {format_name} GeoTIFF...')
            self.setProgress(66)

            self.output_cog.parent.mkdir(parents=True, exist_ok=True)

            if not Path(temp_warped).exists():
                self.error_message = f'Warped intermediate file not found: {temp_warped}'
                log(self.error_message, Qgis.Critical)
                return False

            if self.output_format == 1:
                translate_cmd = [
                    'gdal_translate',
                    '-co', 'BIGTIFF=YES',
                ]
            else:
                translate_cmd = [
                    'gdal_translate',
                    '-co', f'COMPRESS={self.compression}',
                    '-co', 'TILED=YES',
                    '-co', 'BIGTIFF=YES',
                ]

            if self.nodata is not None:
                translate_cmd += ['-a_nodata', str(self.nodata)]

            translate_cmd += [temp_warped, str(self.output_cog)]

            try:
                subprocess.run(translate_cmd, **subprocess_run_kwargs())
            except subprocess.CalledProcessError as e:
                self.error_message = f'gdal_translate failed: {e.stderr}'
                log(self.error_message, Qgis.Critical)
                return False

            if self.isCanceled():
                return False

            if self.output_format == 2 and self.output_cog.exists():
                log('Adding overviews...')
                self.setProgress(85)

                overview_resampling = 'average' if self.compression == 'JPEG' else 'nearest'
                try:
                    subprocess.run(
                        ['gdaladdo', '-r', overview_resampling, str(self.output_cog), '2', '4', '8', '16'],
                        **subprocess_run_kwargs()
                    )
                    log('Overviews added successfully')
                except subprocess.CalledProcessError as e:
                    log(f'Failed to add overviews (non-critical): {e.stderr}', Qgis.Warning)
            else:
                log('Skipping overviews (uncompressed format)')
                self.setProgress(85)

            if self.isCanceled():
                return False

            self.setProgress(100)

            file_size = self.output_cog.stat().st_size / (1024 * 1024)
            log(f'Successfully created COG: {self.output_cog} ({file_size:.2f} MB)')
            return True

        except Exception as e:
            self.error_message = str(e)
            log(f'COG processing failed: {str(e)}', Qgis.Critical)
            return False

        finally:
            if self.temp_dir:
                try:
                    shutil.rmtree(self.temp_dir)
                    log('Cleaned up temporary files')
                except Exception as e:
                    log(f'Warning: Could not remove temporary files: {e}', Qgis.Warning)

    def finished(self, result: bool):
        if result:
            log(f'COG processing complete: {self.output_cog}')
            self.processingComplete.emit(str(self.output_cog))
        else:
            error = self.error_message or 'Unknown error'
            log(f'COG processing failed: {error}', Qgis.Critical)
            self.processingFailed.emit(error)

    def cancel(self):
        log('Cancelling COG processing task...', Qgis.Warning)
        super().cancel()
