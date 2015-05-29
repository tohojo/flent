The Data File Format
====================

The aggregated test data is saved in a file called
*<test\_name>-<date>.<title>.json.gz* (the title part is omitted if no
title is specified by the **-t** parameter). This file contains the data
points generated during the test, as well as some metadata. The
top-level json object has three keys in it: *x\_values*, *results* and
*metadata*.

*x\_values* is an array of the x values for the test data (typically the
time values for timeseries data).

*results* is a json object containing the result data series. The keys
are the data series names; the value for each key is an array of y
values for that data series. The data array has the same length as the
*x\_values* array, but there may be missing data points (signified by
null values).

*metadata* is an object containing various data points about the test
run. The metadata values are read in as configuration parameters when
the data set is loaded in for further processing. Not all tests use all
the parameters, but they are saved anyway.

Currently the metadata values are:

*NAME*: The test name.

*TITLE*: Any extra title specified by the **-t** parameter when the test
was run.

*HOSTS*: List of the server hostnames connected to during the test.

*LOCAL\_HOST*: The hostname of the machine that ran the test.

*LENGTH*: Test length in seconds, as specified by the **-l** parameter.

*TOTAL\_LENGTH*: Actual data series length, after the test has added
time to the *LENGTH*.

*STEP\_SIZE*: Time step size granularity.

*TIME*: ISO timestamp of the time the test was initiated.

*NOTE*: Arbitrary text as entered with the **--note** switch when the
test was run.

*FLENT\_VERSION*: Version of flent that generated the data file.

*IP\_VERSION*: IP version used to run test (as specified by command line
parameters, or auto-detected from *getaddrinfo()* if unspecified).

If the **−−extended−metadata** switch is turned on, the following
additional values are collected and stored (to the extent they are
available from the platform):

*KERNEL\_NAME*: The kernel name as reported by *uname -s*.

*KERNEL\_RELEASE*: The kernel release as reported by *uname -r*.

*IP\_ADDRS*: IP addresses assigned to the machine running flent.

*GATEWAYS*: IP addresses of all detected default gateways on the system,
and the interfaces they are reachable through. Only available if the
*netstat* binary is present on the system.

*EGRESS\_INFO*: Egress interface, its qdisc, offload, driver and BQL
configuration, and (if applicable) the IP address of the next-hop router
used to reach the test target. The egress interface and next-hop router
requires that the *ip* binary is present on Linux, but can be extracted
from *route* on BSD. Qdisc information requires the *tc* binary to be
present, and offload information requires *ethtool*.

If the **--remote-metadata** is used, the extended metadata info is
gathered for each of the hostnames specified. This is gathered under the
*REMOTE\_METADATA* key in the metadata object, keyed by the hostname
values passed to **--remote-metadata**. Additionally, the
*REMOTE\_METADATA* object will contain an object called *INGRESS\_INFO*
which is a duplicate of *EGRESS\_INFO*, but with the destination IP
exchanged for the source address of the host running flent. The
assumption here is that **--remote-metadata** is used to capture
metadata of a router known to be in the test path, in which case
*INGRESS\_INFO* will contain information about the reverse path from the
router (which is ingress from the point of view of the host running
flent). If the host being queried for remote metadata is off the path,
the contents of *INGRESS\_INFO* will probably be the same as that of
*EGRESS\_INFO*.
