"""
ArcGIS REST API client using urllib
"""
import json
import re
import urllib.request
import urllib.parse
import urllib.error
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from qgis.core import (
    QgsMessageLog,
    Qgis
)


class ArcGISClient:
    """Client for ArcGIS REST API using urllib."""

    def __init__(self):
        """Initialize the ArcGIS client."""
        pass

    def _log(self, message: str, level: Qgis.MessageLevel = Qgis.Info):
        """Log message to QGIS message log."""
        QgsMessageLog.logMessage(message, 'ArcGIS ImageServer Downloader', level)

    def _make_request(
        self,
        url: str,
        params: Optional[Dict] = None,
        max_retry: int = 3
    ) -> Dict:
        """Make a network request and return JSON response.

        Args:
            url: URL to request
            params: Query parameters
            max_retry: Maximum number of retry attempts

        Returns:
            JSON response as dictionary

        Raises:
            RuntimeError: If request fails after retries
        """
        if params:
            full_url = url + '?' + urllib.parse.urlencode(params)
        else:
            full_url = url

        req = urllib.request.Request(
            full_url,
            headers={'User-Agent': 'QGIS ArcGIS ImageServer Downloader'}
        )

        last_error = None
        for attempt in range(max_retry):
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    content = response.read()
                    try:
                        return json.loads(content.decode('utf-8'))
                    except json.JSONDecodeError as e:
                        raise RuntimeError(f"Failed to parse JSON response: {e}")
            except urllib.error.URLError as e:
                last_error = e
                if attempt < max_retry - 1:
                    self._log(f"Request failed (attempt {attempt + 1}/{max_retry}), retrying...", Qgis.Warning)

        raise RuntimeError(f"Network request failed after {max_retry} attempts: {last_error}")

    def _download_file(
        self,
        url: str,
        params: Optional[Dict],
        output_path: Path,
        max_retry: int = 3
    ) -> bool:
        """Download a file from URL to output path.

        Args:
            url: URL to download from
            params: Query parameters
            output_path: Path to save file
            max_retry: Maximum retry attempts

        Returns:
            True if successful

        Raises:
            RuntimeError: If download fails
        """
        if params:
            full_url = url + '?' + urllib.parse.urlencode(params)
        else:
            full_url = url

        req = urllib.request.Request(
            full_url,
            headers={'User-Agent': 'QGIS ArcGIS ImageServer Downloader'}
        )

        last_error = None
        for attempt in range(max_retry):
            req = urllib.request.Request(
                full_url,
                headers={'User-Agent': 'QGIS ArcGIS ImageServer Downloader'}
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(output_path, 'wb') as f:
                        while True:
                            chunk = response.read(65536)
                            if not chunk:
                                break
                            f.write(chunk)
                    return True
            except urllib.error.URLError as e:
                last_error = e
                if attempt < max_retry - 1:
                    self._log(f"Download failed (attempt {attempt + 1}/{max_retry}), retrying...", Qgis.Warning)

        raise RuntimeError(f"File download failed after {max_retry} attempts: {last_error}")

    def get_services(self, base_url: str) -> List[Dict]:
        """Fetch services from ArcGIS REST endpoint.

        Args:
            base_url: Base URL of the ArcGIS REST endpoint

        Returns:
            List of service dictionaries with parsed metadata
        """
        params = {'f': 'json'}
        data = self._make_request(base_url, params)

        services = data.get('services', [])
        folders = data.get('folders', [])

        # If there are folders, recursively fetch services from each folder
        if folders:
            self._log(f'Found {len(folders)} folders, discovering services recursively...')
            for folder in folders:
                # Skip system folders
                if folder in ['System', 'Utilities']:
                    continue

                folder_url = f"{base_url.rstrip('/')}/{folder}"
                try:
                    folder_data = self._make_request(folder_url, params)
                    folder_services = folder_data.get('services', [])
                    services.extend(folder_services)
                    self._log(f'Found {len(folder_services)} services in folder: {folder}')
                except Exception as e:
                    self._log(f'Failed to fetch services from folder {folder}: {e}', Qgis.Warning)

        # Filter to only ImageServer services
        imageserver_services = [s for s in services if s.get('type', '') == 'ImageServer']

        if not imageserver_services:
            self._log('No ImageServer services found')
            return []

        # Parse service information
        parsed_services = []
        for service in imageserver_services:
            name = service.get('name', '')

            parsed = {
                'name': name,
                'type': service.get('type', ''),
                'category': '',
                'service_name': '',
                'year': None
            }

            # Split name into category and service_name if it contains '/'
            if '/' in name:
                parts = name.split('/', 1)
                parsed['category'] = parts[0]
                parsed['service_name'] = parts[1]
            else:
                parsed['service_name'] = name

            # Extract year from service name (4 digits)
            year_match = re.search(r'(\d{4})', parsed['service_name'])
            if year_match:
                parsed['year'] = year_match.group(1)

            parsed_services.append(parsed)

        # Sort by category and service_name
        parsed_services.sort(key=lambda x: (x['category'], x['service_name']))

        self._log(f'Total services discovered: {len(parsed_services)}')
        return parsed_services

    def query_tiles(
        self,
        service_url: str,
        service_name: str,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        in_sr: int = 32633,
        out_sr: int = 32633
    ) -> List[int]:
        """Query tile IDs from ImageServer that intersect bounding box.

        Args:
            service_url: Base URL of the service
            service_name: Name of the service
            bbox: Bounding box as (minx, miny, maxx, maxy), None for all tiles
            in_sr: Input spatial reference system EPSG code
            out_sr: Output spatial reference system EPSG code

        Returns:
            List of tile object IDs

        Raises:
            RuntimeError: If no tiles found or error occurs
        """
        query_url = f"{service_url}/{service_name}/ImageServer/query"

        params = {
            'where': '1=1',
            'returnGeometry': 'false',
            'returnIdsOnly': 'true',
            'f': 'json'
        }

        if bbox:
            params['geometry'] = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
            params['geometryType'] = 'esriGeometryEnvelope'
            params['inSR'] = in_sr
            params['spatialRel'] = 'esriSpatialRelIntersects'
            params['outSR'] = out_sr

        data = self._make_request(query_url, params)

        if 'error' in data:
            error = data['error']
            raise RuntimeError(f"{error.get('code', 'Unknown')}: {error.get('message', 'Unknown error')}")

        object_ids = data.get('objectIds', [])
        if not object_ids:
            raise RuntimeError("No tiles found matching the query parameters")

        return object_ids

    def get_tile_info(
        self,
        service_url: str,
        service_name: str,
        tile_id: int
    ) -> Dict:
        """Get information about a specific tile.

        Args:
            service_url: Base URL of the service
            service_name: Name of the service
            tile_id: Tile object ID

        Returns:
            Dictionary with tile information including file path

        Raises:
            RuntimeError: If error occurs
        """
        download_url = f"{service_url}/{service_name}/ImageServer/download"
        params = {
            'rasterIds': str(tile_id),
            'f': 'json'
        }

        data = self._make_request(download_url, params)

        if 'error' in data:
            error = data['error']
            details = error.get('details', [''])[0] if error.get('details') else ''
            raise RuntimeError(f"{error.get('code', 'Unknown')}: {error.get('message', 'Unknown error')} - {details}")

        return data

    def download_tile(
        self,
        service_url: str,
        service_name: str,
        tile_id: int,
        tile_filepath: str,
        output_dir: Path,
        max_retry: int = 5
    ) -> Path:
        """Download a single raster tile.

        Args:
            service_url: Base URL of the service
            service_name: Name of the service
            tile_id: Tile object ID
            tile_filepath: Remote file path from tile info
            output_dir: Directory to save tile
            max_retry: Maximum retry attempts

        Returns:
            Path to downloaded tile file

        Raises:
            RuntimeError: If download fails
        """
        file_endpoint_url = f"{service_url}/{service_name}/ImageServer/file"
        filename = tile_filepath.split("\\")[-1]

        # Skip overview tiles
        if filename.startswith("Ov_"):
            raise ValueError(f"Skipping overview tile: {filename}")

        output_path = output_dir / filename

        # Check if already downloaded
        if output_path.exists():
            return output_path

        file_params = {
            'id': tile_filepath,
            'rasterId': str(tile_id)
        }

        self._download_file(file_endpoint_url, file_params, output_path, max_retry)
        return output_path

    def get_service_metadata(
        self,
        service_url: str,
        service_name: str,
        output_path: Optional[Path] = None
    ) -> Dict:
        """Get service metadata from ImageServer.

        Args:
            service_url: Base URL of the service
            service_name: Name of the service
            output_path: Optional path to save metadata JSON

        Returns:
            Service metadata dictionary
        """
        image_server_url = f"{service_url}/{service_name}/ImageServer"
        params = {'f': 'pjson'}

        metadata = self._make_request(image_server_url, params)

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                json.dump(metadata, f, indent=2)

        return metadata

    def get_tile_metadata(
        self,
        service_url: str,
        service_name: str,
        tile_id: int,
        output_path: Optional[Path] = None
    ) -> Dict:
        """Get metadata for a specific tile.

        Args:
            service_url: Base URL of the service
            service_name: Name of the service
            tile_id: Tile object ID
            output_path: Optional path to save metadata JSON

        Returns:
            Tile metadata dictionary
        """
        metadata_url = f"{service_url}/{service_name}/ImageServer/{tile_id}"
        params = {'f': 'pjson'}

        metadata = self._make_request(metadata_url, params)

        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                json.dump(metadata, f, indent=2)

        return metadata
