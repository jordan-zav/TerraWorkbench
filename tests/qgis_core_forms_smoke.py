"""Construct every registered form and exercise typed/NPZ/error paths."""

import importlib
import inspect
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

import numpy as np
from qgis.core import QgsApplication, QgsSettings
from qgis.PyQt import sip
from qgis.PyQt.QtGui import QFont, QFontDatabase
from qgis.PyQt.QtWidgets import QLabel, QFileDialog, QMessageBox
from qgis.PyQt.QtTest import QTest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from TerraWorkbench.ui.i18n import LANGUAGE_KEY, set_language
from TerraWorkbench.ui.core_job_dialog import CoreJobDialog
from TerraWorkbench.ui.core_parameter_form import CoreParameterForm
from TerraWorkbench.ui.core_field_editor import CoreFieldEditor
from TerraWorkbench.ui.core_workflow_dialog import CoreWorkflowDialog
from TerraWorkbench.ui.core_parameter_schema import presentation_signature
from TerraWorkbench.terraworkbench_core.operations import list_operations, run_operation
from TerraWorkbench.terraworkbench_core.operation_jobs import load_core_job


def exercise_processing_workflow(root, locale, app):
    output = root / ("workflow_" + locale)
    output.mkdir()
    wave = np.broadcast_to(100.0 * np.cos(2 * np.pi * np.arange(9) / 9), (9, 9))
    source = output / "input.npz"
    np.savez(source, density=wave)
    original = source.read_bytes()
    options = dict(
        kind="density", top_depth_m=10.0, thickness_m=50.0, spacing=[5.0, 5.0]
    )
    plan = dict(
        steps=[
            dict(
                id="response",
                operation="potential.layer_response",
                parameters=dict(options, values={"$array": "density"}),
            ),
            dict(
                id="recover",
                operation="potential.apparent_property",
                parameters=dict(
                    options,
                    values={"$result": ["response", "predicted"]},
                    background=0.0,
                    regularization_response=0.0,
                    max_inverse_gain=1e12,
                    minimum_wavelength_m=10.0,
                ),
            ),
        ]
    )
    recipe = output / "recipe.json"
    recipe.write_text(json.dumps(plan), encoding="utf-8")
    dialog = CoreWorkflowDialog()
    try:
        dialog.load_recipe(recipe)
        assert dialog.steps.count() == 2
        before = dialog.recipe_text
        bad = output / "bad.json"
        bad.write_text('{"steps":[],"steps":[]}', encoding="utf-8")
        try:
            dialog.load_recipe(bad)
            raise AssertionError("Duplicate workflow keys accepted")
        except ValueError:
            pass
        assert dialog.recipe_text == before and dialog.steps.count() == 2
        dialog.input_path.setText(str(source))
        dialog.output_path.setText(str(output))
        dialog.start()
        deadline = time.monotonic() + 30
        while dialog.worker is not None and time.monotonic() < deadline:
            app.processEvents()
            QTest.qWait(5)
        assert dialog.worker is None, "Workflow worker did not finish"
        assert dialog.result is not None, dialog.status.text()
        final = load_core_job(Path(dialog.result["folder"]) / "recover")
        np.testing.assert_allclose(final["result"]["contrast"], wave, atol=1e-8)
        assert source.read_bytes() == original
        if locale == "en":
            checks = (
                (
                    "gravity.terrain_adaptive",
                    dict(
                        easting=[0.0, 1.0],
                        northing=[0.0, 1.0],
                        elevation_m=[[1.0, 2.0], [3.0, 4.0]],
                        observation_xyz=[[0.0, 0.0, 10.0], [100.0, 100.0, 50.0]],
                        density_crust=2670.0,
                        density_water=1040.0,
                        reference_elevation_m=0.0,
                        absolute_tolerance_mgal=1e-6,
                    ),
                    "harmonica",
                ),
                (
                    "magnetic.igrf",
                    dict(
                        longitude=[-75.0],
                        latitude=[-10.0],
                        altitude_km=[0.0],
                        date="2025-01-01",
                    ),
                    "ppigrf",
                ),
                (
                    "gravity.terrain_prisms",
                    dict(
                        easting=[0.0, 1.0],
                        northing=[0.0, 1.0],
                        elevation_m=[[0.0, 0.0], [0.0, 0.0]],
                        density_crust=2670.0,
                        density_water=1040.0,
                        clearance_m=1.0,
                    ),
                    "harmonica",
                ),
                (
                    "potential.reproject_xy",
                    dict(
                        x=[-75.0],
                        y=[0.0],
                        source_crs="EPSG:4326",
                        target_crs="EPSG:32718",
                    ),
                    "pyproj",
                ),
                (
                    "structural.skeleton_paths",
                    dict(
                        feature_mask=np.eye(9, dtype=bool),
                        spacing=[1.0, 1.0],
                        origin_xy=[0.0, 0.0],
                    ),
                    "scikit-image",
                ),
            )
            for operation, parameters, library in checks:
                checked = run_operation(operation, **parameters)
                assert library in checked["provenance"]["libraries"]
            print(
                "PASS optional-engine Core operations executed with library provenance",
                flush=True,
            )
        dialog.show()
        app.processEvents()
        assert dialog.grab().save(str(output / "workflow.png"))
    finally:
        if dialog.worker is not None:
            dialog.cancel()
            dialog.worker.wait(30000)
            app.processEvents()
        if dialog.worker is None:
            sip.delete(dialog)


