"""Output naming: sanitising, template rendering, metadata, migration."""

import json

from luna_tpx3_gui.functions.naming import (DEFAULT_TEMPLATE, measurement_context,
                                            migrate_template, render_name, sanitize)


def test_sanitize():
    assert sanitize("DCR 0V gain") == "DCR-0V-gain"
    assert sanitize("  a/b\\c:d  ") == "a-b-c-d"
    assert sanitize("") == ""
    assert sanitize("---") == ""


def test_render_drops_missing_and_collapses_separators():
    ctx = {"stem": "fCqk_000000", "date": "2026-08-07", "time": "", "comment": ""}
    assert render_name("{date}_{time}_{comment}_{stem}", ctx) == "2026-08-07_fCqk_000000"


def test_render_unknown_placeholder_and_bad_template():
    ctx = {"stem": "s"}
    assert render_name("{nope}_{stem}", ctx) == "s"
    assert render_name("{unclosed", ctx) == "s"       # format error -> stem
    assert render_name("", ctx) == "s"


def test_measurement_context_asi_layout(tmp_path):
    meas = tmp_path / "data_DCR_07.08.2026" / "Measurement_Aug_07_2026_12h52m45s"
    raw = meas / "raw"
    raw.mkdir(parents=True)
    tpx3 = raw / "fCqk_000000.tpx3"
    tpx3.write_bytes(b"")
    meta = {
        "StartDateTime": "2026-08-07T12:52:45.123",
        "StopDateTime": "2026-08-07T12:52:55.123",
        "CommentAtTimeOfMeasurement": "DCR 0V gain",
        "NumberOfFrames": 100,
        "Detector": {"Config": {"BiasVoltage": 50},
                     "Layout": {"Width": 256, "Height": 256}},
    }
    (meas / "measurement_metadata.json").write_text(json.dumps(meta), encoding="utf-8")

    ctx = measurement_context(tpx3)
    assert ctx["stem"] == "fCqk_000000"
    assert ctx["measurement"] == meas.name
    assert ctx["campaign"] == "data_DCR_07.08.2026"
    assert ctx["date"] == "2026-08-07"
    assert ctx["time"] == "12-52-45"          # no colons: Windows filenames
    assert ctx["comment"] == "DCR-0V-gain"
    assert ctx["duration"] == "10s"
    assert ctx["bias"] == "50"
    assert ctx["size"] == "256x256"
    assert render_name(DEFAULT_TEMPLATE, ctx) == "2026-08-07_12-52-45_DCR-0V-gain_fCqk_000000"


def test_measurement_context_without_metadata(tmp_path):
    tpx3 = tmp_path / "x.tpx3"
    tpx3.write_bytes(b"")
    ctx = measurement_context(tpx3)
    assert render_name(DEFAULT_TEMPLATE, ctx) == "x"


def test_migrate_template():
    cfg = {"template": "{stem}"}
    assert migrate_template(cfg) is True
    assert cfg["template"] == DEFAULT_TEMPLATE
    assert migrate_template(cfg) is False          # runs once

    mine = {"template": "{campaign}_{stem}"}
    assert migrate_template(mine) is False
    assert mine["template"] == "{campaign}_{stem}"  # a deliberate choice stays
