"""Discoverable standalone operations, lazy engines and execution provenance.

Only actual implemented operations are registered. Backlog links identify
related proposals, NOT completion of every requirement in that proposal.
Metadata feeds the process centre and its explicit advanced Core console.
"""

from datetime import datetime, timezone
import hashlib
import importlib
from importlib.metadata import version
import inspect
import json
from pathlib import Path
import platform

import numpy as np
import scipy


# id: module, function, domain, related backlog candidate, optional extra.
_OPERATIONS = {
    "gravity.polygon_forward": (
        "gravity_profiles",
        "polygon_gravity_2d",
        "space",
        "GRAV-04",
        None,
    ),
    "gravity.polygon_density_fit": (
        "gravity_profiles",
        "fit_polygon_densities",
        "space",
        "GRAV-04",
        None,
    ),
    "radiometry.upward_window_radon": (
        "radon_corrections",
        "upward_window_radon",
        "time",
        "RAD-04",
        None,
    ),
    "radiometry.window_radon": (
        "radon_corrections",
        "calibrated_window_radon",
        "time-energy",
        "RAD-06",
        None,
    ),
    "radiometry.full_spectrum_radon": (
        "radon_corrections",
        "full_spectrum_radon",
        "time-energy",
        "RAD-06",
        None,
    ),
    "radiometry.background_correction": (
        "radiometry",
        "background_correction",
        "time",
        "RAD-06",
        None,
    ),
    "potential.empirical_variogram": (
        "geostatistics",
        "empirical_variogram",
        "space",
        "POT-09",
        None,
    ),
    "potential.ordinary_kriging": (
        "geostatistics",
        "ordinary_kriging",
        "space",
        "POT-09",
        None,
    ),
    "gravity.terrain_adaptive": (
        "adaptive_terrain",
        "terrain_gravity_adaptive",
        "space",
        "GRAV-08",
        "prisms",
    ),
    "magnetic.components": (
        "magnetic_components",
        "convert_field_component",
        "space-wavenumber",
        "MAG-03",
        None,
    ),
    "magnetic.gradient_tmi": (
        "magnetic_components",
        "reconstruct_tmi_from_gradients",
        "space-wavenumber",
        "MAG-03",
        None,
    ),
    "potential.radial_filter": (
        "radial_filters",
        "tabulated_radial_filter",
        "space-wavenumber",
        "POT-04",
        None,
    ),
    "potential.layer_response": (
        "apparent_properties",
        "layer_property_response",
        "space-wavenumber",
        "MAG-01",
        None,
    ),
    "potential.apparent_property": (
        "apparent_properties",
        "apparent_layer_property",
        "space-wavenumber",
        "MAG-01",
        None,
    ),
    "magnetic.dipole_forward": (
        "compact_magnetics",
        "magnetic_dipole_field",
        "space",
        "MAG-08",
        None,
    ),
    "magnetic.dipole_fit": (
        "compact_magnetics",
        "fit_magnetic_dipoles",
        "space",
        "MAG-08",
        None,
    ),
    "structural.phase": (
        "structural_attributes",
        "monogenic_phase_attributes",
        "space-wavenumber",
        "STR-01",
        None,
    ),
    "structural.texture": (
        "structural_attributes",
        "local_grid_texture",
        "space",
        "STR-02",
        None,
    ),
    "structural.orientation_entropy": (
        "structural_attributes",
        "local_orientation_entropy",
        "space",
        "STR-03",
        None,
    ),
    "structural.skeleton_paths": (
        "lineament_geometry",
        "skeleton_paths",
        "space",
        "STR-04",
        "structure",
    ),
    "magnetic.igrf": (
        "geomagnetism",
        "igrf_field",
        "space-time",
        "MAG-04",
        "geomagnetism",
    ),
    "potential.reproject_xy": (
        "coordinates",
        "reproject_xy",
        "space",
        "POT-08",
        "coordinates",
    ),
    "gravity.terrain_prisms": (
        "terrain_gravity",
        "terrain_correction_prisms",
        "space",
        "GRAV-08",
        "prisms",
    ),
    "depth.euler_window": ("source_depth", "euler_window", "space", "POT-07", None),
    "depth.euler_grid": ("source_depth", "euler_grid", "space", "POT-07", None),
    "depth.euler_profile": (
        "source_depth",
        "euler_profile",
        "distance",
        "POT-07",
        None,
    ),
    "depth.werner_profile": (
        "source_depth",
        "werner_profile",
        "distance",
        "POT-07",
        None,
    ),
    "depth.spi_profile": ("source_depth", "spi_profile", "distance", "POT-07", None),
    "depth.interpret_grid": ("source_depth", "interpret_grid", "space", "POT-07", None),
    "sp.pde_forward": (
        "self_potential_pde",
        "sp_pde_forward",
        "space",
        "SP-04",
        "electrical",
    ),
    "sp.pde_source_fit": (
        "self_potential_pde",
        "fit_sp_pde_sources",
        "space",
        "SP-05",
        "electrical",
    ),
    "radiometry.fit_response": (
        "radiometric_calibration",
        "fit_radiometric_response",
        "calibration",
        "RAD-05",
        None,
    ),
    "radiometry.calibrated_concentrations": (
        "radiometric_calibration",
        "radiometric_concentrations",
        "channel",
        "RAD-07",
        None,
    ),
    "em.fit_complex_response": (
        "complex_calibration",
        "fit_complex_response",
        "frequency-calibration",
        "FDEM-03",
        None,
    ),
    "em.apply_complex_response": (
        "complex_calibration",
        "apply_complex_response",
        "frequency-calibration",
        "FDEM-08",
        None,
    ),
    "regional.elastic_flexure": (
        "flexure",
        "thin_plate_flexure",
        "space-wavenumber",
        "REG-03",
        None,
    ),
    "regional.elastic_thickness_scan": (
        "flexure",
        "scan_elastic_thickness",
        "space-wavenumber",
        "REG-03",
        None,
    ),
    "fdem.3d_forward": (
        "fdem_3d",
        "fdem_3d_forward",
        "frequency-space",
        "FDEM-07",
        "em",
    ),
    "fdem.3d_zone_fit": (
        "fdem_3d",
        "fit_fdem_3d_zones",
        "frequency-space",
        "FDEM-07",
        "em",
    ),
    "radiometry.paired_radon": (
        "radiometric_radon",
        "paired_detector_radon",
        "time",
        "RAD-04",
        None,
    ),
    "borehole.read_las": (
        "well_log_io",
        "read_las_text",
        "depth",
        "BORE-01",
        "borehole",
    ),
    "borehole.update_las": (
        "well_log_io",
        "update_las_curves",
        "depth",
        "BORE-01",
        "borehole",
    ),
    "electrical.pde_forward": (
        "electrical_pde",
        "electrical_forward",
        "space",
        "ERT-07",
        "electrical",
    ),
    "electrical.pde_inverse": (
        "electrical_pde",
        "invert_electrical",
        "space",
        "ERT-06",
        "electrical",
    ),
    "waveform.bandpass": (
        "waveform_processing",
        "trace_bandpass",
        "time-frequency",
        "SEIS-03",
        None,
    ),
    "gpr.dewow": ("waveform_processing", "dewow", "time", "GPR-02", None),
    "gpr.background": (
        "waveform_processing",
        "remove_trace_background",
        "time-space",
        "GPR-03",
        None,
    ),
    "gpr.time_zero": (
        "waveform_processing",
        "correct_time_zero",
        "time",
        "GPR-02",
        None,
    ),
    "gpr.time_gain": (
        "waveform_processing",
        "explicit_time_gain",
        "time",
        "GPR-04",
        None,
    ),
    "gpr.hyperbola_fit": (
        "waveform_processing",
        "fit_diffraction_hyperbola",
        "time-space",
        "GPR-05",
        None,
    ),
    "seismic.nmo_stack": (
        "waveform_processing",
        "normal_moveout",
        "time-space",
        "SEIS-06",
        None,
    ),
    "seismic.sta_lta_picks": (
        "waveform_processing",
        "sta_lta_picks",
        "time",
        "SEIS-04",
        None,
    ),
    "passive.hvsr": (
        "waveform_processing",
        "hvsr_windows",
        "frequency",
        "PASS-02",
        None,
    ),
    "passive.phase_velocity": (
        "waveform_processing",
        "phase_velocity_image",
        "frequency-space",
        "PASS-05",
        None,
    ),
    "sp.prescribed_source_forward": (
        "self_potential",
        "prescribed_source_potential",
        "space",
        "SP-04",
        None,
    ),
    "sp.current_inverse": (
        "self_potential",
        "invert_source_currents",
        "space",
        "SP-05",
        None,
    ),
    "sp.reference_network": (
        "self_potential",
        "adjust_reference_network",
        "electrode-network",
        "SP-02",
        None,
    ),
    "borehole.trajectory": (
        "borehole",
        "minimum_curvature_trajectory",
        "depth-space",
        "BORE-03",
        None,
    ),
    "borehole.depth_qc": ("borehole", "log_depth_qc", "depth", "BORE-02", None),
    "inversion.linear_ensemble": (
        "advanced_statistics",
        "linear_gaussian_ensemble",
        "model-parameter",
        "INV-02",
        None,
    ),
    "spectra.matched_layers": (
        "advanced_statistics",
        "matched_layer_filters",
        "spatial-frequency",
        "POT-05",
        None,
    ),
    "regional.admittance_coherence": (
        "advanced_statistics",
        "profile_admittance_coherence",
        "spatial-frequency",
        "REG-04",
        None,
    ),
    "radiometry.mnf": (
        "radiometric_spectra",
        "mnf_denoise",
        "photon-energy/spectra",
        "RAD-03",
        None,
    ),
    "tem.waveform_forward": (
        "layered_em",
        "tem_waveform_layered",
        "time",
        "TEM-02",
        "em",
    ),
    "tem.fit_conductivity": (
        "layered_em",
        "fit_tem_conductivity",
        "time",
        "TEM-05",
        "em",
    ),
    "tem.stack_transients": (
        "transient_processing",
        "stack_transients",
        "time",
        "TEM-01",
        None,
    ),
    "tem.integrate_recorded_gates": (
        "transient_processing",
        "gate_recorded_transients",
        "time",
        "TEM-01",
        None,
    ),
    "potential.equivalent_sources": (
        "equivalent_sources",
        "equivalent_source_predict",
        "space",
        "POT-08",
        "prisms",
    ),
    "spectra.grid_psd": (
        "spectral_analysis",
        "grid_power_spectrum",
        "spatial-frequency",
        "POT-02",
        None,
    ),
    "spectra.directional_bins": (
        "spectral_analysis",
        "binned_power_spectrum",
        "spatial-frequency",
        "POT-02",
        None,
    ),
    "spectra.depth_fit": (
        "spectral_analysis",
        "fit_spectral_depth",
        "spatial-frequency",
        "POT-01",
        None,
    ),
    "spectra.wiener_inverse": (
        "spectral_analysis",
        "wiener_inverse_transfer",
        "spatial-frequency",
        "POT-04",
        None,
    ),
    "gravity.tensor_invariants": (
        "potential_tensors",
        "tensor_invariants",
        "space",
        "POT-03",
        None,
    ),
    "gravity.rotate_tensor": (
        "potential_tensors",
        "rotate_tensor",
        "space",
        "GRAV-03",
        None,
    ),
    "gravity.prism_tensor": (
        "potential_tensors",
        "prism_gravity_tensor",
        "space",
        "GRAV-03",
        "prisms",
    ),
    "gravity.network_adjustment": (
        "gravity_network",
        "adjust_gravity_network",
        "time/station-network",
        "GRAV-07",
        None,
    ),
    "gravity.density_fit": (
        "gravity_network",
        "fit_bouguer_density",
        "space",
        "GRAV-06",
        None,
    ),
    "radiometry.energy_calibration": (
        "radiometric_spectra",
        "fit_energy_calibration",
        "photon-energy",
        "RAD-01",
        None,
    ),
    "radiometry.energy_rebin": (
        "radiometric_spectra",
        "energy_rebin",
        "photon-energy",
        "RAD-01",
        None,
    ),
    "radiometry.nasvd": (
        "radiometric_spectra",
        "poisson_nasvd",
        "photon-energy/spectra",
        "RAD-02",
        None,
    ),
    "radiometry.integrate_windows": (
        "radiometric_spectra",
        "integrate_energy_windows",
        "photon-energy",
        "RAD-06",
        None,
    ),
    "radiometry.covariance_transform": (
        "radiometric_spectra",
        "linear_covariance_transform",
        "measurement-space",
        "RAD-07",
        None,
    ),
    "radiometry.full_spectrum_fit": (
        "radiometric_spectra",
        "fit_full_spectrum",
        "photon-energy",
        "RAD-06",
        None,
    ),
    "electrical.validate_abmn": (
        "electrical",
        "validate_abmn",
        "electrode-geometry",
        "ERT-01",
        None,
    ),
    "electrical.geometric_factor": (
        "electrical",
        "geometric_factor",
        "electrode-geometry",
        "ERT-02",
        None,
    ),
    "electrical.apparent_resistivity": (
        "electrical",
        "apparent_resistivity",
        "electrode-geometry",
        "ERT-02",
        None,
    ),
    "electrical.reciprocal_qc": (
        "electrical",
        "reciprocal_errors",
        "electrode-network",
        "ERT-03",
        None,
    ),
    "electrical.layered_forward": (
        "layered_electrical",
        "dc_layered",
        "electrode-geometry",
        "ERT-05",
        "electrical",
    ),
    "electrical.fit_resistivity": (
        "layered_electrical",
        "fit_dc_resistivity",
        "electrode-geometry",
        "ERT-05",
        "electrical",
    ),
    "ip.integrated_chargeability": (
        "electrical",
        "integrated_chargeability",
        "time",
        "IP-01",
        None,
    ),
    "sip.cole_cole_resistivity": (
        "electrical",
        "cole_cole_resistivity",
        "frequency",
        "IP-06",
        None,
    ),
    "sip.fit_cole_cole": (
        "dispersive_ip",
        "fit_cole_cole_spectrum",
        "frequency",
        "IP-06",
        None,
    ),
    "ip.stack_decay": ("ip_stacking", "stack_ip_decay", "space-time", "IP-01", None),
    "ip.fit_stack": ("ip_stacking", "fit_ip_stack", "space-time", "IP-06", None),
    "ip.waveform_decay": ("ip_waveform", "ip_waveform_decay", "time", "IP-01", None),
    "ip.fit_waveform": ("ip_waveform", "fit_ip_waveform", "time", "IP-01", None),
    "ip.spatial_waveform": (
        "ip_waveform",
        "spatial_ip_waveform",
        "space-time",
        "IP-06",
        None,
    ),
    "ip.fit_spatial_waveform": (
        "ip_waveform",
        "fit_spatial_ip_waveform",
        "space-time",
        "IP-06",
        None,
    ),
    "ip.cole_cole_decay": ("dispersive_ip", "ip_decay_forward", "time", "IP-01", None),
    "ip.fit_decay": ("dispersive_ip", "fit_ip_decay", "time", "IP-01", None),
    "ip.sensitivity": (
        "electrical_pde",
        "ip_sensitivity",
        "space",
        "IP-06",
        "electrical",
    ),
    "ip.dispersive_forward": (
        "dispersive_ip",
        "dispersive_ip_forward",
        "space-time-frequency",
        "IP-06",
        None,
    ),
    "ip.dispersive_inverse": (
        "dispersive_ip",
        "fit_dispersive_ip",
        "space-time-frequency",
        "IP-06",
        None,
    ),
    "fdem.layered_forward": (
        "layered_em",
        "fdem_layered",
        "frequency",
        "FDEM-04",
        "em",
    ),
    "fdem.fit_conductivity": (
        "layered_em",
        "fit_fdem_conductivity",
        "frequency",
        "FDEM-05",
        "em",
    ),
    "tem.stepoff_forward": (
        "layered_em",
        "tem_stepoff_layered",
        "time",
        "TEM-04",
        "em",
    ),
    "tem.gate_average": ("layered_em", "tem_gate_average", "time", "TEM-03", "em"),
    "mt.layered_forward": (
        "magnetotellurics",
        "layered_impedance",
        "frequency",
        "MT-07",
        None,
    ),
    "mt.apparent_resistivity_phase": (
        "magnetotellurics",
        "apparent_resistivity_phase",
        "frequency",
        "MT-02",
        None,
    ),
    "mt.impedance_units": (
        "magnetotellurics",
        "mt_units_to_ohms",
        "frequency",
        "MT-02",
        None,
    ),
    "mt.phase_tensor": ("magnetotellurics", "phase_tensor", "frequency", "MT-05", None),
    "mt.fit_resistivity": (
        "magnetotellurics",
        "fit_layered_resistivity",
        "frequency",
        "MT-07",
        None,
    ),
    "inversion.linear_resolution": (
        "inversion_diagnostics",
        "linear_resolution",
        "model-parameter",
        "INV-01",
        None,
    ),
    "inversion.stochastic_resolution": (
        "matrix_free_resolution",
        "stochastic_linear_resolution",
        "model-parameter",
        "INV-01",
        None,
    ),
    "inversion.point_spread": (
        "matrix_free_resolution",
        "linear_point_spread",
        "model-parameter",
        "INV-01",
        None,
    ),
    "inversion.spatial_constraints": (
        "spatial_constraints",
        "spatial_property_constraints",
        "space/model-parameter",
        "INV-01",
        None,
    ),
    "inversion.recovery_metrics": (
        "recovery_metrics",
        "model_recovery_metrics",
        "space/model-parameter",
        "INV-01",
        None,
    ),
    "gravity.prism_density_fit": (
        "prism_inversion",
        "fit_prism_density",
        "space/model-parameter",
        "INV-01",
        "prisms",
    ),
    "magnetic.prism_magnetization_fit": (
        "prism_inversion",
        "fit_prism_magnetization",
        "space/model-parameter",
        "INV-01",
        "prisms",
    ),
    "inversion.reference_doi": (
        "inversion_diagnostics",
        "reference_model_doi",
        "model-parameter",
        "INV-01",
        None,
    ),
}


