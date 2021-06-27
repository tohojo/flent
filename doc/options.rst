Running Flent
=============

When run, flent must be supplied either (a) a test name and one or more host
names to connect to, or (b) one or more input files containing data from
previous runs to post-process.

Test names, hostnames and input file names can all be specified as unqualified
arguments, and flent will do its best to guess which is which. For each
argument, if it is an existing file, it is assumed to be an input file, if it is
the name of an existing test configuration it’s assumed to be a test name, and
if neither of those are true, it is assumed to be a host name. The :option:`-i`
and :option:`-H` switches can be used to explicitly specify the interpretation
of an argument.

Invocation
----------

**flent** [*options*\ ] *<host\|test\|input file* ...\ *>*



General options
---------------

.. option:: -o OUTPUT, --output=OUTPUT

   File to write processed output to (default standard out).

.. option:: -D DATA_DIR, --data-dir=DATA_DIR

   Directory to store data files in. Defaults to the current directory.

.. option:: -i INPUT, --input=INPUT

   File to read input from (instead of running tests). Input files can also be
   specified as unqualified arguments without using the :option:`-i` switch.

.. option:: -f FORMAT, --format=FORMAT

   Select output format (plot, csv, org\_table, stats). Default is no processed
   output (just writes the JSON data file).

.. option:: -p PLOT, --plot=PLOT

   Select which plot to output for the given test (implies :option:`-f` plot). Use the
   :option:`--list-plots` option to see available plots.

.. option:: -t TITLE, --title-extra=TITLE

   Text to add to plot title and data file name.

.. option:: -n NOTE, --note=NOTE

   Add arbitrary text as a note to be stored in the JSON data file (under the
   *NOTE* key in the metadata object).

.. option:: -r RCFILE, --rcfile=RCFILE

   Load configuration data from *RCFILE* (default *~/.flentrc*). See section
   below for information on the rc file format.

.. option:: -x, --extended-metadata

   Collect extended metadata and store it with the data file. May include
   details of your machine you don’t want to distribute; see the section on the
   data format below.

.. option:: --remote-metadata=HOSTNAME

   Collect extended metadata from a remote host. *HOSTNAME* is passed verbatim
   to ssh, so can include hosts specified in ~/.ssh/config. Note that gathering
   the data can take some time, since it involves executing several remote
   commands. This option can be specified multiple times and implies
   :option:`--extended-metadata`.

.. option:: --gui

   Run the flent GUI. All other options are used as defaults in the GUI, but can
   be changed once it is running. The GUI can also be started by running the
   :command:`flent-gui` binary. For more information on the GUI, see the
   :doc:`gui` section.

.. option:: --new-gui-instance

   Start a new GUI instance. Otherwise, flent will try to connect to an already
   running GUI instance and have that load any new data files specified as
   arguments. Implies :option:`--gui` when passed on the command line, but not when
   set in the rc file. Note that when multiple GUI instances are running, there
   is no guarantee as to which instance will get a subsequent open request (if
   run again without :option:`--new-gui-instance`).

.. option:: --gui-no-defer

   Normally, the GUI defers redrawing plots until they are needed to avoid
   redrawing all open plots every time an option changes. This switch turns off
   that optimisation in favour of always redrawing everything straight away.
   This is useful when loading a bunch of plots from the command line and then
   wanting to flip through them without drawing delay.

.. option:: -b BATCH_NAME, --batch-name=BATCH_NAME

   Run test batch BATCH\_NAME (must be specified in a batch file loaded by the
   :option:`--batch-file` option). Can be supplied multiple times.

.. option:: -B BATCH_FILE, --batch-file=BATCH_FILE

   Load batch file BATCH_FILE. Can be specified multiple times, in which case
   the files will be combined (with identically-named sections being overridden
   by later files). See appropriate section below for an explanation of the
   batch file format.

.. option:: --batch-override=key=value

   Override parameter ’key’ in the batch config and set it to ’value’. The key
   name will be case folded to lower case. Can be specified multiple times.

.. option:: --batch-dry-run

   Dry batch run. Prints what would be done, but doesn’t actually run any tests.

