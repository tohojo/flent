Misc info
=========

Running Tests With The D-ITG Tool
---------------------------------

This version of flent has experimental support for running and parsing the
output of the D-ITG test tool (see
http://traffic.comics.unina.it/software/ITG/). Flent supports parsing the
one-way delay as measured by D-ITG. However, in order to do so, the data needs
to be collected at the receiver end, statistics extracted, and the result passed
back to flent on the sending side.

To perform this function, flent supports a control server which will listen to
XML-RPC requests, spawn an appropriate ITGRecv instance and, after the test is
done, parse its output and make it available for flent to retrieve. This control
server is available as a Python file that by default is installed in
:file:`/usr/share/doc/flent/misc`. It currently requires a patched version of
D-ITG v2.8.1. The patch is also included in the same directory.

Note that the D-ITG server is finicky and not designed with security in mind.
For this reason, the control server includes HMAC authentication to only allow
authenticated clients to run a test against the server; however there is
currently no support for enforcement of this in e.g. firewall rules. Please bear
this in mind when running a publicly reachable ITGRecv instance (with or without
the control server). Another security issue with the control server is that the
Python XML-RPC library by default is vulnerable to XML entity expansion attacks.
For this reason, it is highly recommended to install the :py:mod:`defusedxml`
library (available at https://pypi.python.org/pypi/defusedxml/) on the host
running the control server. The server will try to find the library on startup
and refuse to run if it is not available, unless explicitly told otherwise.

Due to the hassle of using D-ITG, it is recommended to install :command:`irtt`
instead and use that for VoIP tests.

Bugs
----

Under some conditions (such as severe bufferbloat), the UDP RTT measurements
done by netperf can experience packet loss to the extent that the test aborts
completely, which can cause missing data points for some measurement series.
The --socket-timeout feature can alleviate this, but requires a recent SVN
version of netperf to work. Flent tries to detect if netperf supports this
option and enables it for the UDP measurements if it does. Using :command:`irtt`
for UDP measurements is a way to alleviate this; Flent will automatically detect
the availability of irtt and use it if available.

Probably many other bugs. Please report any found to
https://github.com/tohojo/flent/issues and include the output of :option:`flent
--version<-V>` in the report. A debug log (as obtained with :option:`flent
--log-file<-L>`) is also often useful.