def exercise_recipe_loading(root, locale):
    signature = inspect.Signature(
        [
            inspect.Parameter("dt_s", inspect.Parameter.KEYWORD_ONLY, default=1.0),
            inspect.Parameter("text", inspect.Parameter.KEYWORD_ONLY, default=""),
        ]
    )
    form = CoreParameterForm(signature)
    before = {"dt_s": 1.0, "text": "original"}
    form.set_parameters(before)
    for invalid in (3, "\ud800"):
        try:
            form.set_parameters({"dt_s": 2.0, "text": invalid})
            raise AssertionError("Invalid text accepted by text editor")
        except ValueError:
            pass
        assert form.parameters() == before, "Earlier fields changed on failed load"
    sip.delete(form)

    dialog = CoreJobDialog("gpr.dewow")
    before = {"traces": [[1, 2, 3, 4, 5]], "dt_s": 0.01, "window_samples": 3}
    dialog.parameter_form.set_parameters(before)
    dialog.parameters.setPlainText("unfinished JSON draft")
    dialog.parameter_tabs.setCurrentIndex(1)
    archive = root / ("saved_arrays_" + locale + ".npz")
    np.savez(archive, traces=np.arange(5).reshape(1, 5))
    dialog.input_path.setText(str(archive))
    dialog.refresh_input_arrays()
    dialog.output_path.setText(str(root))
    field = dialog.parameter_form.fields["traces"][0]
    tooltip = dialog.input_path.toolTip()
    recipes = [
        '{"dt_s": .02}',
        '{"dt_s": 0.02, "dt_s": 0.03}',
        '{"dt_s": NaN}',
        '{"provenance":{"operation_id":"other"}, "parameters":{}}',
        '{"dt_s": 0.02, "unknown": true}',
        json.dumps({"traces": "x" * (1024**2 + 1)}),
    ]
    for index, raw in enumerate(recipes):
        path = root / f"bad_recipe_{locale}_{index}.json"
        path.write_text(raw, encoding="utf-8")
        with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "")):
            dialog.load_parameters()
        assert dialog.parameters.toPlainText() == "unfinished JSON draft"
        assert dialog.parameter_form.parameters() == before
        assert dialog.parameter_tabs.currentIndex() == 1
        assert dialog.input_path.text() == str(archive)
        assert dialog.input_path.toolTip() == tooltip
        assert field.arrays.count() == 2
        assert dialog.output_path.text() == str(root)
        assert path.read_text(encoding="utf-8") == raw
    valid = dict(before, dt_s=0.02)
    path = root / f"valid_recipe_{locale}.json"
    path.write_text(
        json.dumps({"provenance": {"operation_id": "gpr.dewow"}, "parameters": valid}),
        encoding="utf-8-sig",
    )
    with patch.object(QFileDialog, "getOpenFileName", return_value=(str(path), "")):
        dialog.load_parameters()
    assert dialog.parameter_form.parameters() == valid
    assert json.loads(dialog.parameters.toPlainText()) == valid
    assert dialog.parameter_tabs.currentIndex() == 0
    assert not dialog.input_path.text() and not dialog.input_path.toolTip()
    assert field.arrays.count() == 1 and field.arrays.isHidden()
    assert dialog.output_path.text() == str(root)
    sip.delete(dialog)
    print(
        "PASS",
        locale,
        "atomic recipe load, malformed/oversized JSON rejection and NPZ selector reset",
        flush=True,
    )


