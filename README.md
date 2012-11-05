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
functioning matplotlib installation. You specify which output format with -f {org,plot} and for plot formats you specify -o output.{png,ps,pdf,svg}.

Documentation is relatively sparse at the moment, but try having a look at the
.ini files in the tests directory and running the main script
(netperf-wrapper.py) with -h.

## Saving test data for later plotting ##

Reading back in test data is now supported. First, run the tests with the
'pprint' formatter and save the output in a file (i.e. `python2
netperf-wrapper.py -f pprint -o test.data <test>`), then read it back in using
the -i parameter. This bypasses the actual running of the tests, but still
requires a test config file. So for example, the data can be plotted by using
`python2 netperf-wrapper.py -f plot -i test.data <test>` (with the same test
name as was used to generate the data).

Note that this functionality relies on the data to be eval()'ed by the python
interpreter, so don't under any circumstances use untrusted input data, as it
can in principle do arbitrary bad things.
