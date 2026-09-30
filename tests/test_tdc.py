"""TDC deduplication, tagging, and the HDF5 write/read round trip."""

import pytest

from luna_tpx3_gui.functions import tdc

np = pytest.importorskip("numpy")

EVENT_DTYPE = [("tdc_type", "u1"), ("trigger_count", "<u2"), ("timestamp", "<u8")]


def quad_events():
    """Two TDC1Rising and one TDC1Falling edge, each repeated by four chips."""
    edges = [(1, 1, 1000), (2, 1, 1500), (1, 2, 3000)]
    return np.array(edges * 4, dtype=EVENT_DTYPE)


def test_dedup_collapses_chip_repeats():
    ev = tdc.read_tdc_events({tdc.TDC_DATASET: quad_events()}, np)
    assert len(ev) == 3
    assert list(ev["timestamp"]) == [1000, 1500, 3000]


def test_missing_dataset():
    assert tdc.read_tdc_events({}, np) is None


def test_reference_edges():
    ev = tdc.read_tdc_events({tdc.TDC_DATASET: quad_events()}, np)
    assert len(tdc.tdc_reference_edges(ev, "TDC1Rising", np)) == 2
    assert len(tdc.tdc_reference_edges(ev, tdc.TDC_REFERENCE_ANY, np)) == 3
    with pytest.raises(ValueError):
        tdc.tdc_reference_edges(ev, "TDC9Sideways", np)


def test_tagging():
    ev = tdc.read_tdc_events({tdc.TDC_DATASET: quad_events()}, np)
    edges = tdc.tdc_reference_edges(ev, "TDC1Rising", np)
    times = np.array([500, 1000, 2000, 3500], dtype="<u8")
    cols = tdc.tag_times_with_tdc(times, edges, np)
    # Before the first edge: the tpx3dump-style -1 sentinel.
    assert cols["tdc_index"][0] == tdc.TDC_UNSET
    assert cols["tdc_dt"][0] == tdc.TDC_UNSET
    # Exactly on an edge belongs to that edge (side="right").
    assert cols["tdc_index"][1] == 0 and cols["tdc_dt"][1] == 0
    assert cols["tdc"][2] == 1000 and cols["tdc_dt"][2] == 1000
    assert cols["tdc_index"][3] == 1 and cols["tdc_trigger"][3] == 2
    assert cols["tdc_type"][3] == 1


def test_hdf5_round_trip(tmp_path):
    h5py = pytest.importorskip("h5py")
    pytest.importorskip("pandas")

    path = tmp_path / "run.hdf5"
    clusters = np.zeros(4, dtype=[("ctoa", "<u8"), ("size", "<u2")])
    clusters["ctoa"] = [500, 1000, 2000, 3500]
    with h5py.File(path, "w") as f:
        f.create_dataset(tdc.TDC_DATASET, data=quad_events())
        f.create_dataset("Clusters", data=clusters)

    res = tdc.add_tdc_columns(path, "TDC1Rising")
    assert res["ClustersTDC"]["rows"] == 4
    assert res["ClustersTDC"]["tagged"] == 3

    df = tdc.read_with_tdc(path, "Clusters")
    assert df.attrs["tdc_from_file"] is True
    assert list(df["tdc_index"]) == [-1, 0, 0, 1]
    assert df["tdc_dt_s"].isna().iloc[0]

    edges = tdc.read_tdcs(path)
    assert list(edges["tdc_type"]) == ["TDC1Rising", "TDC1Falling", "TDC1Rising"]

    # Rewriting its own columns is allowed; clobbering someone else's is not.
    tdc.add_tdc_columns(path, "TDC1Rising")
    with h5py.File(path, "r+") as f:
        f["ClustersTDC"].attrs["written_by"] = "someone else"
    with pytest.raises(ValueError, match="not written by this GUI"):
        tdc.add_tdc_columns(path, "TDC1Rising")
