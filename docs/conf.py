"""Sphinx configuration for Luna Tpx3 GUI documentation."""

import os
import sys

sys.path.insert(0, os.path.abspath("../src"))

from luna_tpx3_gui import __version__  # noqa: E402

project = "Luna Tpx3 GUI"
copyright = "2026, Sergei Kulkov"
author = "Sergei Kulkov"
release = __version__

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "myst_parser",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
html_static_path = ["_static"]
html_theme = "sphinx_rtd_theme"

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}

# The README's in-page links (#linux, #windows ...) become heading anchors.
myst_heading_anchors = 3

napoleon_google_docstring = True
napoleon_numpy_docstring = True
napoleon_include_init_with_doc = False
napoleon_include_private_with_doc = False
