"""Safe recipe reuse preserves original channels and exact reviewed inputs."""

import pyarrow as pa
import pytest

from terraworkbench_core.channel_filters import ChannelFilterOptions
from terraworkbench_core.survey_store import SurveyStore
from terraworkbench_core.survey_recipes import prepare_channel_step


@pytest.fixture
def survey(tmp_path):
    source = tmp_path / "survey.csv"
    source.write_text(
        "line,signal,base\n" + "".join(f"A,{i + 100},5\n" for i in range(30)),
        encoding="utf-8",
    )
    store = SurveyStore(tmp_path / "project", create=True)
    database = store.import_file(source)
    store.derive(database, "corrected", 'c("signal") - c("base")', "nT")
    return store, database


def node_for(store, database, name):
    graph = store.channel_pipeline(database, name)
    return graph["nodes"][graph["root"]]


def test_formula_reuse_with_renamed_inputs(survey):
    store, database = survey
    node = node_for(store, database, "corrected")
    store.rename_channel(database, "signal", "magnetic_signal", "nT")
    plan = prepare_channel_step(store, database, node)
    assert "magnetic_signal" in plan["expression"]
    store.derive(
        database,
        "replayed",
        plan["expression"],
        "nT",
        expected_versions=plan["expected_versions"],
        reused_from=node["id"],
        new_channel_only=True,
    )
    data = pa.Table.from_batches(
        list(store.batches(database, ["corrected", "replayed"]))
    ).to_pydict()
    assert data["corrected"] == data["replayed"]
    assert (
        node_for(store, database, "replayed")["provenance"]["reused_from_version"]
        == node["id"]
    )


def test_reuse_refuses_newer_upstream_version(survey):
    store, database = survey
    store.filter_channel(
        database, "corrected", "smoothed", ChannelFilterOptions(group="line")
    )
    node = node_for(store, database, "smoothed")
    store.derive(database, "corrected", 'c("signal") - c("base") + 1', "nT")
    before = store.history(database)
    with pytest.raises(ValueError, match="refusing to substitute"):
        prepare_channel_step(store, database, node)
    assert store.history(database) == before


def test_filter_reuse_and_version_guard(survey):
    store, database = survey
    store.filter_channel(
        database, "corrected", "smoothed", ChannelFilterOptions(group="line")
    )
    node = node_for(store, database, "smoothed")
    plan = prepare_channel_step(store, database, node)
    store.filter_channel(
        database,
        plan["channel"],
        "smoothed_again",
        ChannelFilterOptions(**plan["parameters"]),
        expected_versions=plan["expected_versions"],
        reused_from=node["id"],
    )
    data = pa.Table.from_batches(
        list(store.batches(database, ["smoothed", "smoothed_again"]))
    ).to_pydict()
    assert data["smoothed"] == data["smoothed_again"]
    stale = dict(plan["expected_versions"])
    stale[plan["channel"]] = "not-the-reviewed-version"
    before = store.history(database)
    with pytest.raises(ValueError, match="versions changed"):
        store.filter_channel(
            database,
            plan["channel"],
            "must_not_exist",
            ChannelFilterOptions(**plan["parameters"]),
            expected_versions=stale,
        )
    assert store.history(database) == before
    assert "must_not_exist" not in {row["name"] for row in store.channels(database)}


def test_formula_guard_and_new_output_requirement(survey):
    store, database = survey
    plan = prepare_channel_step(store, database, node_for(store, database, "corrected"))
    before = store.history(database)
    with pytest.raises(ValueError, match="versions changed"):
        store.derive(database, "bad", plan["expression"], expected_versions={})
    with pytest.raises(ValueError, match="new channel"):
        store.derive(
            database,
            "corrected",
            plan["expression"],
            expected_versions=plan["expected_versions"],
            new_channel_only=True,
        )
    assert store.history(database) == before


def test_profile_comparison_is_row_aligned_and_unit_checked(survey):
    from terraworkbench_core.survey_explorer import compare_survey_profiles

    store, database = survey
    store.derive(database, "offset", 'c("corrected") + 2', "nT")
    before = store.history(database)
    result = compare_survey_profiles(
        store, database, "corrected", "offset", group="line"
    )
    assert result["difference"]["mean"] == 2
    assert result["difference"]["valid_rows"] == 30
    assert result["primary"]["rows"] == result["secondary"]["rows"]
    assert store.history(database) == before
    store.rename_channel(database, "offset", "offset", "mGal")
    with pytest.raises(ValueError, match="identical explicitly declared units"):
        compare_survey_profiles(store, database, "corrected", "offset")
