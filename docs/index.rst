.. Luna Tpx3 GUI documentation master file

Luna Tpx3 GUI
=============

A browse-and-batch Qt front end for ASI Luna's ``tpx3dump``: queue Timepix3
``.tpx3`` files, get sensibly named ``.hdf5`` files, and inspect the results.

.. important::

   Luna is **not included**. This is a GUI wrapper around the ``tpx3dump``
   command-line tool from your own licensed ASI Luna installation, which it
   runs unmodified as a subprocess. It cannot process ``.tpx3`` files without
   one.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   intro
   installation
   contribute
   license

.. toctree::
   :maxdepth: 2
   :caption: API (Qt-free core):

   modules

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
