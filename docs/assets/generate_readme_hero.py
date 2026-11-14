"""Generate a portable Britain demo and grab the real QGIS main window.

Run with the QGIS Python environment and an explicit --qgis executable.
QGIS executes this same file via --code to configure its isolated window.
"""
import argparse
from configparser import ConfigParser
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

COAST_URL = 'https://naturalearth.s3.amazonaws.com/10m_physical/ne_10m_coastline.zip'
PROJECT_NAME = 'Britain aeromagnetic survey'
WIDTH, HEIGHT = 1920, 1080


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def revision(root):
    return subprocess.check_output(
        [os.getenv('HERO_GIT', 'git'), 'rev-parse', 'HEAD'],
        cwd=root, text=True).strip()


def plugin_version(path):
    metadata = ConfigParser()
    metadata.read(path, encoding='utf-8')
    return metadata['general']['version']


def build_project(args, root):
    import numpy as np
    import pandas as pd
    from osgeo import gdal, osr
    from scipy.spatial import cKDTree
    from qgis.PyQt.QtGui import QColor
    from qgis.core import (
        Qgis, QgsApplication, QgsBilinearRasterResampler, QgsCoordinateReferenceSystem,
        QgsCoordinateTransform, QgsDatumTransform, QgsFeature, QgsFeatureRequest,
        QgsGeometry, QgsLineSymbol,
        QgsPointXY, QgsProject, QgsRasterLayer, QgsRectangle, QgsReferencedRectangle,
        QgsSingleSymbolRenderer, QgsVectorFileWriter, QgsVectorLayer,
    )
    from TerraWorkbench.terraworkbench_core.basic_processing import ThinPlateGridder
    from TerraWorkbench.terraworkbench_core.filter_recipes import apply_proposals

    from TerraWorkbench.terraworkbench_core.survey_store import SurveyStore
    from TerraWorkbench.terraworkbench_core.survey_map import build_survey_map
    from TerraWorkbench.qgis_plugin.survey_map_layers import (
        qgis_boundary, write_survey_geopackage, add_survey_map)
    from TerraWorkbench.ui.i18n import set_language

    data = args.run / 'demo'
    data.mkdir()
    QgsApplication.setPrefixPath(os.environ['QGIS_PREFIX_PATH'], True)
    app = QgsApplication([], False, str(args.run / 'builder-profile'))
    app.initQgis()
    set_language('en')
    project = QgsProject.instance()
    crs = QgsCoordinateReferenceSystem('EPSG:27700')
    wgs = QgsCoordinateReferenceSystem('EPSG:4326')
    operation_name = 'Inverse of OSGB36 to WGS 84 (6) + British National Grid'
    operation = next(op for op in QgsDatumTransform.operations(wgs, crs)
                     if operation_name in op.name and op.accuracy == 2 and op.isAvailable)
    context = project.transformContext()
    if not context.addCoordinateOperation(wgs, crs, operation.proj, False):
        raise RuntimeError('Could not set the requested 2 m datum transformation')
    reverse = next(op for op in QgsDatumTransform.operations(crs, wgs)
                   if 'OSGB36 to WGS 84 (6)' in op.name and op.accuracy == 2 and op.isAvailable)
    if not context.addCoordinateOperation(crs, wgs, reverse.proj, False):
        raise RuntimeError('Could not set the inverse 2 m datum transformation')
    project.setTransformContext(context)
    project.setCrs(crs)
    project.setTitle(PROJECT_NAME)
    project.setFilePathStorage(Qgis.FilePathType.Relative)
    project.setBackgroundColor(QColor('#f0f3f5'))
    extent = QgsRectangle(-100000, -100000, 750000, 1200000)
    project.viewSettings().setDefaultViewExtent(
        QgsReferencedRectangle(extent, crs))

    print('Gridding the public Britain survey', flush=True)
    survey = pd.read_csv(args.source)
    transform = QgsCoordinateTransform(wgs, crs, project)
    xy = np.array([(p.x(), p.y()) for p in (
        transform.transform(QgsPointXY(lon, lat))
        for lon, lat in zip(survey.longitude, survey.latitude))])
    z = survey.total_field_anomaly_nt.to_numpy(dtype=float)
    valid = np.isfinite(xy).all(axis=1) & np.isfinite(z)
    cell = 1000.0
    x = np.arange(-40000., 680001., cell)
    y = np.arange(-20000., 1090001., cell)
    xx, yy = np.meshgrid(x, y)
    query = np.column_stack((xx.ravel(), yy.ravel()))
    tps = ThinPlateGridder(xy[valid], z[valid], smoothing=0.0, neighbors=32)
    grid = np.concatenate([tps(query[i:i+8192]) for i in range(0, len(query), 8192)])
    grid = grid.reshape(xx.shape)
    distance, _ = cKDTree(xy[valid]).query(query)
    support = distance.reshape(xx.shape) <= 6000
    anomaly = np.where(support, grid, np.nan)
    proposals = [{'name': 'THDR', 'base': 'raw', 'steps': [{'filter': 'THDR'}]}]
    products, recipes = apply_proposals(
        grid, cell, proposals, padding=16,
        composite_derivative_method='finite_difference', composite_preparation='reflect')
    thdr = np.where(support, products['THDR'], np.nan)

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(27700)

    def raster(name, values):
        path = data / name
        ds = gdal.GetDriverByName('GTiff').Create(
            str(path), len(x), len(y), 1, gdal.GDT_Float64, options=['COMPRESS=DEFLATE'])
        ds.SetGeoTransform((x[0]-cell/2, cell, 0, y[-1]+cell/2, 0, -cell))
        ds.SetProjection(srs.ExportToWkt())
        band = ds.GetRasterBand(1)
        band.SetNoDataValue(float('nan'))
        band.WriteArray(values[::-1])
        ds.FlushCache()
        return str(path)

    anomaly_path = raster('britain_anomaly.tif', anomaly)
    thdr_path = raster('britain_thdr.tif', thdr)
    # Keep the complete interpolation available for the dock's actual filter.
    input_path = raster('britain_tps_input.tif', grid)
    display = QgsRasterLayer(anomaly_path, 'Total-field anomaly (nT)')
    result = QgsRasterLayer(thdr_path, 'Total horizontal derivative (nT/m)')
    processing_input = QgsRasterLayer(input_path, 'TPS grid (1 km)')
    processing_input.setCustomProperty('terraworkbench/demo_input', True)

    display.resampleFilter().setZoomedInResampler(QgsBilinearRasterResampler())
    display.resampleFilter().setZoomedOutResampler(QgsBilinearRasterResampler())

    workspace = data / 'Britain workspace'
    store = SurveyStore(workspace, create=True)
    observations = survey.copy()
    observations['easting'], observations['northing'] = xy[:, 0], xy[:, 1]
    source_csv = data / 'britain_observations.csv'
    observations.to_csv(source_csv, index=False)
    database = store.import_file(source_csv, name='Britain', metadata={
        'crs': 'EPSG:27700', 'line_field': 'line_and_segment',
        'date_field': 'year', 'x_field': 'easting', 'y_field': 'northing'})
    survey_map = build_survey_map(store, database, boundary_builder=qgis_boundary)
    package = write_survey_geopackage(store, database, survey_map)
    survey_layers = add_survey_map(project, store, database, 'Britain', package)
    if not {'flight_lines', 'tie_lines', 'survey_boundary'} <= survey_layers.keys():
        raise RuntimeError('Britain survey is missing automatic coverage layers')
    # Preserve the automatic styling; keep dense acquisition lines available
    # in the group without obscuring the anomaly at this continental scale.
    for key in ('flight_lines', 'tie_lines', 'samples'):
        if key in survey_layers:
            project.layerTreeRoot().findLayer(survey_layers[key].id()).setItemVisibilityChecked(False)

    coast_path = data / 'ne_10m_coastline.zip'
    shutil.copyfile(args.coast, coast_path)
    coast = QgsVectorLayer(f'/vsizip/{coast_path.as_posix()}/ne_10m_coastline.shp',
                          'Coastline', 'ogr')
    if not coast.isValid():
        raise RuntimeError('Could not open Natural Earth coastline')
    # Clip the global source in geographic coordinates before applying the
    # UK-area coordinate operation and writing a relative, projected source.
    region = QgsRectangle(-20, 43, 12, 64)
    region_geometry = QgsGeometry.fromRect(region)
    regional_coast = QgsVectorLayer('MultiLineString?crs=EPSG:4326', 'Regional coast', 'memory')
    coastline = []
    for feature in coast.getFeatures(QgsFeatureRequest().setFilterRect(region)):
        geometry = feature.geometry().intersection(region_geometry)
        if not geometry.isEmpty() and geometry.type() == Qgis.GeometryType.Line:
            geometry.convertToMultiType()
            clipped = QgsFeature()
            clipped.setGeometry(geometry)
            coastline.append(clipped)
    regional_coast.dataProvider().addFeatures(coastline)
    gpkg = str(data / 'survey_context.gpkg')
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.layerName = 'coastline'
    options.ct = transform
    error, message, *_ = QgsVectorFileWriter.writeAsVectorFormatV3(
        regional_coast, gpkg, project.transformContext(), options)
    if error:
        raise RuntimeError(message)
    coast = QgsVectorLayer(gpkg + '|layername=coastline', 'Coastline', 'ogr')
    coast.setRenderer(QgsSingleSymbolRenderer(
        QgsLineSymbol.createSimple({'line_color': '71,79,85,220', 'line_width': '0.20'})))
    if coast.crs().authid() != 'EPSG:27700':
        raise RuntimeError('Coastline GeoPackage was not reprojected to EPSG:27700')
    for layer, visible in ((processing_input, False), (result, False),
                           (display, True), (coast, True)):
        if not layer.isValid():
            raise RuntimeError(f'Invalid demo layer: {layer.name()}')
        project.addMapLayer(layer)
        node = project.layerTreeRoot().findLayer(layer.id())
        node.setItemVisibilityChecked(visible)
        node.setExpanded(False)

    project_path = data / 'Britain aeromagnetic survey.qgz'
    project.setFileName(str(project_path))
    if not project.write():
        raise OSError('Could not save the QGIS demo project')
    code_paths = ('terraworkbench_core/basic_processing.py', 'terraworkbench_core/filter_recipes.py',
                  'algorithms/magnetic_filters.py', 'ui/workflow_dock.py', 'qgis_plugin/plugin.py')
    record = {
        'qgis': Qgis.QGIS_VERSION,
        'terraworkbench': {'source_commit': revision(root), 'version': plugin_version(root/'metadata.txt'),
                           'source_code_sha256': {name: digest(root/name) for name in code_paths}},
        'survey': {'filename': args.source.name, 'sha256': digest(args.source), 'rows': len(survey),
                   'doi': '10.5281/zenodo.5879260', 'license': 'CC-BY-4.0',
                   'attribution': 'Uieda (2022); includes BGS materials © UKRI 2021 under OGL'},
        'coastline': {'source': COAST_URL, 'scale': '1:10m', 'license': 'public domain',
                      'sha256': digest(args.coast), 'stored_crs': 'EPSG:27700',
                      'geographic_clip': [-20, 43, 12, 64]},
        'coordinate_operation': {'name': operation.name, 'accuracy_m': operation.accuracy,
                                 'proj': operation.proj, 'allow_fallback': False,
                                 'reverse_name': reverse.name, 'reverse_proj': reverse.proj},
        'grid': {'crs': 'EPSG:27700', 'method': 'local thin-plate spline', 'neighbors': 32,
                 'cell_m': cell, 'smoothing': 0, 'support_distance_m': 6000,
                 'shape': list(grid.shape), 'survey_map': survey_map.summary},
        'filter': {'algorithm': 'terraworkbench:mag_thdr', 'recipes': recipes,
                   'display_mask': 'Apply the same support mask after the derivative.'},
        'style': {'function': 'HillshadeActions.toggle', 'palette': 'classic',
                  'parameters': 'TerraWorkbench defaults; automatic z factor and percentile stretch'},
        'generator_sha256': digest(Path(__file__)),
        'project_files': {p.name: digest(p) for p in sorted(data.iterdir()) if p.suffix in ('.qgz', '.gpkg', '.tif', '.zip')},
    }
    project.clear()
    return project_path, record