def list_operations():
    """Return implemented API metadata without importing optional engines.

    Existing legacy kernels are still accessible directly. This registry
    covers the new expansion and selected historical source-depth methods,
    not the complete historical Core inventory.
    """
    return [
        {
            "id": key,
            "module": "terraworkbench_core." + value[0],
            "function": value[1],
            "domain": value[2],
            "related_backlog_candidate": value[3],
            "optional_extra": value[4],
            "validation": "synthetic_tests_only",
            "backlog_coverage": "partial",
        }
        for key, value in _OPERATIONS.items()
    ]


def operation_info(operation_id):
    """Function contract for the future per-process information panel."""
    if operation_id not in _OPERATIONS:
        raise ValueError("Unknown implemented operation: " + str(operation_id))
    metadata = next(row for row in list_operations() if row["id"] == operation_id)
    module = importlib.import_module(
        "." + metadata["module"].rsplit(".", 1)[1], __package__
    )
    function = getattr(module, metadata["function"])
    return {
        **metadata,
        "signature": str(inspect.signature(function)),
        "documentation": inspect.getdoc(function),
        "base_libraries": {"numpy": np.__version__, "scipy": scipy.__version__},
        "optional_engine": "Harmonica 0.7.x + Numba"
        if metadata["module"].endswith(".adaptive_terrain")
        else {
            "em": "SimPEG 0.25.x",
            "electrical": "SimPEG 0.25.x",
            "prisms": "Harmonica 0.7.x",
            "borehole": "lasio 0.31/0.32",
            "structure": "scikit-image",
            "geomagnetism": "ppigrf",
            "coordinates": "pyproj",
        }.get(metadata["optional_extra"]),
    }


