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
file is specified, the plot is displayed using matplotlib’s interactive
plot browser, which also allows saving of the output (in .png format).

Requirements
------------
Flent runs on Python, versions 2.7+ and 3.3+. Plotting requires a functional
:py:mod:`matplotlib` installation (but everything else can run without
:py:mod:`matplotlib`). For the interactive plot viewer, a graphical display (and
suitably configured :py:mod:`matplotlib`) is required.

Most tests employ the :command:`netperf` benchmarking tool to run the tests.
Version 2.6 or higher is required, and netperf must be compiled with the
:command:`--enable-demo` option passed to :command:`./configure`. Some tests use
iperf in addition to, or instead of netperf. Both tools must be available in the
:envvar:`PATH`.

For ICMP ping measurements, the version of ping employed must support output
timestamping (the -D parameter to GNU ping). This is not supported by the BSD
and OSX versions of ping. As an alternative to the regular ping command, the
:command:`fping` utility (see http://fping.org) can be employed. In that case
fping must be version 3.5 or greater. Flent will attempt to detect the presence
of fping in the :envvar:`PATH` and check for support for the -D parameter. If
this check is successful, :command:`fping` will be employed for ping data,
otherwise the system ping will be used.

The :command:`irtt` tool is highly recommended for UDP measurements. See
https://github.com/peteheist/irtt. Flent will automatically detect if irtt is
available in the :envvar:`PATH` and use it if it is detected. Note that the
server component of irtt needs to be running on the target host(s) as well.
