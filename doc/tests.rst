Supplied Tests
==============

Test are supplied as Python files and can specify commands to run etc.
For a full list of the tests supported by flent, see the
:option:`--list-tests` option.

The Realtime Response Under Load (RRUL) test
--------------------------------------------

This test exists in a couple of variants and is a partial implementation of the
RRUL specification as written by Dave Taht (see
https://www.bufferbloat.net/projects/bloat/wiki/RRUL_Spec/). It works
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
.. envvar:: bidir_streams

   These set the number of streams for the tests that are configurable. The
   ``tcp_nup``, ``tcp_ndown`` and ``rrul_be_nflows`` tests understand
   ``upload_streams`` and ``download_streams``, while the ``rrul_var`` test
   understands ``bidir_streams``. If any of these parameter is set to the
   special value ``num_cpus`` the number of streams will be set to the number of
   CPUs on the system (if this information is available).

.. envvar:: tcp_cong_control

   Set the congestion control used for TCP flows, for platforms that supports
   setting it. This can be specified as a simple string to set the same value
   for upstream and downstream, or two comma-separated values to set it
   separately for the upstream and downstream directions. On Linux, any value in
   the sysctl ``net.ipv4.tcp_allowed_congestion_control`` can be used.

   If a congestion control is specified that is not available on the system
   running the test, setting it will simply fail. In addition, some tests
   override the congestion control for one or more flows. The actual congestion
   control used is stored in the ``CONG_CONTROL`` per-test metadata field.

.. envvar:: udp_bandwidth
.. envvar:: udp_bandwidths
.. envvar:: udp_pktsize
.. envvar:: udp_pktsizes

   This sets the bandwidth and packet size of each UDP stream in the ``udp_*``
   tests. The option is passed to ``iperf`` so can be in any syntax the iperf
   understands (e.g. ``20M`` for 20 Mbps).

   When running multiple UDP streams use the plural versions of the options
   (``udp_bandwidths`` and ``udp_pktsizes``) to specify individual per-stream
   values (comma-separated per stream), or the singular versions to specify the
   same value for all streams.

.. envvar:: burst_length
.. envvar:: burst_ports
.. envvar:: burst_psize
.. envvar:: burst_tos

   These set the length, number of ports to use, packet size and TOS value for
   the packet bursts generated in the ``burst*`` tests.

.. envvar:: cpu_stats_hosts
.. envvar:: netstat_hosts
.. envvar:: ethtool_hosts
.. envvar:: qdisc_stats_hosts
.. envvar:: wifi_stats_hosts

   These specify the hostnames from which to gather statistics during the test.
   Flent passes the hostnames to SSH; therefore, the hostnames follow all the
   traditional SSH hostname declarations, including using the ``username@host``
   syntax or hosts defined in ``~/.ssh/config``. Flent will attempt to run
   remote commands on these hosts to gather the required statistics. For this to
   work, the hosts must have passwordless login enabled. You can specify
   multiple hostnames by separating them by commas.

   While CPU stats, ethtool, and netstat output are global to the machine being
   connected to, the qdisc and WiFi stats are more specific and require extra
   parameters to work effectively. These parameters, namely
   ``qdisc_stats_interfaces``, ``wifi_stats_interfaces``, and
   ``wifi_stats_stations``, play a crucial role in specifying which interfaces
   to gather statistics from and which MAC addresses of stations to gather
   statistics for. Remember, these parameters are paired with the hostnames, so
   they must contain the same number of elements as the ``_hosts`` variables. To
   specify multiple interfaces on the same host, simply duplicate the hostname.
   The ``wifi_stats_stations`` parameter specifies the MAC addresses of stations
   for which statistics are to be gathered. This list is the same for all hosts,
   but only stations present in debugfs on each host are actually captured.
   The ``ethtool_hosts`` parameter lets you finetune which devices and fields to
   monitor using the ``ethtool_devices`` and ``ethtool_fields`` parameters. By
   default, Flent will monitor all network devices from which it can get values.
   However, the ``ethtool_devices`` parameter lets you filter which devices to
   monitor. If no fields are specified, Flent will monitor the ``rx_packets``
   and ``tx_packets`` fields unless you specify other fields in the
   ``ethtool_fields`` parameter. You can create a comma-separated list of fields
   to monitor; however, if you prefix the field with a network device name
   separated by a colon, Flent will only monitor that field for that particular
   device. Example: ``ethtool_fields=tx_bytes,eth0:rx_packets,eth1:tx_packets``

.. envvar:: ping_hosts
.. envvar:: ping_local_binds
.. envvar:: ping_labels

   These are used to define one or more extra host names that will receive a
   ping flow while a test is run. The ``ping_hosts`` variable simply specifies
   hostnames to ping (several can be specified by separating them with commas).
   The ``ping_local_binds`` variable sets local IP address(es) to bind to for
   the extra ping flows. If specified, it must contain the same number of local
   addresses as the number of ping hosts. The same local address can be
   specified multiple times, however. The ``ping_labels`` variable is used to
   label each of the ping flows; if not specified, Flent will create a default
   label based on the target hostname for each flow.

.. envvar:: voip_host
.. envvar:: voip_local_bind
.. envvar:: voip_control_host
.. envvar:: voip_marking

   Similar to the ping variants above, these parameters specify a hostname that
   will receive a VoIP test. However, unlike the ping parameters, only one
   hostname can be specified for VoIP tests, and that end-host needs to have
   either D-ITG (and the control server) or the IRTT server running. The marking
   setting controls which DiffServ marking is applied to the VoIP flow and
   defaults to no marking being set.

.. envvar:: control_hosts

   Hostnames to use for the control connections for the ``rtt_fair*`` tests.
   Comma-separated. If specified, it must contain as many hostnames as the
   number of target hostnames specified for the test.

.. envvar:: markings
.. envvar:: labels

   Flow markings to use for each of the flows in the ``rtt_fair*`` tests.
   Comma-separated values of markings understood by Netperf (such as "CS0").
   Only supports setting the same marking on both the upstream and downstream
   packets of each flow (so no "CS0,CS0" setting as can be used for Netperf). If
   not set, defaults to CS0 (best effort). If set, each value corresponds to a
   flow, and any extra flows will be set to CS0. By default each flow will be
   labelled according to its marking; to override these labels, use the
   ``labels`` parameter.

.. envvar:: stream_delays

   Specify a per-stream delay (in seconds) for the different streams started up
   by a test. Use commas to separate values for the different streams. This can
   be used to create tests with staggered start times, for example to test TCP
   flow startup convergence times. What exactly constitutes a stream depends on
   the test. For example, the rtt_fair* tests considers each hostname a stream,
   whether or not there is one or two flows going to that host.
