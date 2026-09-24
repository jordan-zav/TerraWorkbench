"""Exercise the ASC-to-raster runner without private survey data."""

from argparse import Namespace
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
sys.path.insert(0, str(Path(os.environ["QGIS_PREFIX_PATH"]) / "python/plugins"))

from process_archaeology_asc import process
from TerraWorkbench.provider import TerraWorkbenchProvider
from qgis.core import QgsApplication
from processing.core.Processing import Processing


def main():
    app = QgsApplication([], False)
    app.initQgis()
    Processing.initialize()
    provider = TerraWorkbenchProvider()
    QgsApplication.processingRegistry().addProvider(provider)
    with tempfile.TemporaryDirectory(prefix="tw_asc_") as folder:
        root = Path(folder)
        source = root / "survey.asc"
        lines = ["Raw track data", "x\ty\tmag\tline\tsensor\ttime"]
        for line in range(4):
            for sensor in range(2):
                for step in range(16):
                    x, y = 500000 + line * 2 + sensor * .5, 4600000 + step * .5
                    lines.append(f"{x}\t{y}\t{10 + line * 2 + sensor - step}\t{line:03d}\t{sensor}\t{step}")
        source.write_text("\n".join(lines) + "\n", encoding="utf-8")
        args = Namespace(source=source, output=root / "output", x="x", y="y", value="mag",
                         line="line", sensor="sensor", unit="nT", source_crs="EPSG:32617",
                         target_crs="EPSG:32617", cell_size=.25, search_radius=.55, median_radius=.5)
        report = process(args)
        assert report["passed"] and report["observations"] == 128
        assert report["lines"] == 4 and len(report["sensors"]) == 2
        assert report["source_kind"] == "raw_track_export"
        assert report["text_layout"]["header_row"] == 2
        assert report["text_layout"]["data_row"] == 3
        assert report["line_sensor_pairs"] == 8
        assert report["missing_cells"] > 0 and len(report["products"]) == 7
        try:
            process(args)
        except ValueError as error:
            assert "never overwritten" in str(error)
        else:
            raise AssertionError("An existing output directory was overwritten")
        args.output = root / "corrected"
        args.despike_window, args.despike_threshold = 7, 6.
        args.time_channel, args.time_scale, args.max_gap_seconds = "time", 1., 2.
        corrected = process(args)
        assert corrected["passed"] and corrected["gridded_rows"] == 80
        assert corrected["excluded_null_rows"] == 48
        assert corrected["corrections"]["recipe"]["statistics"]["segments"] == 8
    print("PASS: complete ASC import, point bridge, seven rasters, numerical checks and overwrite protection")


if __name__ == "__main__":
    main()