.. option:: --batch-verbose

   Be verbose during batch run: Print all commands executed.

.. option:: --batch-no-shuffle

   Do not randomise the order of test runs within each batch.

.. option:: --batch-repetitions=REPETITIONS

   Shorthand for :option:`--batch-override` ``'repetitions=REPETITIONS’``.

.. option:: --batch-title=TITLE

   Shorthand for :option:`--batch-override` ``'batch_title=TITLE’``.

.. option:: --batch-resume=DIR

   Try to resume a previously interrupted batch run. The argument is the
   top-level output directory from the previous run.

   This will attempt to find a data file in the resume directory and load the
   BATCH_TIME from the previous run from that and continue. The assumption is
   that the output directory and filenames are generated from the batch time, so
   that they will match with the previous run when the same time is used. Then,
   tests for which data files already exist will be skipped on this run. If the
   rest of the batch invocation is different from the one being resumed, results
   may not be what you want.

   There's a check to ensure that the generated output path is a subdirectory of
   the resume directory, and the whole run will be aborted if it isn't.

Test configuration options
--------------------------

These options affect the behaviour of the test being run and have no effect when
parsing input files.

.. option :: -H HOST, --host=HOST

   Host to connect to for tests. For tests that support it, multiple hosts can
   be specified by supplying this option multiple times. Hosts can also be
   specified as unqualified arguments; this parameter guarantees that the
   argument be interpreted as a host name (rather than being subject to
   auto-detection between input files, hostnames and test names).

.. option:: --local-bind=IP

   Local hostname or IP address to bind to (for test tools that support this).
   Can be specified multiple times for tests that connect to more than one host;
   if it is, it must be specified as many times as there are hosts.

.. option:: --remote-host=idx=HOSTNAME

   A remote hostname to connect to when starting a test. The idx is the runner
   index, which is assigned sequentially to each *runner* (and so it is *not*
   the same as the sequence of hostnames). Look for the 'IDX' key in SERIES_META
   for a test get the idx used here, but note that the idx assignment depends on
   the exact arguments to the test.

   This works by simply prepending 'ssh HOSTNAME' to the runner command, so it
   relies on the same binaries being in the same places on both machines, and
   won't work for all runners.

   This option can be specified multiple times to have multiple runners run on
   remote hosts.

.. option:: -l LENGTH, --length=LENGTH

   Base test length (some tests may add some time to this).

.. option:: -s STEP_SIZE, --step-size=STEP_SIZE

   Measurement data point step size.

.. option:: -d DELAY, --delay=DELAY

   Number of seconds to delay parts of test (such as bandwidth loaders).

.. option:: -4, --ipv4

   Use IPv4 for tests (some tests may ignore this).

.. option:: -6, --ipv6

   Use IPv6 for tests (some tests may ignore this).

.. option:: --socket-timeout=SOCKET_TIMEOUT

   Socket timeout (in seconds) used for UDP delay measurement, to prevent stalls
   on packet loss. Only enabled if the installed netperf version is detected to
   support this (requires SVN version of netperf).

   For the default value, see the output of flent :option:`-h`. The value of
   this parameter is an implicit upper bound on how long a round-trip time that
   can be measured. As such you may need to adjust it if you are experiencing
   latency above the default value. Set to 0 to disable.

.. option:: --send-size=SEND_SIZE

    Send size (in bytes) used for TCP tests. Netperf uses the socket buffer size
    by default, which if too large can cause spikes in the throughput results.
    Lowering this value will increase CPU usage but also improves the fidelity
    of the throughput results without having to decrease the socket buffer size.

    Can be specified multiple times, with each value corresponding to a stream
    of a test. If only specified once, the same value will be applied to all
    flows.

.. option:: --test-parameter=key=value

   Arbitrary test parameter in key=value format. Key will be case folded to
   lower case. The values are stored with the results metadata, and so can be
   used for storing arbitrary information relevant for a particular test run.

   In addition to serving as simple metadata, the test parameters can also
   affect the behaviour of some test configurations. See the :doc:`tests`
   section for information on these.

   This option can be specified multiple times to set multiple test parameters.

