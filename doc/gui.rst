The Flent GUI
=============

Flent comes equipped with a GUI to browse and plot previously captured datasets.
The GUI requires PyQt4; if this is installed, it can be launched with the
:option:`--gui` parameter, or by launching the ``flent-gui`` binary.
Additionally, if Flent is launched without parameters and without a controlling
terminal, the GUI will be launched automatically.

The GUI can be used for interactively plotting previously captured datasets, and
makes it easy to compare results from several test runs. It presents a tabbed
interface to graphs of data files, allows dynamic configuration of plots, and
includes a metadata browser. For each loaded data file, additional data files
can be loaded and added to the plot, similar to what happens when specifying
multiple input files for plotting on the command line. A checkbox controls
whether the added data files are added as separate entries to the plot, or
whether they are used for scaling the output (mirroring the
:option:`--scale-mode`) command line switch.

The GUI also incorporates matplotlib’s interactive browsing toolbar, enabling
panning and zooming of the plot area, dynamic configuration of plot and axis
parameters and labels and saving the plots to file. The exact dynamic features
supported depends on the installed version of matplotlib.
