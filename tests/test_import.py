"""Package-level checks: version, public API, and the Qt-free core."""

import subprocess
import sys


def test_version():
    import luna_tpx3_gui

    assert isinstance(luna_tpx3_gui.__version__, str)
    assert luna_tpx3_gui.__version__.count(".") >= 1


def test_public_tdc_api():
    import luna_tpx3_gui as g

    for name in ("read_tdcs", "add_tdc_columns", "read_with_tdc"):
        assert callable(getattr(g, name))


def test_core_does_not_import_qt():
    """functions/ must stay importable without PySide6 or a display.

    Run in a fresh interpreter, since another test may already have imported
    Qt into this one.
    """
    code = (
        "import sys, luna_tpx3_gui, luna_tpx3_gui.functions.backend, "
        "luna_tpx3_gui.functions.naming, luna_tpx3_gui.functions.tdc, "
        "luna_tpx3_gui.functions.config, luna_tpx3_gui.functions.plotting; "
        "assert not any(m.startswith('PySide6') for m in sys.modules), "
        "[m for m in sys.modules if m.startswith('PySide6')]"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