.. option:: --swap-up-down

   Switch upstream and downstream directions for data transfer. This means that
   ’upload’ will become ’download’ and vice versa. Works by exchanging netperf
   ``TCP_MAERTS`` and ``TCP_STREAM`` parameters, so only works for tests that employ
   these as their data transfer, and only for the TCP streams.

.. option:: --socket-stats

    Parse socket stats during test. This will capture and parse socket
    statistics for all TCP upload flows during a test, adding TCP cwnd and RTT
    values to the test data. Requires the 'ss' utility to be present on the
    system, and can fail if there are too many simultaneous upload flows; which
    is why this option is not enabled by default.

.. option:: --marking-name

    Define a new symbolic name that can be used when specifying flow markings
    using the 'markings' test parameter. This can be used to make it easier to
    specify custom diffserv markings on flows by using symbolic names for each
    marking value instead of the hex codes. Values specified here will be used
    in addition to the common values (listed below), and cannot override the
    built-in names. Names will be case-folded when matching.

    The list of symbolic markings natively supported, along with their hex
    expansions, are::

               AF11: 0x28    CS0: 0x00
               AF12: 0x30    CS1: 0x20
               AF13: 0x38    CS2: 0x40
               AF21: 0x48    CS3: 0x60
               AF22: 0x50    CS4: 0x80
               AF23: 0x58    CS5: 0xa0
               AF31: 0x68    CS6: 0xc0
               AF32: 0x70    CS7: 0xe0
               AF33: 0x78    EF:  0xb8
               AF41: 0x88
               AF42: 0x90
               AF43: 0x98

    Note that the hexadecimal values denote the value of the full ToS byte
    (including the two ECN bits), so they need to be right-shifted by two bits
    to get the corresponding diffserv code points.


Plot configuration options
--------------------------

These options are used to configure the appearance of plot output and only make
sense combined with :option:`-f` *plot*.

.. option:: --label-x=LABEL
.. option:: --label-y=LABEL

   Override the figure axis labels. Can be specified twice, corresponding to
   figures with multiple axes.

.. option:: -I, --invert-latency-y

   Invert latency data series axis (typically the Y-axis), making plots show
   ’better' values upwards.

.. option:: -z, --zero-y

   Always start Y axis of plot at zero, instead of autoscaling the axis.
   Autoscaling is still enabled for the upper bound. This also disables log
   scale if enabled.

.. option:: --log-scale={log2,log10}

   Use the specified logarithmic scale on plots.

.. option:: --norm-factor=FACTOR

   Data normalisation factor. Divide all data points by this value. Can be
   specified multiple times, in which case each value corresponds to a data
   series.

.. option:: --bounds-x=BOUNDS
.. option:: --bounds-y=BOUNDS

   Specify bounds of the plot axes. If specifying one number, that will become
   the upper bound. Specify two numbers separated by a comma to specify both
   upper and lower bounds. To specify just the lower bound, add a comma
   afterwards. Can be specified twice, corresponding to figures with multiple
   axes.

.. option:: -S, --scale-mode

   Treat file names (except for the first one) passed as unqualified arguments
   as if passed as :option:`--scale-data` (default as if passed as
   :option:`--input`).

.. option:: --concatenate

   Concatenate multiple result sets into one data series. This means that each
   data file will have its time axis shifted by the preceding series duration
   and appended to the first data set specified. Only works for data sets from
   the same test, obviously.

.. option:: --absolute-time

   Plot data points with absolute UNIX time on the x-axis. This requires the
   absolute starting time for the test run to be stored in the data file, and so
   it won’t work with data files that predates this feature.

.. option:: --subplot-combine

   When plotting multiple data series, plot each one on a separate subplot
   instead of combining them into one plot. This mode is not supported for all
   plot types, and only works when :option:`--scale-mode` is disabled.

.. option:: --skip-missing-series

   Skip missing series entirely from bar plots, instead of leaving an empty
   space for it.

.. option:: --no-print-n

   Do not print the number of data points on combined plots. When using plot
   types that combines results from several test runs, the number of data series
   in each combined data point is normally added after the series name, (n=X)
   for X data series. This option turns that off.

.. option:: --no-annotation

   Exclude annotation with hostnames, time and test length from plots.

