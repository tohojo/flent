Supplied Tests
==============

Test are supplied as Python files and can specify commands to run etc.
For a full list of the tests supported by flent, see the
:option:`--list-tests` option.

The Realtime Response Under Load (RRUL) test
--------------------------------------------

This test exists in a couple of variants and is a partial implementation of the
RRUL specification as written by Dave Taht (see
https://github.com/dtaht/deBloat/blob/master/spec/rrule.doc?raw=true). It works
by running RTT measurement using ICMP ping and UDP roundtrip time measurement,
while loading up the link with eight TCP streams (four downloads, four uploads).
This quite reliably saturates the measured link (wherever the bottleneck might
be), and thus exposes bufferbloat when it is present.

Simple TCP flow tests
---------------------

These tests combine a TCP flow (either in one direction, or both) with an ICMP
ping measurement. It’s a simpler test than RRUL, but in some cases the single
TCP flow can be sufficient to saturate the link.

UDP flood test
--------------

This test runs *iperf* configured to emit 100Mbps of UDP packets targeted at the
test host, while measuring RTT using ICMP ping. It is useful for observing
latency in the face of a completely unresponsive packet stream.

Test parameters
---------------

Some test parameters (set with :option:`--test-parameter`) affect the way tests
behave. These are:


.. envvar:: upload_streams
.. envvar:: download_streams

   These set the number of upload or download streams for the ``tcp_nup``,
   ``tcp_ndown`` and ``rrul_be_nflows`` tests.

.. envvar:: udp_bandwidth

   This sets the bandwidth of each UDP stream in the ``udp_*`` tests. The option
   is passed to ``iperf`` so can be in any syntax the iperf understands (e.g.
   ``20M`` for 20 Mbps).

.. envvar:: burst_length
.. envvar:: burst_ports
.. envvar:: burst_psize
.. envvar:: burst_tos

   These set the length, number of ports to use, packet size and TOS value for
   the packet bursts generated in the ``burst*`` tests.

.. envvar:: cpu_stats_hosts
.. envvar:: netstat_hosts
.. envvar:: qdisc_stats_hosts
.. envvar:: wifi_stats_hosts

   These set hostnames to gather statistics from from during the test. The
   hostnames are passed to SSH, so can be anything understood by SSH (including
   using ``username@host`` syntax, or using hosts defined in ``~/.ssh/config``).
   This will attempt to run remote commands on these hosts to gather the
   required statistics, so passwordless login has to be enabled for. Multiple
   hostnames can be specified, separated by commas.

   CPU stats and netstat output is global to the machine being connected to. The
   qdisc and WiFi stats need extra parameters to work. These are
   ``qdisc_stats_interfaces``, ``wifi_stats_interfaces`` and
   ``wifi_stats_stations``. The two former specify which interfaces to gather
   statistics from. These are paired with the hostnames, and so must contain the
   same number of elements (also comma-separated) as the ``_hosts`` variables.
   To specify multiple interfaces on the same host, duplicate the hostname. The
   ``wifi_stats_stations`` parameter specifies MAC addresses of stations to
   gather statistics for. This list is the same for all hosts, but only stations
   present in debugfs on each host are actually captured.

   The qdisc stats gather statistics output from ``tc -s``, while the WiFi stats
   gather statistics from debugfs. These are gathered by looping in a shell
   script; however, for better performance, the ``tc_iterate`` and
   ``wifistats_iterate`` programmes available in the ``misc/`` directory of the
   source code tarball can be installed. On low-powered systems this can be
   critical to get correct statistics. The helper programmes are packaged for
   LEDE/OpenWrt in the ``flent-tools`` package.

.. envvar:: ping_hosts
.. envvar:: ping_local_binds

   These are used to define one or more extra host names that will receive a
   ping flow while a test is run. The ``ping_hosts`` variable simply specifies
   hostnames to ping (several can be specified by separating them with commas).
   The ``ping_local_binds`` variable sets local IP address(es) to bind to for
   the extra ping flows. If specified, it must contain the same number of local
   addresses as the number of ping hosts. The same local address can be
   specified multiple times, however.

.. envvar:: control_hosts

   Hostnames to use for the control connections for the ``rtt_fair_var*`` tests.
   Comma-separated. If specified, it must contain as many hostnames as the
   number of target hostnames specified for the test.
