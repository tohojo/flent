netperf-wrapper
===============

Python wrapper to run multiple simultaneous netperf/iperf/ping instances and
aggregate the results.

Tests are specified as .ini config files, and various parsers for tool output
are supplied. At the moment, parsers for netperf in -D mode, iperf in csv mode
and ping/ping6 in -D mode are supplied, as well as a generic parser for commands
that just outputs a single number.

Several tests can be run in parallel and, provided they output timestamped
values, (which netperf ping and iperf do, the latter with a small patch,
available in the misc/ directory), the test data points can be aligned with each
other in time, interpolating differences between the actual measurement points.
This makes it possible to graph (e.g.) ping times before, during and after a
link is loaded.

An alternative run mode is running several iterated tests (which each output one
data point, e.g. netperf tests not in -D mode), and outputting the results of
these several runs.

Output is either simple Python pretty-printed output (which can be eval'ed back
into a Python data structure), org mode tables, or plots. The latter requires a
functioning matplotlib installation.

Documentation is relatively sparse at the moment, but try having a look at the
.ini files in the tests directory and running the main script
(netperf-wrapper.py) with -h.