.. option:: --figure-note=NOTE, --fig-note=NOTE

   Add a note (arbitrary text) to the bottom-left of the figure.

.. option:: --no-title

   Exclude title from plots.

.. option:: --override-title=TITLE

   Override plot title with this string. Completely discards the configured
   title (from the test configuration), as well as the title stored in the data
   set, and replaces it with the value supplied here. This is useful to override
   the plot title *at the time of plotting*, for instance to add a title to an
   aggregate plot from several data series. When this parameter is specified,
   :option:`--no-title` has no effect.

.. option:: --no-labels

   Hides tick labels from box and bar plots.

.. option:: --no-markers

   Don’t use line markers to differentiate data series on plots.

.. option:: --no-legend

   Exclude legend from plots.

.. option:: --horizontal-legend

   Place a horizontal legend below the plot instead of a vertical one next to
   it. Doesn't always work well if there are too many items in the legend.

.. option:: --legend-title=LEGEND_TITLE

   Override legend title on plot.

.. option:: --legend-placement=LEGEND_PLACEMENT

   Control legend placement. Enabling this option will place the legend inside
   the plot at the specified location. Can be one of 'best', 'upper right',
   'upper left', 'lower left', 'lower right', 'right', 'center left', 'center
   right', 'lower center', 'upper center' or 'center'.

.. option:: --legend-columns=LEGEND_COLUMNS
    Set the number of columns in the legend.

.. option:: --reverse-legend

   Reverse the order of items in the legend. This can be useful to make the
   legend order match the data series in some cases.

.. option:: --filter-legend

   Filter legend labels by removing the longest common substring from all
   entries. This is not particularly smart, so use with care.

.. option:: --replace-legend=src=dest

   Replace 'src' with 'dst' in legends. Can be specified multiple times.

.. option:: --filter-regexp=REGEXP

   Filter the plot legend by the supplied regular expression. Note that for
   combining several plot results, the regular expression is also applied before
   the grouping logic, meaning that a too wide filter can mess up the grouping.

.. option:: --override-label=LABEL

   Override dataset label. Can be specified multiple times when multiple
   datasets are being plotted, in which case the order of labels corresponds to
   the order of datasets.

   Like :option:`--override-title`, this is applied *at the time of plotting*.

.. option:: --filter-series=SERIES

   Filter out specified series from plot. Can be specified multiple times.

.. option:: --split-group=LABEL

   Split data sets into groups when creating box plots. Specify this option
   multiple times to define the new groups; the value of each option is the
   group name.

   Say you're plotting nine datasets which are really testing two variables with
   three values each. In this case, it can be useful to have the box plot of the
   results be split into three parts (corresponding to the values of one
   variable) with each three boxes in each of them (corresponding to the values
   of the second variable). This option makes this possible; simply specify it
   three times with the labels to be used for the three groups.

   A constraint on this option is that the number of datasets being plotted must
   be divisible by the number of groups.

.. option:: --colours=COLOURS

   Comma-separated list of colours to be used for the plot colour cycle. Can be
   specified in any format understood by matplotlib (including HTML hex values
   prefixed with a #).

   Yes, this option uses British spelling. No, American spelling is not
   supported.

.. option:: --override-colour-mode=MODE

   Override colour_mode attribute. This changes the way colours are
   assigned to bar plots. The default is 'groups' which assigns a separate
   colour to each group of data series. The alternative is 'series' which
   assigns a separate colour to each series, repeating them for each data
   group.

.. option:: --override-group-by=GROUP

   Override the ``group_by`` setting for combination plots. This is useful to,
   for instance, switch to splitting up combined data sets by batch run instead
   of by file name.

.. option:: --combine-save-dir=DIRNAME

   When doing a combination plot save the intermediate data to ``DIRNAME``. This
   can then be used for subsequent plotting to avoid having to load all the
   source data files again on each plot.

.. option:: --figure-width=FIG_WIDTH

   Figure width in inches. Used when saving plots to file and for default size
   of the interactive plot window.

.. option:: --figure-height=FIG_HEIGHT

   Figure height in inches. Used when saving plots to file and for default size
   of the interactive plot window.

.. option:: --figure-dpi=FIG_DPI

   Figure DPI. Used when saving plots to raster format files.

.. option:: --fallback-layout

   Use the fallback layout engine (tight_layout built in to matplotlib). Use
   this if text is cut off on saved figures. The downside to the fallback engine
   is that the size of the figure (as specified by :option:`--figure-width` and
   :option:`--figure-height`) is no longer kept constant.)