def capture_window(config):
    from qgis.PyQt.QtCore import QEventLoop, QSettings, Qt, QTimer
    from qgis.PyQt.QtGui import QFont, QImage
    from qgis.PyQt.QtWidgets import QApplication, QDockWidget, QWidget
    from qgis.core import Qgis, QgsProject, QgsRectangle, QgsSettings
    from qgis.utils import iface, loadPlugin, plugins, startPlugin
    import site
    import traceback

    log = Path(config['status'])
    log.write_text('QGIS startup code entered', encoding='utf-8')
    window = iface.mainWindow()

    closing = False

    def close():
        nonlocal closing
        if closing:
            return
        closing = True
        iface.mapCanvas().stopRendering()
        QgsProject.instance().clear()
        QgsProject.instance().setDirty(False)
        QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)
        QSettings().sync()
        window.close()

    def fail():
        log.write_text(traceback.format_exc(), encoding='utf-8')
        QTimer.singleShot(0, close)

    def prepare():
        try:
            for path in config['python_sites']:
                site.addsitedir(path)
            from TerraWorkbench.ui.dependency_dialog import SETTINGS_KEY, PLUGIN_VERSION, dependency_status
            from TerraWorkbench.ui.i18n import set_language
            from TerraWorkbench.ui.workflow_dock import KEY_INSPECTOR

            missing = [str(item.requirement) for item in dependency_status() if not item.satisfied]
            if missing:
                raise RuntimeError('Missing QGIS demo dependencies: ' + ', '.join(missing))
            QSettings().setValue(SETTINGS_KEY, PLUGIN_VERSION)
            QgsSettings().setValue('/projections/promptWhenMultipleTransformsExist',
                                   False, QgsSettings.App)
            QgsSettings().setValue(KEY_INSPECTOR, False)
            set_language('en')
            if 'TerraWorkbench' not in plugins:
                if not loadPlugin('TerraWorkbench') or not startPlugin('TerraWorkbench'):
                    raise RuntimeError('TerraWorkbench could not be loaded from the demo profile')
            log.write_text('TerraWorkbench loaded', encoding='utf-8')
            iface.addProject(config['project'])
            project = QgsProject.instance()
            if project.title() != PROJECT_NAME:
                raise RuntimeError('QGIS could not open the demonstration project')
            # Publish the existing automatically generated survey package again
            # in the UI language (also supports capture-only iterations).
            from TerraWorkbench.terraworkbench_core.survey_store import SurveyStore
            from TerraWorkbench.qgis_plugin.survey_map_layers import add_survey_map
            group = project.layerTreeRoot().findGroup('Britain')
            nodes = group.findLayers()
            survey_source = nodes[0].layer()
            package_path = Path(survey_source.source().split('|')[0])
            keys = tuple(node.layer().source().split('layername=')[1] for node in nodes)
            summary = json.loads(survey_source.metadata().abstract())
            store = SurveyStore(Path(config['project']).parent/'Britain workspace')
            database = store.databases()[0]['id']
            layers = add_survey_map(project, store, database, 'Britain', (package_path, keys, summary))
            for key, layer in layers.items():
                project.layerTreeRoot().findLayer(layer.id()).setItemVisibilityChecked(key == 'survey_boundary')
            dock = plugins['TerraWorkbench'].filter_stack_dock
            dock.setFloating(False)
            window.addDockWidget(Qt.RightDockWidgetArea, dock)
            dock.show()
            layer_panel = window.findChild(QDockWidget, 'Layers')
            if layer_panel is None:
                raise RuntimeError('QGIS Layers dock not found')
            layer_panel.show()
            for panel in window.findChildren(QDockWidget):
                if panel.objectName().lower().startswith('browser') or panel.windowTitle() in ('Browser', 'Navegador'):
                    panel.hide()
            for child in dock.findChildren(QWidget):
                child.setFont(QFont('Segoe UI', 11))
            source = next(layer for layer in project.mapLayers().values()
                          if layer.customProperty('terraworkbench/demo_input', False))
            dock.layer_combo.setCurrentIndex(dock.layer_combo.findData(source.id()))
            dock.choose_algorithm_id('terraworkbench:mag_thdr')
            dock.add_step()
            dock._set_work_directory(Path(config['project']).parent / 'Britain workspace')
            dock.inspector.hide()
            if len(dock.steps()) != 1 or dock.steps()[0].algorithm_id != 'terraworkbench:mag_thdr':
                raise RuntimeError('The actual dock does not contain the THDR filter')
            display = project.mapLayersByName('Total-field anomaly (nT)')[0]
            iface.setActiveLayer(display)
            dock.hillshade.toggle_action.trigger()
            from TerraWorkbench.qgis_plugin.hillshade import effect_layer, visual_statistics
            shade = effect_layer(project, display)
            if shade is None:
                raise RuntimeError('The Hillshade button did not create its visual effect')
            config['hillshade_statistics'] = list(visual_statistics(display))
            window.showNormal()
            window.resize(WIDTH, HEIGHT)
            window.resizeDocks([layer_panel, dock], [360, 580], Qt.Horizontal)
            window.setWindowTitle(f'{PROJECT_NAME} — QGIS')
            canvas = iface.mapCanvas()
            canvas.setExtent(QgsRectangle(-100000, -100000, 750000, 1200000))
            canvas.refresh()
            QTimer.singleShot(500, lambda: wait_for_render(canvas, dock, layer_panel))
        except Exception:
            fail()

    def wait_for_render(canvas, dock, layer_panel, attempts=0):
        if closing:
            return
        try:
            if canvas.isDrawing() or attempts < 2:
                if attempts >= 100:
                    raise TimeoutError('QGIS map canvas did not finish rendering')
                QTimer.singleShot(250, lambda: wait_for_render(canvas, dock, layer_panel, attempts+1))
                return
            if QApplication.activeModalWidget() is not None:
                raise RuntimeError('Unexpected modal dialog during capture')
            message_bar = iface.messageBar()
            warnings = [(item.title(), item.text()) for item in message_bar.items()
                        if item.level() != Qgis.MessageLevel.Info]
            if warnings:
                raise RuntimeError(f'Unexpected QGIS warnings during capture: {warnings}')
            message_bar.clearWidgets()
            shot = window.grab()
            if (window.width(), window.height(), shot.width(), shot.height()) != (WIDTH, HEIGHT, WIDTH, HEIGHT) or shot.devicePixelRatio() != 1:
                raise RuntimeError(f'Unexpected capture scale: {shot.width()}x{shot.height()}, DPR={shot.devicePixelRatio()}')
            if not shot.save(config['image'], 'PNG'):
                raise OSError('Could not save QGIS main window grab')
            if config['preview']:
                scaled = QImage(config['image']).scaledToWidth(900, Qt.SmoothTransformation)
                if not scaled.save(config['preview'], 'PNG'):
                    raise OSError('Could not save 900 px preview')
            log.write_text(json.dumps({
                'platform': QApplication.platformName(), 'logical_size': [window.width(), window.height()],
                'pixel_size': [shot.width(), shot.height()], 'device_pixel_ratio': shot.devicePixelRatio(),
                'pixel_to_logical_ratio': shot.width() / window.width(),
                'modal_dialog': False, 'hillshade_statistics': config['hillshade_statistics'],
                'work_folder': dock.work_directory_button.text(),
                'filter_steps': [step.algorithm_id for step in dock.steps()],
                'dock_visible': dock.isVisible(), 'layers_visible': layer_panel.isVisible(),
                'canvas_layers': [layer.name() for layer in canvas.layers()],
                'canvas_extent_epsg_27700': canvas.extent().toString(),
            }), encoding='utf-8')
            QTimer.singleShot(0, close)
        except Exception:
            fail()

    def cancel_stalled_capture():
        if closing or (log.exists() and log.read_text(encoding='utf-8').startswith('{')):
            return
        log.write_text('QGIS capture did not complete in 60 seconds', encoding='utf-8')
        dialog = QApplication.activeModalWidget()
        if dialog is not None:
            dialog.reject()
        QTimer.singleShot(0, close)

    QTimer.singleShot(60000, cancel_stalled_capture)
    QTimer.singleShot(0, prepare)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'coast', 'run', 'assets', 'qgis'):
        parser.add_argument(f'--{name}', type=Path, required=True)
    parser.add_argument('--reuse-build', type=Path, help='Reuse a completed build record for capture-only iterations')
    parser.add_argument('--python-site', type=Path, action='append', default=[])
    parser.add_argument('--platform', default='windows')
    parser.add_argument('--proj-grid', type=Path, required=True,
                        help='Local uk_os_OSTN15_NTv2_OSGBtoETRS.tif, for QGIS startup transforms')
    args = parser.parse_args()
    for name in ('source', 'coast', 'run', 'assets', 'qgis'):
        setattr(args, name, getattr(args, name).resolve())
    os.environ['QT_QPA_PLATFORM'] = 'offscreen'
    os.environ['QGIS_CUSTOM_CONFIG_PATH'] = str(args.run / 'builder-profile')
    args.run.mkdir(parents=True, exist_ok=False)
    args.assets.mkdir(parents=True, exist_ok=True)
    root = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root.parent))
    import site
    for path in args.python_site:
        site.addsitedir(str(path))
    from scripts.package_plugin import package_files

    profile = args.run/'profiles'
    plugin = profile/'profiles'/'Britain demo'/'python'/'plugins'/'TerraWorkbench'
    for source in package_files():
        destination = plugin/source.relative_to(root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)

    # QGIS evaluates geographic view extents during startup, before it reads
    # the project's explicit operations. Make its preferred grid available
    # in each isolated profile, never in the user's QGIS profile.
    for folder in (args.run/'builder-profile'/'proj',
                   args.run/'builder-profile'/'profiles'/'default'/'proj',
                   profile/'profiles'/'Britain demo'/'proj'):
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.proj_grid, folder/args.proj_grid.name)
    if args.reuse_build:
        previous = args.reuse_build.resolve()
        record = json.loads((previous/'assets'/'readme-hero-record.json').read_text(encoding='utf-8'))
        record['build_generator_sha256'] = record.get('build_generator_sha256', record['generator_sha256'])
        project = previous/'demo'/'Britain aeromagnetic survey.qgz'
        record['generator_sha256'] = digest(Path(__file__))
    else:
        project, record = build_project(args, root)
    record['startup_proj_grid'] = {'name': args.proj_grid.name, 'sha256': digest(args.proj_grid)}
    image = args.assets/'readme-hero.png'
    if image.exists():
        raise FileExistsError(image)
    status = args.run/'capture.json'
    config = {
        'project': str(project), 'image': str(image), 'status': str(status),
        'preview': str(args.run/'github-900.png'),
        'python_sites': [str(path.resolve()) for path in args.python_site],
    }
    env = dict(os.environ, QT_QPA_PLATFORM=args.platform, QT_SCALE_FACTOR='1',
               QT_AUTO_SCREEN_SCALE_FACTOR='0', QT_ENABLE_HIGHDPI_SCALING='0',
               QT_SCREEN_SCALE_FACTORS='1', QGIS_CUSTOM_CONFIG_PATH=str(profile),
               TW_HERO_CAPTURE_CONFIG=json.dumps(config), PYTHONDONTWRITEBYTECODE='1')
    command = [str(args.qgis), '--nologo', '--noversioncheck', '--nocustomization',
               '--lang', 'en_US', '--profiles-path', str(profile),
               '--profile', 'Britain demo', '--code', str(Path(__file__).resolve())]
    print(f'Launching full QGIS on {args.platform}', flush=True)
    try:
        subprocess.run(command, env=env, check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(status.read_text(encoding='utf-8') if status.exists()
                           else 'QGIS startup did not complete') from exc
    if not image.is_file():
        raise RuntimeError(status.read_text(encoding='utf-8') if status.exists()
                           else 'QGIS exited without a capture')
    record['capture'] = {'name': image.name, 'sha256': digest(image),
                         'qt_scale_factor': 1, **json.loads(status.read_text(encoding='utf-8'))}
    record['preview_sha256'] = digest(args.run/'github-900.png')
    (args.assets/'readme-hero-record.json').write_text(
        json.dumps(record, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Native QGIS main window grab saved', flush=True)
    sys.stdout.flush()
    os._exit(0)  # Isolated builder owns QGIS C++ objects until process exit.


if os.getenv('TW_HERO_CAPTURE_CONFIG'):
    capture_window(json.loads(os.environ['TW_HERO_CAPTURE_CONFIG']))
elif __name__ == '__main__':
    main()
