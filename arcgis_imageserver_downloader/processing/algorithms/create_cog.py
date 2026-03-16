"""
Processing algorithm to create Cloud Optimized GeoTIFF from tiles
"""
import subprocess
import tempfile
import shutil
import os
from pathlib import Path

from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterFile,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterBoolean,
    QgsProcessingException,
    QgsProcessingContext,
    QgsProcessingFeedback
)
from qgis.PyQt.QtCore import QCoreApplication


class CreateCOGAlgorithm(QgsProcessingAlgorithm):
    """Create Cloud Optimized GeoTIFF from raster tiles."""

    INPUT_FOLDER = 'INPUT_FOLDER'
    INPUT_EPSG = 'INPUT_EPSG'
    INPUT_NODATA = 'INPUT_NODATA'
    INPUT_USE_NODATA = 'INPUT_USE_NODATA'
    OUTPUT_COG = 'OUTPUT_COG'

    def __init__(self):
        """Initialize algorithm."""
        super().__init__()

    def tr(self, string):
        """Get translation for a string."""
        return QCoreApplication.translate(self.__class__.__name__, string)

    def createInstance(self):
        """Create a new instance of the algorithm."""
        return CreateCOGAlgorithm()

    def name(self):
        """Return algorithm name."""
        return 'create_cog'

    def displayName(self):
        """Return algorithm display name."""
        return self.tr('Create Cloud Optimized GeoTIFF (COG)')

    def group(self):
        """Return algorithm group."""
        return self.tr('Processing')

    def groupId(self):
        """Return algorithm group ID."""
        return 'processing'

    def shortHelpString(self):
        """Return algorithm help string."""
        return self.tr('''Creates a Cloud Optimized GeoTIFF (COG) from a folder of raster tiles.

The algorithm:
1. Builds a virtual raster (VRT) from all tiles in the input folder
2. Warps the VRT to the specified EPSG code
3. Adds overviews for efficient access
4. Converts to COG format with LZW compression

The output is a single, optimized raster file suitable for cloud storage and efficient web access.''')

    def initAlgorithm(self, config=None):
        """Initialize algorithm parameters."""
        self.addParameter(
            QgsProcessingParameterFile(
                self.INPUT_FOLDER,
                self.tr('Input Folder with Tiles'),
                behavior=QgsProcessingParameterFile.Folder
            )
        )

        self.addParameter(
            QgsProcessingParameterNumber(
                self.INPUT_EPSG,
                self.tr('Output EPSG Code'),
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=32633,
                minValue=1000,
                maxValue=99999
            )
        )

        self.addParameter(
            QgsProcessingParameterBoolean(
                self.INPUT_USE_NODATA,
                self.tr('Set NoData Value'),
                defaultValue=False
            )
        )

        self.addParameter(
            QgsProcessingParameterNumber(
                self.INPUT_NODATA,
                self.tr('NoData Value'),
                type=QgsProcessingParameterNumber.Double,
                defaultValue=0,
                optional=True
            )
        )

        self.addParameter(
            QgsProcessingParameterFileDestination(
                self.OUTPUT_COG,
                self.tr('Output COG File'),
                fileFilter=self.tr('GeoTIFF files (*.tif *.tiff)')
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        """Execute algorithm."""
        input_folder = self.parameterAsString(parameters, self.INPUT_FOLDER, context)
        epsg = self.parameterAsInt(parameters, self.INPUT_EPSG, context)
        use_nodata = self.parameterAsBool(parameters, self.INPUT_USE_NODATA, context)
        nodata = self.parameterAsDouble(parameters, self.INPUT_NODATA, context) if use_nodata else None
        output_cog = self.parameterAsFileOutput(parameters, self.OUTPUT_COG, context)

        if not input_folder:
            raise QgsProcessingException(self.tr('Input folder is required'))

        # Find all raster files in folder
        input_dir = Path(input_folder)
        raster_extensions = ['.tif', '.tiff', '.jp2', '.jpg', '.png']
        tile_files = []
        for ext in raster_extensions:
            tile_files.extend(input_dir.glob(f'*{ext}'))

        if not tile_files:
            raise QgsProcessingException(self.tr('No raster files found in {0}').format(input_folder))

        feedback.pushInfo(f'Found {len(tile_files)} raster tiles')

        temp_dir = tempfile.mkdtemp()
        try:
            temp_vrt = os.path.join(temp_dir, 'temp.vrt')
            temp_warped = os.path.join(temp_dir, 'temp_warped.tif')

            # Step 1: Build VRT from tiles
            feedback.setProgress(0)
            feedback.pushInfo('Building virtual raster from tiles...')
            try:
                subprocess.run(
                    ['gdalbuildvrt', temp_vrt] + [str(f) for f in tile_files],
                    check=True, capture_output=True, text=True
                )
            except subprocess.CalledProcessError as e:
                raise QgsProcessingException(self.tr('gdalbuildvrt failed: {0}').format(e.stderr))

            if feedback.isCanceled():
                return {}

            # Step 2: Warp to target EPSG
            feedback.setProgress(25)
            feedback.pushInfo(f'Warping to EPSG:{epsg}...')
            try:
                subprocess.run(
                    ['gdalwarp', '-t_srs', f'EPSG:{epsg}', '-multi', temp_vrt, temp_warped],
                    check=True, capture_output=True, text=True
                )
            except subprocess.CalledProcessError as e:
                raise QgsProcessingException(self.tr('gdalwarp failed: {0}').format(e.stderr))

            if feedback.isCanceled():
                return {}

            # Step 3: Add overviews
            feedback.setProgress(50)
            feedback.pushInfo('Adding overviews...')
            try:
                subprocess.run(
                    ['gdaladdo', '-r', 'nearest', temp_warped, '2', '4', '8', '16', '32'],
                    check=True, capture_output=True, text=True
                )
            except subprocess.CalledProcessError as e:
                feedback.pushInfo(f'Warning: gdaladdo failed (non-critical): {e.stderr}')

            if feedback.isCanceled():
                return {}

            # Step 4: Convert to COG
            feedback.setProgress(75)
            feedback.pushInfo('Converting to Cloud Optimized GeoTIFF...')
            cog_cmd = [
                'gdal_translate', '-of', 'COG',
                '-co', 'COMPRESS=LZW',
                '-co', 'OVERVIEWS=IGNORE_EXISTING',
            ]
            if nodata is not None:
                cog_cmd += ['-a_nodata', str(nodata)]
            cog_cmd += [temp_warped, output_cog]

            try:
                subprocess.run(cog_cmd, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as e:
                raise QgsProcessingException(self.tr('gdal_translate (COG) failed: {0}').format(e.stderr))

            feedback.setProgress(100)
            feedback.pushInfo(f'\nSuccessfully created COG: {output_cog}')

            return {self.OUTPUT_COG: output_cog}

        except QgsProcessingException:
            raise
        except Exception as e:
            raise QgsProcessingException(self.tr('Failed to create COG: {0}').format(str(e)))
        finally:
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                feedback.pushInfo(f'Warning: Could not remove temporary files: {e}')