def _input_digest(parameters):
    digest = hashlib.sha256()

    def visit(value):
        if isinstance(value, np.ndarray):
            if np.ma.isMaskedArray(value) and np.any(np.ma.getmask(value)):
                raise ValueError(
                    "Masked input cannot be hashed without explicit NoData handling"
                )
            if value.dtype.hasobject:
                raise ValueError("Object arrays cannot be hashed reproducibly")
            digest.update(b"array")
            digest.update(value.dtype.str.encode())
            digest.update(str(value.shape).encode())
            # Bounded copies even for noncontiguous large survey arrays.
            for chunk in np.nditer(
                value,
                flags=["external_loop", "buffered", "zerosize_ok"],
                order="C",
                buffersize=65536,
            ):
                digest.update(chunk.tobytes())
        elif isinstance(value, np.generic):
            visit(value.item())
        elif isinstance(value, dict):
            digest.update(b"dict{")
            for key in sorted(value, key=lambda k: (type(k).__name__, str(k))):
                visit(key)
                visit(value[key])
            digest.update(b"}")
        elif isinstance(value, (tuple, list)):
            digest.update(type(value).__name__.encode() + b"[")
            for item in value:
                visit(item)
            digest.update(b"]")
        elif callable(value):
            # Runtime cancellation cannot be replayed from this digest.
            digest.update(b"runtime-callback")
        elif value is None or isinstance(value, (str, int, float, bool, complex)):
            digest.update(type(value).__name__.encode() + b":")
            if isinstance(value, complex):
                visit(value.real)
                visit(value.imag)
            elif isinstance(value, float) and not np.isfinite(value):
                # Valid missing data in real-valued Python lists must behave
                # like NaN-containing arrays. Hash tagged text, never emit
                # nonstandard JSON numbers in the provenance envelope.
                digest.update(str(value).encode("ascii"))
            else:
                digest.update(
                    json.dumps(value, ensure_ascii=True, allow_nan=False).encode()
                )
            digest.update(b";")
        else:
            raise TypeError(
                "Unsupported provenance input type: " + type(value).__name__
            )

    visit(parameters)
    return digest.hexdigest()


