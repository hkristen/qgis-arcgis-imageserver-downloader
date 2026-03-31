# ArcGIS ImageServer Downloader for QGIS

[![QGIS Plugin](https://img.shields.io/badge/QGIS-Plugin-green.svg)](https://plugins.qgis.org/plugins/arcgis_imageserver_downloader)
[![Version](https://img.shields.io/badge/version-0.1.2-blue.svg)](https://plugins.qgis.org/plugins/arcgis_imageserver_downloader)
[![License](https://img.shields.io/badge/License-GPL%20v2-blue.svg)](https://www.gnu.org/licenses/old-licenses/gpl-2.0.html)

A QGIS plugin for downloading raster tiles from ArcGIS ImageServer REST services and creating Cloud Optimized GeoTIFFs (COGs).

## Features

- Download very large areas that would be impossible to export directly via the ArcGIS REST service
- Tiles are fetched at original spatial resolution — no resampling or processing by WMS/tile services
- Pre-configured preset for GIS Steiermark; add custom servers via the UI
- Batch processing support via QGIS Processing framework
- Background downloads with progress tracking and cancellation
- Multiple bbox selection methods: draw on canvas, from layer extent, or manual coordinates
- Automatic Cloud Optimized GeoTIFF generation with selectable compression
- Zero external dependencies — uses only QGIS and Qt libraries
- Compatible with QGIS 3.40+ (Qt5) and QGIS 4.0+ (Qt6)
- Internationalization support (English, German)

> **Note:** The plugin is designed around the ArcGIS ImageServer REST API and is currently only tested against GIS Steiermark endpoints. Compatibility with other ArcGIS ImageServer deployments is likely but not yet verified.

## Quick Start

### Installation

The easiest way to install is via the official QGIS Plugin Repository:

1. In QGIS: **Plugins > Manage and Install Plugins**
2. Search for **ArcGIS ImageServer Downloader**
3. Click **Install Plugin**

Alternatively, install from ZIP:

1. Download the latest release ZIP from the [GitHub repository](https://github.com/hkristen/qgis-arcgis-imageserver-downloader/releases)
2. In QGIS: **Plugins > Manage and Install Plugins > Install from ZIP**
3. Browse to the ZIP file and click **Install Plugin**

### Manual Installation

Copy the `arcgis_imageserver_downloader` folder to your QGIS plugins directory:
- **Linux:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
- **Windows:** `C:\Users\<username>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\`
- **macOS:** `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`

Restart QGIS and enable the plugin in **Plugins > Manage and Install Plugins**.

## Using the GUI

1. Open the plugin from **Raster > ArcGIS ImageServer Downloader**
2. Select a server from the dropdown (or add a custom server with the **+** button)
3. Browse available services in the table — use the filter to search
4. Select a service
5. Define a bounding box:
   - **Draw on canvas** — click and drag a rectangle on the map
   - **From layer extent** — use the extent of an existing layer
   - **Manual coords** — enter coordinates directly
6. Set output CRS (EPSG code), output format, and output directory
7. Optionally check **Add to canvas** to load the result automatically
8. Click **Download**

### Output Formats

- **Tiles only** — save raw tiles without merging (fastest)
- **Merge uncompressed** — merge tiles into a single GeoTIFF
- **Merge compressed** — merge with LZW compression, tiling, and overviews (recommended)

## Using Processing Algorithms

Available in the Processing Toolbox under **ArcGIS ImageServer**:

### 1. Discover ImageServer Services

Discovers available services from an ArcGIS REST endpoint.

**Parameters:**
- Server URL (e.g., `https://gis.stmk.gv.at/image/rest/services`)
- Output JSON file path

### 2. Download Raster Tiles

Downloads raster tiles from an ImageServer service.

**Parameters:**
- Server URL
- Service Name (e.g., `OGD_DOP/Flug_2019_2021_RGB`)
- Bounding Box Layer (optional)
- Output EPSG Code
- Maximum Retry Attempts
- Output Folder

### 3. Create Cloud Optimized GeoTIFF (COG)

Creates a COG from a folder of raster tiles.

**Parameters:**
- Input Folder (containing tiles)
- Output EPSG Code
- Set NoData Value (optional)
- NoData Value
- Output COG File

### Scripting Example

```python
# In QGIS Python console:

# Discover services
processing.run("arcgis_imageserver:discover_services", {
    'INPUT_URL': 'https://gis.stmk.gv.at/image/rest/services',
    'OUTPUT_JSON': '/tmp/services.json'
})

# Download tiles using a layer for bbox
processing.run("arcgis_imageserver:download_tiles", {
    'INPUT_URL': 'https://gis.stmk.gv.at/image/rest/services',
    'INPUT_SERVICE': 'OGD_DOP/Flug_2019_2021_RGB',
    'INPUT_BBOX_LAYER': 'my_study_area_layer',
    'INPUT_EPSG': 32633,
    'OUTPUT_FOLDER': '/tmp/tiles'
})

# Create COG from tiles
processing.run("arcgis_imageserver:create_cog", {
    'INPUT_FOLDER': '/tmp/tiles',
    'INPUT_EPSG': 32633,
    'OUTPUT_COG': '/tmp/output.tif'
})

# Add to canvas
iface.addRasterLayer('/tmp/output.tif', 'Orthophoto 2019-2021')
```

## Adding Custom Servers

1. Click the **+** button next to the server dropdown
2. Enter a display name and the ArcGIS REST services endpoint URL
3. Click OK

Custom servers are saved in your QGIS settings directory as `arcgis_imageserver_custom_servers.json`.

## GIS Steiermark Preset

- **URL:** `https://gis.stmk.gv.at/image/rest/services`
- **Default EPSG:** 32633 (UTM Zone 33N)
- **Available services include:**
  - **OGD_DOP:** Orthophotos (various years)
  - **OGD_Hoehen:** Elevation data

## Requirements

- **QGIS 3.40+** (Qt5) or **QGIS 4.0+** (Qt6)
- GDAL 3.1+ with COG driver support

## Troubleshooting

**Plugin doesn't load** — Check QGIS Python console for errors; verify QGIS 3.40+.

**Services not loading** — Verify the server URL is accessible. Authentication is not currently supported.

**COG creation fails** — Check GDAL version (`gdalinfo --format COG`); verify disk space.

**Download progress stuck** — Large areas take time; check QGIS message log. Click Cancel and retry with a smaller bbox if needed.

**Layer not added to canvas** — Verify the output file exists and CRS is valid; try adding manually via the Layer menu.

## Tips

- Use **Merge compressed** for the best balance of file size and performance
- Match output CRS to your project CRS for seamless integration
- Cancelled downloads retain partial tiles; re-running skips already-downloaded tiles
- Use the Processing framework or Model Builder to automate multi-service batch downloads

## Acknowledgments

Built by [Harald Kristen](https://hkristen.at) with [Claude](https://claude.ai) as an AI pair-programmer. The plugin architecture, GUI, and Processing algorithms were developed iteratively with human-in-the-loop feedback and review.

## License

GNU General Public License v2.0

## Support

For issues and feature requests, please use the [GitHub issue tracker](https://github.com/hkristen/qgis-arcgis-imageserver-downloader/issues).
