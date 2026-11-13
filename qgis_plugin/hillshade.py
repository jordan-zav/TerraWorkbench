"""Raster hillshade rendering and export for QGIS."""

from dataclasses import dataclass, replace
import json
import numpy as np
from qgis.PyQt.QtGui import QColor, QPainter
from qgis.core import (
    QgsColorRampShader, QgsHillshadeRenderer, QgsProject, QgsRasterShader,
    QgsRectangle, QgsSingleBandPseudoColorRenderer,
)

from .qgis_compat import qt_enum
from .raster_io import read_raster_source, write_geotiff


# Copied from GeoRamp georamp/plugin.py, PALETTES["classic_geophysics"].
CLASSIC = (
    "#0000ff", "#0055ff", "#007fff", "#00aaff", "#00d4ff", "#00e9ff", "#00ffff",
    "#00ffc8", "#00ff91", "#00ff3f", "#00ff31", "#00ff24", "#00ff00", "#48ff00",
    "#63ff00", "#6dff00", "#8eff00", "#b6ff00", "#c9ff00", "#f4ff00", "#ffec00",
    "#ffd500", "#ffcb00", "#ffbc00", "#ffaf00", "#ffaa00", "#ff9400", "#ff8700",
    "#ff7700", "#ff6a00", "#ff5500", "#ff3500", "#ff1500", "#ff0000", "#ff0037",
    "#ff006d", "#ff00b6", "#ff0bda", "#ff41ec", "#ff79ff", "#ff9fff",
)
DIRECTIONS = tuple(range(0, 360, 45))
EFFECT = "TerraWorkbench/hillshadeSource"
GROUP = "TerraWorkbench/hillshadeGroup"
STYLE = "TerraWorkbench/hillshadeStyle"


@dataclass(frozen=True)
class ShadeStyle:
    azimuth: float = 315
    altitude: float = 45
    intensity: float = 1
    palette: str = "classic"

    @classmethod
    def from_layer(cls, layer):
        return cls(**json.loads(layer.customProperty(STYLE, "{}")))

    def save_to_layer(self, layer):
        layer.setCustomProperty(STYLE, json.dumps(vars(self)))
        QgsProject.instance().setDirty(True)


