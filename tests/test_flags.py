"""The tpx3dump flag table: argv construction and value checks."""

from luna_tpx3_gui.functions.flags import (FLAGS, flag_args, flag_bits,
                                           flag_problems)


def test_unset_flags_pass_nothing():
    assert flag_args({}) == []
    assert flag_args({f.key: "" for f in FLAGS}) == []


def test_values_switches_and_choices():
    args = flag_args({"eps_t": "200 ns", "layout": "quad", "raw_only": True,
                      "disable_clustering": False, "log_level": ""})
    assert args == ["--layout", "quad", "--eps-t", "200ns", "--raw-only"]


def test_switch_choice_needs_its_box():
    off = {"tof_tdc_reference_on": False, "tof_tdc_reference": "TDC2Falling"}
    assert flag_args(off) == []
    on = dict(off, tof_tdc_reference_on=True)
    assert flag_args(on) == ["--tof-tdc-reference", "TDC2Falling"]


def test_paths_are_translated():
    bits = flag_bits({"timewalk_file": r"C:\runs\tw.hdf5"},
                     translate=lambda p: "/mnt/c/runs/tw.hdf5")
    assert bits == [["--timewalk-file", "/mnt/c/runs/tw.hdf5"]]


def test_problems():
    assert flag_problems({"eps_t": "100ns", "time_bin_interval": "0.495s",
                          "eps_s": "1.5", "num_time_bins": "3"}) == []
    bad = flag_problems({"eps_t": "100", "time_bin_interval": "500 parsecs",
                         "num_time_bins": "3.5", "eps_s": "one"})
    assert len(bad) == 4
    assert any(p.startswith("--eps-t needs a number with a unit") for p in bad)


def test_keys_and_flags_are_unique():
    assert len({f.key for f in FLAGS}) == len(FLAGS)
    assert len({f.flag for f in FLAGS}) == len(FLAGS)
