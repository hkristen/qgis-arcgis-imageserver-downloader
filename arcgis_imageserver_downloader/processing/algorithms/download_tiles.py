"""
Processing algorithm to download raster tiles from ArcGIS ImageServer
"""
from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterString,
    QgsProcessingParameterVectorLayer,
    QgsProcessingParameterFolderDestination,
    QgsProcessingParameterNumber,
    QgsProcessingParameterBoolean,
    QgsProcessingException,
    QgsProcessingContext,
    QgsProcessingFeedback,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsProject
)
from qgis.PyQt.QtCore import QCoreApplication
from pathlib import Path

from ...core.arcgis_client import ArcGISClient


class DownloadTilesAlgorithm(QgsProcessingAlgorithm):
    """Download raster tiles from ArcGIS ImageServer."""

    INPUT_URL = 'INPUT_URL'
    INPUT_SERVICE = 'INPUT_SERVICE'
    INPUT_BBOX_LAYER = 'INPUT_BBOX_LAYER'
    INPUT_EPSG = 'INPUT_EPSG'
    INPUT_MAX_RETRY = 'INPUT_MAX_RETRY'
    OUTPUT_FOLDER = 'OUTPUT_FOLDER'

    def __init__(self):
        """Initialize algorithm."""
        super().__init__()

    def tr(self, string):
        """Get translation for a string."""
        return QCoreApplication.translate(self.__class__.__name__, string)

    def createInstance(self):
        """Create a new instance of the algorithm."""
        return DownloadTilesAlgorithm()

    def name(self):
        """Return algorithm name."""
        return 'download_tiles'

    def displayName(self):
        """Return algorithm display name."""
        return self.tr('Download Raster Tiles')

    def group(self):
        """Return algorithm group."""
        return self.tr('Download')

    def groupId(self):
        """Return algorithm group ID."""
        return 'download'

    def shortHelpString(self):
        """Return algorithm help string."""
        return self.tr('''Downloads raster tiles from an ArcGIS ImageServer service.

Tiles can be filtered by a bounding box layer, or all tiles will be downloaded if no layer is provided.

The tiles are saved as individual raster files in the output folder, along with metadata JSON files.

Example:
- Server URL: https://gis.stmk.gv.at/image/rest/services
- Service Name: OGD_DOP/Flug_2019_2021_RGB''')

    def initAlgorithm(self, config=None):
        """Initialize algorithm parameters."""
        self.addParameter(
            QgsProcessingParameterString(
                self.INPUT_URL,
                self.tr('Server URL'),
                defaultValue='https://gis.stmk.gv.at/image/rest/services'
            )
        )

        self.addParameter(
            QgsProcessingParameterString(
                self.INPUT_SERVICE,
                self.tr('Service Name'),
                defaultValue='',
                optional=False
            )
        )

        self.addParameter(
            QgsProcessingParameterVectorLayer(
                self.INPUT_BBOX_LAYER,
                self.tr('Bounding Box Layer (optional)'),
                optional=True
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
            QgsProcessingParameterNumber(
                self.INPUT_MAX_RETRY,
                self.tr('Maximum Retry Attempts'),
                type=QgsProcessingParameterNumber.Integer,
                defaultValue=5,
                minValue=1,
                maxValue=20
            )
        )

        self.addParameter(
            QgsProcessingParameterFolderDestination(
                self.OUTPUT_FOLDER,
                self.tr('Output Folder')
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        """Execute algorithm."""
        url = self.parameterAsString(parameters, self.INPUT_URL, context)
        service_name = self.parameterAsString(parameters, self.INPUT_SERVICE, context)
        bbox_layer = self.parameterAsVectorLayer(parameters, self.INPUT_BBOX_LAYER, context)
        epsg = self.parameterAsInt(parameters, self.INPUT_EPSG, context)
        max_retry = self.parameterAsInt(parameters, self.INPUT_MAX_RETRY, context)
        output_folder = self.parameterAsString(parameters, self.OUTPUT_FOLDER, context)

        if not url or not service_name:
            raise QgsProcessingException(self.tr('Server URL and Service Name are required'))

        output_dir = Path(output_folder)
        output_dir.mkdir(parents=True, exist_ok=True)

        feedback.pushInfo(f'Downloading tiles from: {url}/{service_name}')

        # Get bounding box if layer provided
        bbox = None
        if bbox_layer:
            extent = bbox_layer.extent()
            source_crs = bbox_layer.crs()
            target_crs = QgsCoordinateReferenceSystem(f'EPSG:{epsg}')

            # Transform bbox if needed
            if source_crs != target_crs:
                transform = QgsCoordinateTransform(source_crs, target_crs, QgsProject.instance())
                extent = transform.transformBoundingBox(extent)

            bbox = (extent.xMinimum(), extent.yMinimum(), extent.xMaximum(), extent.yMaximum())
            feedback.pushInfo(f'Using bounding box: {bbox}')

        try:
            client = ArcGISClient()

            # Query tiles
            feedback.pushInfo('Querying tiles...')
            tile_ids = client.query_tiles(url, service_name, bbox, epsg, epsg)
            feedback.pushInfo(f'Found {len(tile_ids)} tiles to download')

            # Download service metadata
            metadata_path = output_dir / f'{service_name.replace("/", "_")}.json'
            client.get_service_metadata(url, service_name, metadata_path)
            feedback.pushInfo(f'Saved service metadata')

            # Download tiles
            downloaded_files = []
            for i, tile_id in enumerate(tile_ids):
                if feedback.isCanceled():
                    break

                feedback.setProgress(int((i / len(tile_ids)) * 100))
                feedback.pushInfo(f'Processing tile {i+1}/{len(tile_ids)} (ID: {tile_id})')

                try:
                    # Get tile info
                    tile_info = client.get_tile_info(url, service_name, tile_id)
                    raster_files = tile_info.get('rasterFiles', [])
                    if not raster_files:
                        feedback.pushWarning(f'  No rasterFiles for tile {tile_id}, skipping')
                        continue
                    tile_filepath = raster_files[0]['id']
                    filename = tile_filepath.split("\\")[-1]

                    # Skip overview tiles
                    if filename.startswith("Ov_"):
                        feedback.pushInfo(f'  Skipping overview tile: {filename}')
                        continue

                    # Download tile
                    output_path = client.download_tile(
                        url, service_name, tile_id, tile_filepath, output_dir, max_retry
                    )
                    downloaded_files.append(str(output_path))
                    feedback.pushInfo(f'  Downloaded: {filename}')

                    # Download tile metadata
                    metadata_path = output_dir / f'{output_path.stem}.json'
                    client.get_tile_metadata(url, service_name, tile_id, metadata_path)

                except ValueError as e:
                    # Skip overview tiles
                    feedback.pushInfo(f'  {str(e)}')
                except Exception as e:
                    feedback.reportError(f'  Failed to download tile {tile_id}: {str(e)}')

            feedback.pushInfo(f'\nDownloaded {len(downloaded_files)} tiles to {output_folder}')

            return {self.OUTPUT_FOLDER: output_folder}

        except Exception as e:
            raise QgsProcessingException(self.tr('Failed to download tiles: {0}').format(str(e)))
