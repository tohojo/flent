Introduction
============

Flent is a wrapper around *netperf* and similar tools to run predefined
tests and aggregate and plot the results. It defines several tests that
can be run against one or more hosts, primarily targeted at testing for
the presence of bufferbloat under various conditions.

The aggregated data is saved in (gzipped) JSON format for later
processing and/or import into other tools. The JSON format is documented
below.

Apart from the JSON format, the data can be output as csv values, emacs
org mode tables or plots. Each test can specify several different plots,
including time-series plots of the values against each other, as well as
CDF plots of (e.g.) ping times.

Plots can be output to the formats supported by matplotlib by specifying
the output filename with :option:`-o` *output.{png,ps,pdf,svg}*. If no output
file is specified, the plot is diplayed using matplotlib’s interactive
plot browser, which also allows saving of the output (in .png format).

