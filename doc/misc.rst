Misc info
=========

Running Tests With The D-ITG Tool
---------------------------------

This version of flent has experimental support for running and parsing
the output of the D-ITG test tool (see
*http://traffic.comics.unina.it/software/ITG/*). Flent supports parsing
the one-way delay as measured by D-ITG. However, in order to do so, the
data needs to be collected at the receiver end, statistics extracted,
and the result passed back to flent on the sending side.

To perform this function, flent supports a control server which will
listen to XML-RPC requests, spawn an appropriate ITGRecv instance and,
after the test is done, parse its output and make it available for flent
to retrieve. This control server is available as a Python file that by
default is installed in */usr/share/doc/flent/misc*. It currently
requires a patched version of D-ITG v2.8.1. The patch is also included
in the same directory.

Note that the D-ITG server is finicky and not designed with security in
mind. For this reason, the control server includes HMAC authentication
to only allow authenticated clients to run a test against the server;
however there is currently no support for enforcement of this in e.g.
firewall rules. Please bear this in mind when running a publicly
reachable ITGRecv instance (with or without the control server). Another
security issue with the control server is that the Python XML-RPC
library by default is vulnerable to XML entity expansion attacks. For
this reason, it is highly recommended to install the ’defusedxml’
library (available at *https://pypi.python.org/pypi/defusedxml/*) on the
host running the control server. The server will try to find the library
on startup and refuse to run if it is not available, unless explicitly
told otherwise.

Examples
--------

Run the RRUL test against testserver.example.com::

  flent rrul testserver.example.com

This produces no output, but saves the result in a datafile named after the
current date and time (in gzipped JSON format).

Show an interactive plot of a previously run test, which stored the data in
*datafile.flent.gz* (requires a working matplotlib and a graphical display)::

  flent -f plot datafile.flent.gz

Combine multiple data files into one CDF plot::

  flent -p icmp_cdf *.flent.gz


Signals
-------

Flent will abort what it is currently doing on receiving a **SIGINT** -- this
includes killing all runners, cleaning up temporary files and shutting down as
gracefully as possible. Runners are killed with **SIGTERM** in this mode, and
their output is discarded. If a batch run is in progress, the current test will
be interrupted in this way, and the rest of the batch run is aborted. Previously
completed tests and their results are not aborted. Post-commands marked as
’essential’ will be run after the test is interrupted. Additionally, flent
converts **SIGTERM** into **SIGINT** internally and reacts accordingly.

Upon receiving a **SIGUSR1**, flent will try to gracefully abort the test it is
currently running, and parse the output of the runners to the extent that any
such output exists. That is, each runner will be killed by a **SIGINT**, which
will cause a graceful shutdown for at least ping and netperf (although netperf
running in *TCP_MAERTS* mode will bug out when interrupted like this, so
end-of-tests statistics will be missing). Flent will only react once to a
**SIGUSR1**, sending exactly one **SIGINT** to the active runners, then wait for
them to exit. This may take several seconds in the case of netperf. If the
runners for some reason fail to exit, flent will be stuck and will need to be
killed with **SIGINT**. If running in batch mode, **SIGUSR1** will only affect
the currently running test; subsequent tests will still be run.

Bugs
----

Under some conditions (such as severe bufferbloat), the UDP RTT measurements
done by netperf can experience packet loss to the extent that the test aborts
completely, which can cause missing data points for some measurement series.
The --socket-timeout feature can alleviate this, but requires a recent SVN
version of netperf to work. Flent tries to detect if netperf supports this
option and enables it for the UDP measurements if it does.

Probably many other bugs. Please report any found to
*https://github.com/tohojo/flent/issues* and include the output of
``flent`` :option:`--version` in the report.

Authors
-------

Flent is written and maintained by Toke Høiland-Jørgensen, with contributions
from Dave Taht and others.
