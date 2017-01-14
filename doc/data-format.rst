The Data File Format
====================
The aggregated test data is saved in a file called
:file:`<test_name>-<date>.<title>.flent.gz` (the title part is omitted if no title is
specified by the :option:`-t` parameter). This file contains the data points
generated during the test, as well as some metadata.


The top-level object keys
-------------------------

.. envvar:: version

            The file format version as an integer.

.. envvar:: x_values

            An array of the x values for the test data (typically the time
            values for timeseries data).

.. envvar:: results

            A JSON object containing the result data series. The keys are the
            data series names; the value for each key is an array of y values
            for that data series. The data array has the same length as the
            :envvar:`x_values` array, but there may be missing data points
            (signified by null values).

.. envvar:: metadata

            An object containing various data points about the test run. The
            metadata values are read in as configuration parameters when the
            data set is loaded in for further processing. Not all tests use all
            the parameters, but they are saved anyway.

.. envvar:: raw_values

            An array of objects for each data series. Each element of the array
            contains the raw values as parsed from the test tool corresponding
            to that data series.


Metadata keys
-------------

.. envvar:: NAME

	    The test name.

.. envvar:: TITLE

	    Any extra title specified by the :option:`--title-extra` parameter
            when the test was run.

.. envvar:: HOSTS

	    List of the server hostnames connected to during the test.

.. envvar:: LOCAL_HOST

	    The hostname of the machine that ran the test.

.. envvar:: LENGTH

	    Test length in seconds, as specified by the :option:`--length` parameter.

.. envvar:: TOTAL_LENGTH

            Actual data series length, after the test has added time to the
            :envvar:`LENGTH`.

.. envvar:: STEP_SIZE

	    Time step size granularity.

.. envvar:: TIME

            ISO timestamp of the time the test was initiated.

.. envvar:: NOTE

	    Arbitrary text as entered with the :option:`--note` switch when the
            test was run.

.. envvar:: FLENT_VERSION

            Version of Flent that generated the data file.

.. envvar:: IP_VERSION

            IP version used to run test (as specified by command line
	    parameters, or auto-detected from :c:func:`getaddrinfo()` if unspecified).

.. envvar:: KERNEL_NAME

	    The kernel name as reported by :command:`uname -s`.

.. envvar:: KERNEL_RELEASE

            The kernel release as reported by :command:`uname -r`.

.. envvar:: MODULE_VERSIONS

            The sha1sum of certain interesting Linux kernel modules, if
            available. Can be used to match test data to specific code versions,
            if the kernel build is instrumented to, e.g., set the build ID to a
            git revision.

.. envvar:: SYSCTLS

            The values of several networking-related sysctls on the host (if
            available; Linux only).

.. envvar:: EGRESS_INFO

	    Interface name, qdisc, offload, driver and BQL configuration of the
            interface used to reach the test target. This requires that the
            :command:`ip` binary is present on Linux, but can be extracted from
            :command:`route` on BSD. Qdisc information requires the
            :command:`tc` binary to be present, and offload information requires
            :command:`ethtool`.

            If the :option:`--remote-metadata` is used, the extended metadata
            info is gathered for each of the hostnames specified. This is
            gathered under the :envvar:`REMOTE_METADATA` key in the metadata
            object, keyed by the hostname values passed to
            :option:`--remote-metadata`. Additionally, the
            :envvar:`REMOTE_METADATA` object will contain an object called
            :envvar:`INGRESS_INFO` which is a duplicate of
            :envvar:`EGRESS_INFO`, but with the destination IP exchanged for the
            source address of the host running flent. The assumption here is
            that :option:`--remote-metadata` is used to capture metadata of a
            router known to be in the test path, in which case
            :envvar:`INGRESS_INFO` will contain information about the reverse
            path from the router (which is ingress from the point of view of the
            host running flent). If the host being queried for remote metadata
            is off the path, the contents of :envvar:`INGRESS_INFO` will
            probably be the same as that of :envvar:`EGRESS_INFO` .

Extended metadata
-----------------

If the :option:`--extended-metadata` switch is turned on, the following
additional values are collected and stored (to the extent they are available
from the platform):

.. envvar:: IP_ADDRS

	    IP addresses assigned to the machine running flent.

.. envvar:: GATEWAYS

	    IP addresses of all detected default gateways on the system, and the
            interfaces they are reachable through. Only available if the
            :command:`netstat` binary is present on the system.

.. envvar:: EGRESS_INFO

            In the :envvar:`EGRESS_INFO` key, the IP address of the next-hop
            router and the interface MAC address are added if extended metadata
            is enabled.
