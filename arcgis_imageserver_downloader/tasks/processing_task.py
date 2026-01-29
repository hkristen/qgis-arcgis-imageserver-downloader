"""
QgsTask for creating COG from tiles in background
"""
import tempfile
import shutil
from pathlib import Path
from typing import List, Optional

from qgis.core import (
    QgsTask,
    QgsMessageLog,
    Qgis,
    QgsProcessingContext,
    QgsProcessingFeedback
)
from qgis.PyQt.QtCore import pyqtSignal
from qgis import processing


class COGProcessingFeedback(QgsProcessingFeedback):
    """Custom feedback for processing that updates task progress."""

    def __init__(self, task):
        """Initialize feedback.

        Args:
            task: Parent QgsTask
        """
        super().__init__()
        self.task = task
        self.error_messages = []

    def reportError(self, error, fatalError=False):
        """Capture error messages.

        Args:
            error: Error message
            fatalError: Whether it's a fatal error
        """
        super().reportError(error, fatalError)
        self.error_messages.append(error)
        if self.task:
            self.task._log(f'GDAL Error: {error}', Qgis.Critical if fatalError else Qgis.Warning)

    def setProgress(self, progress):
        """Update progress.

        Args:
            progress: Progress percentage (0-100)
        """
        super().setProgress(progress)
        if self.task:
            self.task.setProgress(int(progress))

    def isCanceled(self):
        """Check if task is canceled.

        Returns:
            True if canceled
        """
        return self.task and self.task.isCanceled()


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
        """Initialize merge processing task.

        Args:
            tile_files: List of tile file paths
            output_cog: Output file path
            epsg: EPSG code for output
            nodata: Optional nodata value
            output_format: 1=uncompressed, 2=compressed
            description: Task description
        """
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

    def _log(self, message: str, level: Qgis.MessageLevel = Qgis.Info):
        """Log message to QGIS message log."""
        QgsMessageLog.logMessage(
            message,
            'ArcGIS ImageServer Downloader',
            level
        )

    def run(self):
        """Execute COG creation.

        Returns:
            True if successful, False otherwise
        """
        try:
            if not self.tile_files:
                self.error_message = 'No tile files provided'
                return False

            self._log(f'Creating merged GeoTIFF from {len(self.tile_files)} tiles...')

            # Create temporary directory
            self.temp_dir = tempfile.mkdtemp()
            temp_vrt = Path(self.temp_dir) / 'temp.vrt'
            temp_warped_vrt = Path(self.temp_dir) / 'temp_warped.vrt'

            # Create processing context and feedback
            context = QgsProcessingContext()
            feedback = COGProcessingFeedback(self)

            # Step 1: Build VRT (33% of progress)
            self._log('Building virtual raster...')
            self.setProgress(0)

            vrt_result = processing.run(
                'gdal:buildvirtualraster',
                {
                    'INPUT': [str(f) for f in self.tile_files],
                    'RESOLUTION': 0,
                    'SEPARATE': False,
                    'OUTPUT': str(temp_vrt)
                },
                context=context,
                feedback=feedback
            )

            if self.isCanceled():
                return False

            # Step 2: Warp to target EPSG (66% of progress)
            self._log(f'Warping to EPSG:{self.epsg}...')
            self.setProgress(33)

            warp_result = processing.run(
                'gdal:warpreproject',
                {
                    'INPUT': str(temp_vrt),
                    'SOURCE_CRS': None,
                    'TARGET_CRS': f'EPSG:{self.epsg}',
                    'RESAMPLING': 0,
                    'DATA_TYPE': 0,
                    'MULTITHREADING': True,
                    'OUTPUT': str(temp_warped_vrt)
                },
                context=context,
                feedback=feedback
            )

            if self.isCanceled():
                return False

            # Step 3: Create output GeoTIFF based on format selection
            format_names = {1: 'uncompressed', 2: 'compressed'}
            format_name = format_names.get(self.output_format, 'compressed')
            self._log(f'Creating {format_name} GeoTIFF...')
            self.setProgress(66)

            # Ensure output directory exists
            self.output_cog.parent.mkdir(parents=True, exist_ok=True)

            # Check if input VRT exists
            if not temp_warped_vrt.exists():
                self.error_message = f'Input VRT not found: {temp_warped_vrt}'
                self._log(self.error_message, Qgis.Critical)
                return False

            self._log(f'Input VRT: {temp_warped_vrt}')
            self._log(f'Output file: {self.output_cog}')
            self._log(f'Output format: {self.output_format} ({format_name})')

            # Build creation options based on output format
            if self.output_format == 1:
                # Uncompressed - no compression, no tiling
                extra_options = '-co BIGTIFF=YES'
            else:
                # Compressed (format 2 or default) - LZW compression with tiling
                extra_options = '-co COMPRESS=LZW -co TILED=YES -co BIGTIFF=YES'

            # Add nodata if specified
            translate_options = ''
            if self.nodata is not None:
                translate_options = f'-a_nodata {self.nodata}'

            self._log(f'Creation options: {extra_options}')
            if translate_options:
                self._log(f'Translate options: {translate_options}')

            try:
                translate_result = processing.run(
                    'gdal:translate',
                    {
                        'INPUT': str(temp_warped_vrt),
                        'TARGET_CRS': None,
                        'NODATA': None,
                        'COPY_SUBDATASETS': False,
                        'OPTIONS': translate_options if translate_options else '',
                        'EXTRA': extra_options,
                        'DATA_TYPE': 0,
                        'OUTPUT': str(self.output_cog)
                    },
                    context=context,
                    feedback=feedback
                )
                self._log(f'GDAL translate result: {translate_result}')
            except Exception as e:
                self.error_message = f'GDAL translate failed: {str(e)}'
                self._log(self.error_message, Qgis.Critical)
                if hasattr(feedback, 'error_messages') and feedback.error_messages:
                    self._log(f'GDAL errors: {feedback.error_messages}', Qgis.Critical)
                return False

            if self.isCanceled():
                return False

            # Step 4: Add overviews for better performance (only for compressed format)
            if self.output_format == 2 and self.output_cog.exists():
                self._log('Adding overviews...')
                self.setProgress(85)

                try:
                    processing.run(
                        'gdal:overviews',
                        {
                            'INPUT': str(self.output_cog),
                            'LEVELS': '2 4 8 16',
                            'RESAMPLING': 0,  # Nearest neighbor
                            'FORMAT': 0  # Internal (GTiff)
                        },
                        context=context,
                        feedback=feedback
                    )
                    self._log('Overviews added successfully')
                except Exception as e:
                    # Overviews are nice to have but not critical
                    self._log(f'Failed to add overviews (non-critical): {str(e)}', Qgis.Warning)
            else:
                # Skip overviews for uncompressed format
                self._log('Skipping overviews (uncompressed format)')
                self.setProgress(85)

            if self.isCanceled():
                return False

            self.setProgress(100)

            file_size = self.output_cog.stat().st_size / (1024 * 1024)  # MB
            self._log(f'Successfully created COG: {self.output_cog} ({file_size:.2f} MB)')
            return True

        except Exception as e:
            self.error_message = str(e)
            self._log(f'COG processing failed: {str(e)}', Qgis.Critical)
            return False

        finally:
            # Cleanup temporary files (always clean up VRT files)
            if self.temp_dir:
                try:
                    shutil.rmtree(self.temp_dir)
                    self._log('Cleaned up temporary files')
                except Exception as e:
                    self._log(f'Warning: Could not remove temporary files: {e}', Qgis.Warning)

    def finished(self, result: bool):
        """Called when task finishes.

        Args:
            result: True if task completed successfully
        """
        if result:
            self._log(f'COG processing complete: {self.output_cog}')
            self.processingComplete.emit(str(self.output_cog))
        else:
            error = self.error_message or 'Unknown error'
            self._log(f'COG processing failed: {error}', Qgis.Critical)
            self.processingFailed.emit(error)

    def cancel(self):
        """Cancel the task."""
        self._log('Cancelling COG processing task...', Qgis.Warning)
        super().cancel()