def exercise_depth_grid(root, locale, app):
    dialog = CoreJobDialog("depth.interpret_grid")
    form = dialog.parameter_form
    coordinate = np.linspace(-10, 10, 5)
    xx, yy = np.meshgrid(coordinate, coordinate)
    radius = np.sqrt(xx**2 + yy**2 + 25)
    parameters = dict(
        method="euler",
        x=coordinate.tolist(),
        y=coordinate.tolist(),
        elevation=0,
        field=(1 / radius).tolist(),
        derivative_grids={
            "dx": (-xx / radius**3).tolist(),
            "dy": (-yy / radius**3).tolist(),
            "dz": (-5 / radius**3).tolist(),
        },
        structural_index=1,
        window_size=5,
    )
    form.set_parameters(parameters)
    assert form.parameters() == parameters
    result = run_operation("depth.interpret_grid", **form.parameters())["result"]
    assert len(result["solutions"]) == 1
    assert abs(result["solutions"][0]["depth"] - 5) < 1e-8
    dialog.insert_required()
    assert "structural_index" in json.loads(dialog.parameters.toPlainText())
    form.set_arrays({"profile": "shape (101,), float64"})
    method = form.base.fields["method"][0]
    form.fields["structural_index"][0].setText("unfinished")
    method.setText('"werner"')
    assert "structural_index" not in form.fields and "background_degree" in form.fields
    assert "structural_index" not in form.parameters()
    assert form.fields["profile_id"][0].arrays.count() == 2
    method.setText('"euler"')
    assert form.fields["structural_index"][0].text() == "unfinished"
    form.set_parameters(parameters)
    assert form.fields["structural_index"][0].text() == "1"
    form.option_form.extra.setPlainText('{"x": [1, 2]}')
    try:
        form.parameters()
        raise AssertionError("Method options overrode grid geometry")
    except ValueError:
        pass
    form.option_form.extra.setPlainText("{}")
    form.option_form.extra.setPlainText('{"observation_elevation": 5}')
    try:
        form.parameters()
        raise AssertionError("Method options overrode facade-supplied elevation")
    except ValueError:
        pass
    form.option_form.extra.setPlainText("{}")
    snapshot = form.parameters()
    try:
        form.set_parameters({"method": "invalid", "structural_index": 1})
        raise AssertionError("Invalid method recipe accepted")
    except ValueError:
        pass
    assert form.parameters() == snapshot

    along = np.linspace(499500.0, 500500.0, 101)
    across = np.arange(4.0) * 10 + 6000000
    u, depth = along - 500030.0, 125.0
    values = np.tile(20000 * depth / (u * u + depth**2) + 45000.0, (4, 1))
    g = (depth + 1j * u) ** -2
    dg = -2j * (depth + 1j * u) ** -3
    derivatives = {
        name: np.tile(value, (4, 1)).tolist()
        for name, value in (
            ("dx", g.real),
            ("dz", g.imag),
            ("dxx", dg.real),
            ("dxz", dg.imag),
        )
    }
    for chosen in ("werner", "spi"):
        parameters = dict(
            method=chosen,
            x=along.tolist(),
            y=across.tolist(),
            elevation=50.0,
            field=values.tolist(),
        )
        if chosen == "werner":
            parameters.update(window_size=31, stride=10)
        else:
            parameters.update(derivative_grids=derivatives, source_model="thin_sheet")
        dialog.parameters.setPlainText(json.dumps(parameters))
        dialog.parameter_tabs.setCurrentIndex(0)
        form.set_parameters(parameters)
        assert form.parameters() == parameters
        result = run_operation("depth.interpret_grid", **form.parameters())["result"]
        assert len(result["solutions"]) == (32 if chosen == "werner" else 4)
        np.testing.assert_allclose(
            [s["depth"] for s in result["solutions"]], depth, rtol=1e-6
        )
        form.tabs.setCurrentIndex(1)
        dialog.show()
        app.processEvents()
        assert dialog.grab().save(str(root / f"grid_{chosen}_{locale}.png"))
    sip.delete(dialog)
    print(
        "PASS",
        locale,
        "method-specific grid forms, draft preservation, recipe roundtrip and Euler/Werner/SPI calculations",
        flush=True,
    )