def visual_statistics(layer):
    from ..terraworkbench_core.terrain_analysis import automatic_hillshade_z

    provider = layer.dataProvider()
    width, height = layer.width(), layer.height()
    if min(width, height) < 2:
        raise ValueError("Hillshade requires at least two rows and columns.")
    # Adjacent native cells, distributed across the grid, preserve local gradients.
    # A downsampled overview would systematically underestimate their magnitudes.
    tile_width, tile_height = min(width, 48), min(height, 48)
    extent = layer.extent()
    dx, dy = extent.width() / width, extent.height() / height
    tiles = []
    for y in np.unique(np.linspace(0, height - tile_height, min(5, height // tile_height + 1), dtype=int)):
        for x in np.unique(np.linspace(0, width - tile_width, min(5, width // tile_width + 1), dtype=int)):
            west, north = extent.xMinimum() + x * dx, extent.yMaximum() - y * dy
            block = provider.block(
                1, QgsRectangle(west, north - tile_height * dy, west + tile_width * dx, north),
                tile_width, tile_height,
            )
            if block and block.isValid():
                values = [
                    np.nan if block.isNoData(index) else block.value(index)
                    for index in range(tile_width * tile_height)
                ]
                tiles.append(np.asarray(values).reshape(tile_height, tile_width))
                tiles.append(np.full((1, tile_width), np.nan))
    if not tiles:
        raise ValueError("The raster could not be sampled.")
    sample = np.concatenate(tiles)
    finite = sample[np.isfinite(sample)]
    if not finite.size:
        raise ValueError("The raster has no finite samples.")
    low, high = np.percentile(finite, [2, 98])
    if low == high:
        low, high = np.min(finite), np.max(finite)
    if low == high:
        width = max(abs(low), 1.0) * 1e-6
        low, high = low - width, high + width
    return float(low), float(high), automatic_hillshade_z(sample, (dx, 0, 0, -dy))


def source_group(project, layer):
    node = project.layerTreeRoot().findLayer(layer.id())
    parent = node.parent()
    if parent.customProperty(GROUP) == layer.id():
        return parent
    group = parent.insertGroup(parent.children().index(node), layer.name())
    group.setCustomProperty(GROUP, layer.id())
    group.addChildNode(node.clone())
    parent.removeChildNode(node)
    return group


def effect_layer(project, source):
    return next(
        (layer for layer in project.mapLayers().values() if layer.customProperty(EFFECT) == source.id()),
        None,
    )


def apply_effect(source, shade, style, statistics):
    low, high, factor = statistics
    colors = CLASSIC if style.palette == "classic" else ("#000000", "#ffffff")
    ramp = QgsColorRampShader(low, high)
    ramp.setColorRampItemList([
        QgsColorRampShader.ColorRampItem(float(value), QColor(color), f"{value:.4g}")
        for value, color in zip(np.linspace(low, high, len(colors)), colors)
    ])
    shader = QgsRasterShader(low, high)
    shader.setRasterShaderFunction(ramp)
    renderer = QgsSingleBandPseudoColorRenderer(source.dataProvider(), 1, shader)
    renderer.setClassificationMin(low)
    renderer.setClassificationMax(high)
    source.setRenderer(renderer)
    hill = QgsHillshadeRenderer(shade.dataProvider(), 1, style.azimuth, style.altitude)
    hill.setZFactor(factor * style.intensity)
    shade.setRenderer(hill)
    shade.setOpacity(0.34)
    shade.setBlendMode(qt_enum(QPainter, "CompositionMode", "CompositionMode_Multiply"))
    for layer in (source, shade):
        layer.triggerRepaint()
    style.save_to_layer(source)


def calculate_shades(task, source, destination, stem, directions, altitude, z_factor, combined, crs_override):
    """Read and write GDAL files in the worker using only copied input values."""
    from ..terraworkbench_core.terrain_analysis import hillshade_arrays

    if task.isCanceled():
        return []
    grid = read_raster_source(source, 1)
    values = grid.values
    values[~np.isfinite(values)] = np.nan
    if grid.nodata is not None:
        values[values == grid.nodata] = np.nan
    transform = grid.geotransform
    pixel_transform = transform[1:3] + transform[4:6]
    results = []
    average = np.zeros(values.shape) if combined else None

    def write(shading, factor, azimuths, suffix):
        if task.isCanceled():
            raise InterruptedError()
        path = destination / f"{stem}_hs_{suffix}.tif"
        encoded = shading.astype(np.float32)
        if grid.nodata is not None:
            valid = np.isfinite(encoded)
            # Keep valid shadows distinguishable from a source NoData of zero.
            if 0 <= grid.nodata <= 1:
                nodata = np.float32(grid.nodata)
                substitute = np.nextafter(nodata, np.float32(1 if nodata < 0.5 else 0))
                if nodata == 0:
                    substitute = np.finfo(np.float32).eps
                encoded[valid & (encoded == nodata)] = substitute
            encoded[~valid] = grid.nodata
        metadata = {
            "TW_HILLSHADE_AZIMUTH": ",".join(map(str, azimuths)),
            "TW_HILLSHADE_ALTITUDE": str(altitude),
            "TW_HILLSHADE_Z_FACTOR": str(factor),
            "TW_HILLSHADE_SOURCE": source,
            "TW_HILLSHADE_WEIGHTS": ",".join([str(1 / len(azimuths))] * len(azimuths)),
        }
        results.append(path)
        output_grid = replace(grid, metadata=metadata, projection=crs_override or grid.projection)
        write_geotiff(str(path), encoded, output_grid, "Hillshade", grid.nodata, float32=True)

    try:
        for index, (shading, factor) in enumerate(hillshade_arrays(
            values, pixel_transform, directions, altitude, z_factor, task.isCanceled,
        )):
            azimuth = directions[index]
            if combined:
                average += shading / len(directions)
            else:
                write(shading, factor, [azimuth], f"az{azimuth:g}_alt{altitude:g}")
            task.setProgress(100.0 * (index + 1) / len(directions))
        if combined:
            write(average, factor, directions, "multi")
        return results
    except Exception:
        for path in results:
            path.unlink(missing_ok=True)
        raise
