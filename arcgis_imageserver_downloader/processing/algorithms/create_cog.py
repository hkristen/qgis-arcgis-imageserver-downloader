"""
Processing algorithm to create Cloud Optimized GeoTIFF from tiles
"""
from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterFile,
    QgsProcessingParameterFileDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterBoolean,
    QgsProcessingException,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsProcessingMultiStepFeedback
)
from qgis.PyQt.QtCore import QCoreApplication
from qgis import processing
from pathlib import Path
import tempfile
import os


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
3. Creates a compressed GeoTIFF with overviews
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

        # Use multi-step feedback for progress
        multi_feedback = QgsProcessingMultiStepFeedback(4, feedback)

        try:
            # Create temporary directory for intermediate files
            temp_dir = tempfile.mkdtemp()
            temp_vrt = os.path.join(temp_dir, 'temp.vrt')
            temp_warped_vrt = os.path.join(temp_dir, 'temp_warped.vrt')
            temp_tif = os.path.join(temp_dir, 'temp.tif')

            # Step 1: Build VRT from tiles
            multi_feedback.setCurrentStep(0)
            feedback.pushInfo('Building virtual raster from tiles...')

            vrt_result = processing.run(
                'gdal:buildvirtualraster',
                {
                    'INPUT': [str(f) for f in tile_files],
                    'RESOLUTION': 0,  # Use highest resolution
                    'SEPARATE': False,
                    'OUTPUT': temp_vrt
                },
                context=context,
                feedback=multi_feedback
            )

            if multi_feedback.isCanceled():
                return {}

            # Step 2: Warp to target EPSG
            multi_feedback.setCurrentStep(1)
            feedback.pushInfo(f'Warping to EPSG:{epsg}...')

            warp_result = processing.run(
                'gdal:warpreproject',
                {
                    'INPUT': temp_vrt,
                    'SOURCE_CRS': None,  # Use source CRS
                    'TARGET_CRS': f'EPSG:{epsg}',
                    'RESAMPLING': 0,  # Nearest neighbor
                    'DATA_TYPE': 0,  # Use input layer data type
                    'OPTIONS': '',
                    'MULTITHREADING': True,
                    'OUTPUT': temp_warped_vrt
                },
                context=context,
                feedback=multi_feedback
            )

            if multi_feedback.isCanceled():
                return {}

            # Step 3: Convert to compressed GeoTIFF with overviews
            multi_feedback.setCurrentStep(2)
            feedback.pushInfo('Creating compressed GeoTIFF...')

            extra_args = f'-a_nodata {nodata}' if nodata is not None else ''

            translate_result = processing.run(
                'gdal:translate',
                {
                    'INPUT': temp_warped_vrt,
                    'OPTIONS': 'COMPRESS=LZW|TILED=YES',
                    'EXTRA': extra_args,
                    'DATA_TYPE': 0,  # Use input layer data type
                    'OUTPUT': temp_tif
                },
                context=context,
                feedback=multi_feedback
            )

            if multi_feedback.isCanceled():
                return {}

            # Add overviews to the GeoTIFF
            feedback.pushInfo('Adding overviews...')
            processing.run(
                'gdal:overviews',
                {
                    'INPUT': temp_tif,
                    'LEVELS': '2 4 8 16 32',
                    'RESAMPLING': 0,  # Nearest neighbor
                    'FORMAT': 0  # Internal (GeoTIFF)
                },
                context=context,
                feedback=multi_feedback
            )

            # Step 4: Convert to COG
            multi_feedback.setCurrentStep(3)
            feedback.pushInfo('Converting to Cloud Optimized GeoTIFF...')

            cog_result = processing.run(
                'gdal:translate',
                {
                    'INPUT': temp_tif,
                    'OPTIONS': 'COMPRESS=LZW|OVERVIEWS=IGNORE_EXISTING',
                    'EXTRA': '-of COG',
                    'DATA_TYPE': 0,  # Use input layer data type
                    'OUTPUT': output_cog
                },
                context=context,
                feedback=multi_feedback
            )

            if multi_feedback.isCanceled():
                return {}

            # Cleanup temporary files
            try:
                import shutil
                shutil.rmtree(temp_dir)
            except Exception as e:
                feedback.pushInfo(f'Warning: Could not remove temporary files: {e}')

            feedback.pushInfo(f'\nSuccessfully created COG: {output_cog}')

            return {self.OUTPUT_COG: output_cog}

        except Exception as e:
            raise QgsProcessingException(self.tr('Failed to create COG: {0}').format(str(e)))
