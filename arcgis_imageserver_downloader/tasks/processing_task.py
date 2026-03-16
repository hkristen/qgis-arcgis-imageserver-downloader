"""
QgsTask for creating COG from tiles in background
"""
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import List, Optional

from qgis.core import QgsTask, Qgis

from ..utils import log
from qgis.PyQt.QtCore import pyqtSignal


class COGProcessingTask(QgsTask):
    """Background task for creating compressed, tiled GeoTIFF with overviews from tiles."""

    # Signals
    processingProgress = pyqtSignal(int, str)  # progress, message
    processingComplete = pyqtSignal(str)  # output file path
    processingFailed = pyqtSignal(str)  # error message

    def __init__(
        self,
        tile_files: List[Path],
        output_cog: Path,
        epsg: int = 32633,
        nodata: Optional[float] = None,
        output_format: int = 2,
        description: str = 'Creating GeoTIFF'
    ):
        """Initialize merge processing task."""
        super().__init__(description, QgsTask.CanCancel)

        # Store parameters (make copies)
        self.tile_files = [Path(f) for f in tile_files]
        self.output_cog = Path(output_cog)
        self.epsg = epsg
        self.nodata = nodata
        self.output_format = output_format

        # Task state
        self.error_message = None
        self.temp_dir = None

    def run(self):
        try:
            if not self.tile_files:
                self.error_message = 'No tile files provided'
                return False

            log(f'Creating merged GeoTIFF from {len(self.tile_files)} tiles...')

            # Create temporary directory
            self.temp_dir = tempfile.mkdtemp()
            temp_vrt = str(Path(self.temp_dir) / 'temp.vrt')
            temp_warped_vrt = str(Path(self.temp_dir) / 'temp_warped.vrt')

            # Step 1: Build VRT
            log('Building virtual raster...')
            self.setProgress(0)

            try:
                subprocess.run(
                    ['gdalbuildvrt', temp_vrt] + [str(f) for f in self.tile_files],
                    check=True,
                    capture_output=True,
                    text=True
                )
            except subprocess.CalledProcessError as e:
                self.error_message = f'gdalbuildvrt failed: {e.stderr}'
                log(self.error_message, Qgis.Critical)
                return False

            if self.isCanceled():
                return False

            # Step 2: Warp to target EPSG
            log(f'Warping to EPSG:{self.epsg}...')
            self.setProgress(33)

            try:
                subprocess.run(
                    ['gdalwarp', '-t_srs', f'EPSG:{self.epsg}', '-multi', temp_vrt, temp_warped_vrt],
                    check=True,
                    capture_output=True,
                    text=True
                )
            except subprocess.CalledProcessError as e:
                self.error_message = f'gdalwarp failed: {e.stderr}'
                log(self.error_message, Qgis.Critical)
                return False

            if self.isCanceled():
                return False

            # Step 3: Create output GeoTIFF based on format selection
            format_names = {1: 'uncompressed', 2: 'compressed'}
            format_name = format_names.get(self.output_format, 'compressed')
            log(f'Creating {format_name} GeoTIFF...')
            self.setProgress(66)

            # Ensure output directory exists
            self.output_cog.parent.mkdir(parents=True, exist_ok=True)

            if not Path(temp_warped_vrt).exists():
                self.error_message = f'Input VRT not found: {temp_warped_vrt}'
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
                    '-co', 'COMPRESS=LZW',
                    '-co', 'TILED=YES',
                    '-co', 'BIGTIFF=YES',
                ]

            if self.nodata is not None:
                translate_cmd += ['-a_nodata', str(self.nodata)]

            translate_cmd += [temp_warped_vrt, str(self.output_cog)]

            try:
                subprocess.run(
                    translate_cmd,
                    check=True,
                    capture_output=True,
                    text=True
                )
            except subprocess.CalledProcessError as e:
                self.error_message = f'gdal_translate failed: {e.stderr}'
                log(self.error_message, Qgis.Critical)
                return False

            if self.isCanceled():
                return False

            # Step 4: Add overviews for better performance (only for compressed format)
            if self.output_format == 2 and self.output_cog.exists():
                log('Adding overviews...')
                self.setProgress(85)

                try:
                    subprocess.run(
                        ['gdaladdo', '-r', 'nearest', str(self.output_cog), '2', '4', '8', '16'],
                        check=True,
                        capture_output=True,
                        text=True
                    )
                    log('Overviews added successfully')
                except subprocess.CalledProcessError as e:
                    # Overviews are nice to have but not critical
                    log(f'Failed to add overviews (non-critical): {e.stderr}', Qgis.Warning)
            else:
                # Skip overviews for uncompressed format
                log('Skipping overviews (uncompressed format)')
                self.setProgress(85)

            if self.isCanceled():
                return False

            self.setProgress(100)

            file_size = self.output_cog.stat().st_size / (1024 * 1024)  # MB
            log(f'Successfully created COG: {self.output_cog} ({file_size:.2f} MB)')
            return True

        except Exception as e:
            self.error_message = str(e)
            log(f'COG processing failed: {str(e)}', Qgis.Critical)
            return False

        finally:
            # Cleanup temporary files (always clean up VRT files)
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
