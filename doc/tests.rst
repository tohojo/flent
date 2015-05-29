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
