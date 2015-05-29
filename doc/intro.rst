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

Invocation
----------

When run, flent must be supplied either (a) a test name and one or more
host names to connect to, or (b) one or more input files containing data
from previous runs to post-process.

Test names, hostnames and input file names can all be specified as
unqualified arguments, and flent will do its best to guess which is
which. For each argument, if it is an existing file, it is assumed to be
an input file, if it is the name of an existing test configuration it’s
assumed to be a test name, and if neither of those are true, it is
assumed to be a host name. The **-i** and **-H** switches can be used to
explicitly specify the interpretation of an argument.

