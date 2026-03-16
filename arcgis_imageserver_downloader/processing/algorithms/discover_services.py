"""
Processing algorithm to discover ArcGIS ImageServer services
"""
from qgis.core import (
    QgsProcessingAlgorithm,
    QgsProcessingParameterString,
    QgsProcessingParameterFileDestination,
    QgsProcessingException,
    QgsProcessingContext,
    QgsProcessingFeedback
)
from qgis.PyQt.QtCore import QCoreApplication
import json
from pathlib import Path

from ...core.arcgis_client import ArcGISClient


class DiscoverServicesAlgorithm(QgsProcessingAlgorithm):
    """Discover services from ArcGIS ImageServer endpoint."""

    INPUT_URL = 'INPUT_URL'
    OUTPUT_JSON = 'OUTPUT_JSON'

    def __init__(self):
        super().__init__()

    def tr(self, string):
        return QCoreApplication.translate(self.__class__.__name__, string)

    def createInstance(self):
        return DiscoverServicesAlgorithm()

    def name(self):
        return 'discover_services'

    def displayName(self):
        return self.tr('Discover ImageServer Services')

    def group(self):
        return self.tr('Service Discovery')

    def groupId(self):
        return 'discovery'

    def shortHelpString(self):
        """Return algorithm help string."""
        return self.tr('''Discovers available ImageServer services from an ArcGIS REST endpoint.

Returns a JSON file with service metadata including:
- Service name and category
- Service type
- Year information (if available in name)

Example URL: https://gis.stmk.gv.at/image/rest/services''')

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
            QgsProcessingParameterFileDestination(
                self.OUTPUT_JSON,
                self.tr('Output JSON file'),
                fileFilter=self.tr('JSON files (*.json)')
            )
        )

    def processAlgorithm(self, parameters, context, feedback):
        """Execute algorithm."""
        url = self.parameterAsString(parameters, self.INPUT_URL, context)
        output_path = self.parameterAsFileOutput(parameters, self.OUTPUT_JSON, context)

        if not url:
            raise QgsProcessingException(self.tr('Server URL is required'))

        feedback.pushInfo(f'Discovering services from: {url}')

        try:
            client = ArcGISClient()
            services = client.get_services(url)

            feedback.pushInfo(f'Found {len(services)} services')

            # Save to JSON
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, 'w') as f:
                json.dump(services, f, indent=2)

            feedback.pushInfo(f'Services saved to: {output_path}')

            return {self.OUTPUT_JSON: output_path}

        except Exception as e:
            raise QgsProcessingException(self.tr('Failed to discover services: {0}').format(str(e)))