def main():
    QgsApplication.setPrefixPath(os.environ["QGIS_PREFIX_PATH"], True)
    app = QgsApplication([], False)
    app.initQgis()
    if os.name == "nt":
        QFontDatabase.addApplicationFont(
            str(Path(os.environ["WINDIR"]) / "Fonts/arial.ttf")
        )
    app.setFont(QFont("Arial", 10))
    settings = QgsSettings()
    previous = settings.value(LANGUAGE_KEY) if settings.contains(LANGUAGE_KEY) else None
    root = Path(tempfile.gettempdir()) / "core-forms"
    root.mkdir()
    try:
        for locale in ("en", "es", "pt"):
            set_language(locale)
            count = 0
            for metadata in list_operations():
                module = importlib.import_module("TerraWorkbench." + metadata["module"])
                signature = presentation_signature(
                    getattr(module, metadata["function"]), metadata["id"]
                )
                form = CoreParameterForm(signature, operation_id=metadata["id"])
                assert all(field.accessibleName() for field, _ in form.fields.values())
                assert not any(
                    "Unauthored" in label.text() for label in form.findChildren(QLabel)
                )
                for name, (field, required) in form.fields.items():
                    if required and form.kinds[name] in (
                        "integer",
                        "number",
                        "text",
                        "string",
                    ):
                        assert "JSON" not in field.line.placeholderText()
                        assert field.line.placeholderText()
                    if required and form.kinds[name] == "json":
                        assert "JSON" in field.line.placeholderText()
                    assert field.text() == "", (
                        metadata["id"],
                        name,
                        "must not guess values",
                    )
                if metadata["id"] == "depth.euler_window":
                    assert form.fields["structural_index"][1]
                    assert "max_relative_depth_error" in form.fields
                if metadata["id"] in (
                    "fdem.fit_conductivity",
                    "tem.fit_conductivity",
                    "tem.gate_average",
                ):
                    assert form.fields["source_m"][1] and form.fields["receiver_m"][1]
                    assert (
                        "conductivity_s_m" not in form.fields
                        or metadata["id"] == "tem.gate_average"
                    )
                sip.delete(form)
                count += 1
            dialog = CoreJobDialog("gpr.dewow")
            dialog.parameter_form.set_parameters(
                {"traces": [[1, 2, 3, 4, 5]], "dt_s": 0.01, "window_samples": 3}
            )
            assert dialog.parameter_form.parameters()["window_samples"] == 3
            dialog.parameter_form.fields["window_samples"][0].setText("4")
            try:
                dialog.parameter_form.parameters()
                raise AssertionError("Even dewow window was accepted")
            except ValueError:
                pass
            dialog.run()
            assert ("Review", "Revisa", "Revise")[
                ("en", "es", "pt").index(locale)
            ] in dialog.status.text()
            archive = root / f"input_{locale}.npz"
            np.savez(
                archive, traces=np.arange(40).reshape(2, 20), times=np.arange(20) * 0.01
            )
            dialog.input_path.setText(str(archive))
            dialog.refresh_input_arrays()
            field = dialog.parameter_form.fields["traces"][0]
            assert field.arrays.count() == 3
            field._array_selected(field.arrays.findData("traces"))
            assert field.text() == "@traces"
            assert "(2, 20)" in dialog.input_path.toolTip()
            bad = root / "bad.npz"
            bad.write_bytes(b"not an archive")
            dialog.input_path.setText(str(bad))
            dialog.refresh_input_arrays()
            assert field.arrays.count() == 1
            dialog.show()
            app.processEvents()
            assert dialog.grab().save(str(root / f"editor_{locale}.png"))
            sip.delete(dialog)
            selection = CoreJobDialog("gpr.background")
            choice = selection.parameter_form.fields["method"][0]
            choice.setText('"median"')
            assert json.loads(choice.text()) == "median"
            sip.delete(selection)
            euler = CoreJobDialog("depth.euler_window")
            xx, yy = np.meshgrid(np.linspace(-10, 10, 5), np.linspace(-10, 10, 5))
            xyz = np.column_stack((xx.ravel(), yy.ravel(), np.zeros(xx.size)))
            relative = xyz - np.array([0.0, 0.0, -5.0])
            radius = np.linalg.norm(relative, axis=1)
            euler.parameter_form.set_parameters(
                {
                    "xyz": xyz.tolist(),
                    "field": (1 / radius).tolist(),
                    "gradients": (-relative / radius[:, None] ** 3).tolist(),
                    "structural_index": 1,
                }
            )
            solution, reason = run_operation(
                "depth.euler_window", **euler.parameter_form.parameters()
            )["result"]
            assert reason is None and abs(solution["depth"] - 5) < 1e-8
            sip.delete(euler)
            exercise_depth_grid(root, locale, app)
            exercise_recipe_loading(root, locale)
            exercise_processing_workflow(root, locale, app)
            # Exercise new typed geometry and calibrated spectra in all three
            # locales, in addition to constructing every registered form.
            extension_cases = (
                (
                    "inversion.spatial_constraints",
                    dict(
                        cell_centers_enu_m=[[0.0, 0.0, -100.0], [300.0, 0.0, -100.0]],
                        lower=0.0,
                        upper=1.0,
                        background_value=0.0,
                        support_prisms_m=[[-100.0, 100.0, -100.0, 100.0, -200.0, 0.0]],
                        mode="hard",
                    ),
                    "upper",
                ),
                (
                    "inversion.recovery_metrics",
                    dict(
                        coordinates_enu_m=[[0.0, 0.0, -100.0], [100.0, 0.0, -100.0]],
                        cell_volumes_m3=[1.0, 1.0],
                        recovered=[1.0, 0.0],
                        truth=[1.0, 0.0],
                        criteria=dict(
                            location_tolerance_m=100.0,
                            volume_relative_tolerance=0.35,
                            contrast_relative_tolerance=0.35,
                            support_dice_min=0.6,
                            direction_tolerance_deg=15.0,
                            model_relative_tolerance=0.5,
                        ),
                        connectivity_radius_m=101.0,
                    ),
                    "model_relative_error",
                ),
                (
                    "gravity.polygon_forward",
                    dict(
                        observation_xz_m=[[0.0, 0.0]],
                        polygons_xz_m=[[[-20.0, -100.0], [20.0, -100.0], [0.0, -50.0]]],
                        density_kg_m3=[500.0],
                    ),
                    "gravity_mgal",
                ),
                (
                    "radiometry.full_spectrum_radon",
                    dict(
                        spectra=[[2.0, 3.0]],
                        response_matrix=[[1.0, 0.0], [0.0, 1.0]],
                        rate_std=[1.0, 1.0],
                        component_names=["ground", "radon"],
                        radon_component=1,
                    ),
                    "corrected_spectra",
                ),
                (
                    "potential.ordinary_kriging",
                    dict(
                        coordinates=[[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]],
                        values=[1.0, 2.0, 3.0],
                        query_coordinates=[[0.2, 0.3]],
                        range_m=2.0,
                        partial_sill=1.0,
                        model="gaussian",
                        neighbors=3,
                    ),
                    "predicted",
                ),
            )
            for operation, parameters, result_key in extension_cases:
                extension = CoreJobDialog(operation)
                extension.parameter_form.set_parameters(parameters)
                result = run_operation(
                    operation, **extension.parameter_form.parameters()
                )
                assert np.isfinite(result["result"][result_key]).all()
                sip.delete(extension)
            linear_form = CoreJobDialog("inversion.stochastic_resolution")
            linear_form.parameter_form.set_parameters(
                dict(
                    sensitivity=[[1.0, 0.0], [0.0, 2.0]],
                    data_std=[1.0, 1.0],
                    regularization=[[1.0, 0.0], [0.0, 1.0]],
                    beta=1.0,
                    method="basis",
                    probe_count=2,
                )
            )
            linear_result = run_operation(
                "inversion.stochastic_resolution",
                **linear_form.parameter_form.parameters(),
            )
            np.testing.assert_allclose(
                linear_result["result"]["posterior_variance_estimate"], [0.5, 0.2]
            )
            sip.delete(linear_form)
            text_editor = CoreFieldEditor("text")
            long_text = "LAS metadata " * 4000
            text_editor.setText(json.dumps(long_text))
            assert json.loads(text_editor.text()) == long_text
            source = root / "text.las"
            source.write_text(long_text, encoding="utf-8")
            with patch.object(
                QFileDialog, "getOpenFileName", return_value=(str(source), "")
            ):
                text_editor.load_text()
            assert json.loads(text_editor.text()) == long_text
            assert source.read_text(encoding="utf-8") == long_text
            source.write_bytes(b"\xff")
            with (
                patch.object(
                    QFileDialog, "getOpenFileName", return_value=(str(source), "")
                ),
                patch.object(QMessageBox, "warning") as warning,
            ):
                text_editor.load_text()
                assert warning.called
            assert json.loads(text_editor.text()) == long_text
            try:
                text_editor.setText("x" * (1024**2 + 1))
                raise AssertionError("Oversized editor input accepted")
            except ValueError:
                pass
            assert json.loads(text_editor.text()) == long_text
            sip.delete(text_editor)
            print(
                "PASS",
                locale,
                count,
                "Core forms; explicit required fields, typed validation, NPZ metadata and error handling",
                flush=True,
            )
    finally:
        if previous is None:
            settings.remove(LANGUAGE_KEY)
        else:
            settings.setValue(LANGUAGE_KEY, previous)
        app.exitQgis()


if __name__ == "__main__":
    main()