def run_operation(operation_id, **parameters):
    """Execute an implemented operation with input/source hashes and versions.

    No files are created and no data values enter the provenance envelope.
    Caller owns result storage. A hash identifies exact explicit inputs, not
    omitted defaults, external files, callback state or the entire dependency
    tree. Failed/cancelled operations raise; solver success=False is explicitly
    recorded as not_converged, never a completed numerical solve.
    """
    info = operation_info(operation_id)
    module = importlib.import_module(
        "." + info["module"].rsplit(".", 1)[1], __package__
    )
    function = getattr(module, info["function"])
    inspect.signature(function).bind(**parameters)
    input_hash = _input_digest(parameters)
    started = datetime.now(timezone.utc).isoformat()
    source = Path(inspect.getsourcefile(function))
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    result = function(**parameters)
    converged = (
        bool(result["success"])
        if isinstance(result, dict) and "success" in result
        else None
    )
    libraries = dict(info["base_libraries"])
    engine_package = {
        "em": "simpeg",
        "electrical": "simpeg",
        "prisms": "harmonica",
        "borehole": "lasio",
        "structure": "scikit-image",
        "geomagnetism": "ppigrf",
        "coordinates": "pyproj",
    }.get(info["optional_extra"])
    if engine_package is not None:
        libraries[engine_package] = version(engine_package)
    if info["module"].endswith(".adaptive_terrain"):
        libraries["numba"] = version("numba")
    return {
        "result": result,
        "provenance": {
            "schema_version": 1,
            "operation_id": operation_id,
            "status": "not_converged" if converged is False else "completed",
            "solver_converged": converged,
            "started_utc": started,
            "finished_utc": datetime.now(timezone.utc).isoformat(),
            "input_sha256": input_hash,
            "input_hash_scheme": "typed-tree-sha256-v2",
            "source_sha256": source_hash,
            "source_module": info["module"],
            "python": platform.python_version(),
            "libraries": libraries,
            "optional_engine": info["optional_engine"],
            "engine_version": result.get("engine_version")
            if isinstance(result, dict)
            else None,
            "domain": info["domain"],
            "validation": info["validation"],
            "hash_scope": "explicit parameters and implementation module, not transitive dependencies",
        },
    }
