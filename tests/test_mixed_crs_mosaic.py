"""
Regression test: gdalbuildvrt silently drops tiles with a different CRS than the
first file. Fix is to pass all tile paths directly to gdalwarp.
"""
import subprocess

import numpy as np
import pytest

try:
    from osgeo import gdal, osr
    gdal.UseExceptions()
except ImportError:
    pytest.skip("GDAL Python bindings not available", allow_module_level=True)


# Distinct fill values per tile so we can tell them apart in the output
FILL_31255 = 100
FILL_31256 = 200


def _create_tile(path: str, epsg: int, x_origin: float, y_origin: float,
                 fill: int, pixel_size: float = 100.0, size: int = 10) -> None:
    driver = gdal.GetDriverByName("GTiff")
    ds = driver.Create(path, size, size, 1, gdal.GDT_Byte)
    ds.SetGeoTransform([x_origin, pixel_size, 0, y_origin, 0, -pixel_size])
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(epsg)
    ds.SetProjection(srs.ExportToWkt())
    ds.GetRasterBand(1).Fill(fill)
    ds.FlushCache()
    ds = None


def _pixel_values(tif_path: str) -> np.ndarray:
    ds = gdal.Open(tif_path)
    arr = ds.GetRasterBand(1).ReadAsArray()
    ds = None
    return arr


@pytest.fixture()
def two_tiles(tmp_path):
    t1 = str(tmp_path / "tile_31255.tif")
    t2 = str(tmp_path / "tile_31256.tif")
    _create_tile(t1, epsg=31255, x_origin=460000, y_origin=5280100, fill=FILL_31255)
    _create_tile(t2, epsg=31256, x_origin=630000, y_origin=5280100, fill=FILL_31256)
    return t1, t2


def test_gdalbuildvrt_reproduces_bug(two_tiles, tmp_path):
    """gdalbuildvrt + gdalwarp drops one tile — output contains only one fill value."""
    t1, t2 = two_tiles
    vrt = str(tmp_path / "mosaic.vrt")
    out = str(tmp_path / "buggy.tif")

    subprocess.run(["gdalbuildvrt", vrt, t1, t2], check=True, capture_output=True)
    subprocess.run(
        ["gdalwarp", "-t_srs", "EPSG:32633", "-multi", vrt, out],
        check=True, capture_output=True,
    )

    pixels = _pixel_values(out)
    has_31255 = (pixels == FILL_31255).any()
    has_31256 = (pixels == FILL_31256).any()

    assert not (has_31255 and has_31256), (
        "Both tiles found — gdalbuildvrt may have started handling mixed CRS upstream."
    )


def test_gdalwarp_direct_fixes_mixed_crs(two_tiles, tmp_path):
    """gdalwarp on all tile paths directly includes pixel data from both CRS zones."""
    t1, t2 = two_tiles
    out = str(tmp_path / "fixed.tif")

    subprocess.run(
        ["gdalwarp", "-t_srs", "EPSG:32633", "-multi", t1, t2, out],
        check=True, capture_output=True,
    )

    pixels = _pixel_values(out)
    assert (pixels == FILL_31255).any(), "Tile from EPSG:31255 missing from output"
    assert (pixels == FILL_31256).any(), "Tile from EPSG:31256 missing from output"
