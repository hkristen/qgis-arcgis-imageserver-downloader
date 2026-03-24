# ArcGIS ImageServer Downloader for QGIS

A QGIS plugin for downloading raster tiles from ArcGIS ImageServer REST services and creating Cloud Optimized GeoTIFFs (COGs).

## Features

- Works with any ArcGIS ImageServer endpoint
- Pre-configured presets for quick access (includes GIS Steiermark)
- Interactive GUI with dockable widget
- Batch processing support via QGIS Processing framework
- Background downloads with progress tracking
- Multiple bbox selection methods (draw on canvas, from layer, manual coords)
- Automatic Cloud Optimized GeoTIFF generation with compression
- Zero external dependencies - uses only QGIS and Qt libraries
- Compatible with QGIS 3.40+ (Qt5) and QGIS 4.0+ (Qt6)
- Internationalization support (English, German)

## Quick Start

### Installation

1. Download or package the plugin directory as a ZIP file:
   ```bash
   cd qgis-arcgis-imageserver-downloader
   zip -r arcgis_imageserver_downloader.zip arcgis_imageserver_downloader/
   ```

2. In QGIS, go to **Plugins > Manage and Install Plugins**

3. Select **Install from ZIP** tab

4. Browse to the ZIP file and click **Install Plugin**

### Manual Installation

Copy the `arcgis_imageserver_downloader` folder to your QGIS plugins directory:
- **Linux:** `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
- **Windows:** `C:\Users\<username>\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\`
- **macOS:** `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`

Restart QGIS and enable the plugin in **Plugins > Manage and Install Plugins**.

### First Download

1. **Open Plugin:** **Raster > ArcGIS ImageServer Downloader**

2. **Select Server:** Choose "GIS Steiermark" from the dropdown

3. **Select Service:** Type "2019" in the filter and select "Flug_2019_2021_RGB"

4. **Define Area:** Click "Draw on canvas" and draw a rectangle on the map

5. **Configure Output:**
   - Click [...] to choose output folder
   - Select output format (e.g., "Merge compressed")
   - Check "Add to canvas"

6. **Download:** Click the Download button and wait for completion

## Using the GUI

1. Open the plugin from **Raster > ArcGIS ImageServer Downloader**

2. Select a server from the dropdown (or add a custom server with the + button)

3. Browse available services in the table (use filter to search)

4. Select a service from the list

5. Define a bounding box using one of three methods:
   - **Draw on canvas** - Click and draw a rectangle on the map
   - **From layer** - Use the extent of the active layer
   - **Manual coords** - Enter coordinates directly

6. Configure output settings:
   - Output CRS (EPSG code)
   - Output format: Tiles only, Merge uncompressed, or Merge compressed (recommended)
   - Add to canvas (automatically load result)

7. Choose output directory

8. Click **Download**

## Using Processing Algorithms

The plugin provides three Processing algorithms available in the Processing Toolbox under "ArcGIS ImageServer":

### 1. Discover ImageServer Services

Discovers available services from an ArcGIS REST endpoint.

**Parameters:**
- Server URL (e.g., `https://gis.stmk.gv.at/image/rest/services`)
- Output JSON file path

**Output:** JSON file with service metadata

### 2. Download Raster Tiles

Downloads raster tiles from an ImageServer service.

**Parameters:**
- Server URL
- Service Name (e.g., `OGD_DOP/Flug_2019_2021_RGB`)
- Bounding Box Layer (optional)
- Output EPSG Code
- Maximum Retry Attempts
- Output Folder

**Output:** Folder containing raster tiles and metadata JSON files

### 3. Create Cloud Optimized GeoTIFF (COG)

Creates a COG from a folder of raster tiles.

**Parameters:**
- Input Folder (containing tiles)
- Output EPSG Code
- Set NoData Value (optional)
- NoData Value
- Output COG File

**Output:** Cloud Optimized GeoTIFF file

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

2. Enter:
   - Name (display name)
   - URL (ArcGIS REST services endpoint)

3. Click OK

Custom servers are saved in your QGIS settings directory as `arcgis_imageserver_custom_servers.json`.

## Common Workflows

### Download Orthophoto for Study Area

1. Load your study area shapefile/geopackage
2. Open plugin: **Raster > ArcGIS ImageServer Downloader**
3. Server: "GIS Steiermark"
4. Service: Browse and select orthophoto service
5. Bbox: Select "From layer extent" and choose your study area layer
6. Output CRS: Match your project CRS (e.g., EPSG:32633)
7. Click **Download**

### Batch Processing Multiple Services

Use QGIS Model Builder:
1. **Processing > Graphical Modeler**
2. Add "Download Raster Tiles" algorithm multiple times
3. Change service name for each
4. Use same bbox layer for all
5. Run model

## GIS Steiermark Preset

The plugin includes a pre-configured preset for GIS Steiermark (Styria, Austria):

- **URL:** `https://gis.stmk.gv.at/image/rest/services`
- **Default EPSG:** 32633 (UTM Zone 33N)
- **Available Services:**
  - **OGD_DOP:** Orthophotos (various years)
  - **OGD_Hoehen:** Elevation data

## Requirements

- **QGIS 3.40+** (Qt5-based) or **QGIS 4.0+** (Qt6-based)
- GDAL with COG driver support (GDAL 3.1+)

The plugin uses QGIS's Qt compatibility layer and works seamlessly with both Qt5 and Qt6.

## Troubleshooting

### Plugin doesn't load

- Check QGIS Python console for error messages
- Verify QGIS version is 3.40 or higher
- Ensure plugin is installed in correct directory

### Services not loading

- Verify server URL is accessible
- Check network connection
- Some servers may require authentication (not currently supported)

### COG creation fails

- Ensure GDAL version supports COG driver (`gdalinfo --format COG`)
- Check that input tiles are valid raster files
- Verify sufficient disk space for temporary files

### Download progress stuck

- Some tiles may be very large - be patient
- Check QGIS message log for detailed progress
- Click Cancel if needed, then retry with smaller bbox

### Layer not added to canvas

- Check output file exists
- Verify CRS is valid
- Try adding manually from Layer menu

## Tips & Tricks

### Performance
- Use smaller bounding boxes for faster downloads
- Select "Tiles only" to skip merging for faster results
- "Merge compressed" adds LZW compression, tiling, and overviews for best file size and performance

### CRS Selection
- Match your project CRS for seamless integration
- EPSG:32633 is default for GIS Steiermark (UTM Zone 33N)
- CRS transformation is automatic

### Progress Monitoring
- Watch progress bar for percentage
- Read status messages for details
- Check QGIS message log for verbose output

### Cancellation
- Click **Cancel** during download to stop
- Partially downloaded tiles are kept
- Can resume by downloading again (skips existing)

## License

GNU General Public License v2.0

## Support

For issues and feature requests, please use the [GitHub issue tracker](https://github.com/hkristen/qgis-arcgis-imageserver-downloader/issues).