.. option:: --no-matplotlibrc

   Don’t load included matplotlibrc values. Use this if autodetection of custom
   matplotlibrc fails and flent is inadvertently overriding rc values.

.. option:: --no-hover-highlight

   Don't highlight data series on hover in interactive plot views. Use this if
   redrawing is too slow, or the highlighting is undesired for other reasons.

.. option:: --scale-data=SCALE_DATA

   Additional data files to consider when scaling the plot axes (for plotting
   several plots with identical axes). Note, this displays only the first data
   set, but with axis scaling taking into account the additional data sets. Can
   be supplied multiple times; see also :option:`--scale-mode`.


Test tool-related options
-------------------------
.. option:: --control-host=HOST

   Hostname for the test control connection (for test tools that support this).
   Default: First hostname of test target.

   When running tests that uses D-ITG as a test tool (such as the voip-\*
   tests), this switch controls where flent will look for the D-ITG control
   server (see section below on running tests with D-ITG). For Netperf-based
   tests, this option is passed to Netperf to control where to point the control
   connection. This is useful to, for instance, to run the control server
   communication over a separate control network so as to not interfere with
   test traffic.

   There is also a per-flow setting for this for tests that connect to multiple
   hosts; see the `control_hosts` test parameter in :doc:`tests`. If both are
   set, the per-flow setting takes precedence for those tests that use it.

.. option:: --control-local-bind=IP

   Local hostname or IP to bind control connection to (for test tools that
   support it; currently netperf). If not supplied, the value for
   :option:`--local-bind` will be used. Note that if this value is passed but
   :option:`--local-bind` is *not*, netperf will use the value specified here to
   bind the data connections to as well.

.. option:: --netperf-control-port=PORT

   Port for Netperf control server. Default: 12865.

.. option:: --ditg-control-port=PORT

   Port for D-ITG control server. Default: 8000.

.. option:: --ditg-control-secret=SECRET

   Secret for D-ITG control server authentication. Default: ’’.

.. option:: --http-getter-urllist=FILENAME

   When running HTTP tests, the http-getter tool is used to fetch URLs (see
   https://github.com/tohojo/http-getter). This option specifies the filename
   containing the list of HTTP URLs to get. Can also be a URL, which will then
   be downloaded as part of each test iteration. If not specified, this is set
   to http://<hostname>/filelist.txt where <hostname> is the first test
   hostname.

.. option:: --http-getter-dns-servers=DNS_SERVERS

   DNS servers to use for http-getter lookups. Format is
   host[:port][,host[:port]]... This option will only work if libcurl supports
   it (needs to be built with the ares resolver). Default is none (use the
   system resolver).

.. option:: --http-getter-timeout=MILLISECONDS

   Timeout for HTTP connections. Default is to use the test length.

.. option:: --http-getter-workers=NUMBER

   Number of workers to use for getting HTTP urls. Default is 4.

.. option:: --irtt-sampling-interval=MILLISECONDS

   Override the sampling interval passed to irtt, in milliseconds. Can be used
   to run irtt with a higher sampling frequency than the rest of the test. If
   set, this will override the sampling interval for all instances of irtt used
   in the test.

Misc and debugging options:
---------------------------

.. option::  -L LOG_FILE, --log-file=LOG_FILE

   Write debug log (test program output) to log file.

.. option:: --list-tests

   List available tests and exit.

.. option:: --list-plots

   List available plots for selected test and exit.

.. option:: -V, --version

   Show Flent version information and exit.

.. option:: -v, --verbose

   Enable verbose logging to console.

.. option:: -q, --quiet

   Disable normal logging to console (and only log warnings and errors).

.. option:: --debug-error

   Print full exception backtraces to console.

.. option:: -h, --help

   Show usage help message and exit.


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
