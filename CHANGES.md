# Changes since latest release #

Changes since v1.2.0 include:

- Fix DSCP handling for irtt flows.

- Fix several crashes in the GUI.

- Fix handling of empty data series and several potential crashes in the
  plotting code.

- Fix potential crash in metadata gathering and add timeout to commands.

- Add several missing plots to various tests.

# Flent v1.2.0 #
Released on 2018-02-06.

Changes since v1.1.1 include:

- Add support for the irtt binary (https://github.com/peteheist/irtt/)
  for isochronous UDP latency tests. If irtt is available in $PATH, it
  will be preferred over netperf for UDP RTT tests and over D-ITG for
  VoIP tests. This means that UDP latency tests will no longer use more
  bandwidth as the RTT decreases, and VoIP tests are easier to setup.
  Many thanks to Pete Heist for writing the irtt tool.

  As part of this change, a generic facility for runner preferences has
  been added, which makes it possible to define a test in terms of
  higher level functionality and let Flent pick the best available
  underlying tool to run the test. For now this is only used in the
  cases mentioned above for irtt.

- Add a configurable option for overriding the colour mode for plots.
  This makes it possible to change how colours are assigned to different
  data series.

- Improve handling of multi-value options between batch files, rc file
  and command line. This means that multi-value options can now use both
  comma and semicolon as separators in the batch file, and values can be
  quoted to prevent splitting.

- Drop compatibility with matplotlib versions earlier than 1.4.2. Using
  older versions resulted in spurious errors anyway, and it is too much
  backporting work to support them properly.

- Fix batch mode logging to make sure a log file for a batch run only
  includes log lines from that run and not previous runs.

- Fix several bugs in the plotting and runner code.

# Flent v1.1.1 #
Released on 2017-11-15.

Changes since v1.1.0 include:

- Fix several plotting bugs resulting from the overhaul of the plotting
  code. This includes a couple of crash bugs, bugs in the airtime plots,
  and a bug where all bar plots were completely broken, showing wrong
  values.

# Flent v1.1.0 #
Released on 2017-10-26.

Changes since v1.0.1 include:

- A complete overhaul of the plotting code so that it now uses the exact
  data points captured from the test tools wherever possible, instead of
  interpolating values to align data points on the time axis. This
  should improve the accuracy of plots, especially for integer-value
  data series such as packet drops.

- The GUI has gained a new widget that makes it possible to control all
  plot-related settings. Previously, only a few of the settings for
  generating plots that are available on the command line could be set
  from within the GUI; now, the full set of command line settings can be
  manipulated in the GUI settings pane as well.

- Another rewrite of the plot layout algorithm which should result in
  fewer issues with plot elements such as titles being drawn on top of
  the plot.

- More keyboard shortcuts in the GUI: Ctrl+Up/Down will move between
  different plots, and x/X and y/Y will zoom the axes in/out.

- By default, batch run order is now randomised to prevent periodic
  errors biasing results in long tests. This can be turned off with
  the --batch-no-shuffle option.

- Netperf is now instructed to prefill its buffers with random data,
  instead of the data packets consisting repeated 7-byte strings
  ('netperf'). This ensures that data flows are not trivially
  compressible, which should improve test accuracy on encapsulated
  connections that enable compression.

- Added support for setting TCP congestion control and diffserv markings
  as test parameters for some tests.

- Added support for capturing socket statistics for TCP flows and store
  them as an auxiliary data set. This makes it possible to capture
  window size and RTT estimates from the kernel TCP state machine (Linux
  only). Thanks to Matthias Tafelmeier for the initial implementation of
  this feature.

- Added support for watchdog timers to make sure runners don't go over
  time. This is applied to the fping runner thus far.

- More metadata is captured from test runs; in particular, Netperf
  TCP_INFO variables, the congestion control used for each flow and
  socket buffer sizes are captured for every flow and stored in the
  metadata object.

- Numerous bug fixes throughout.

# Flent v1.0.1 #
Released on 2017-01-16.

Changes since v1.0.0 include:

- Change the default hosts used for rtt_fair tests. One of the old ones
  did not exist anymore.

- Fix a bunch of crashes and behavioural issues in the new test dialog
  in the GUI.

- Make sure log entries emitted during startup make it to the GUI
  console.

# Flent v1.0.0 #
Released on 2017-01-14.

Changes since v0.15.0 include:

- With most of the longtime outstanding issues closed, Flent has now
  reached the big 1.0. Woohoo!

- Use the UltraJSON library (if available) to load data files; this
  speeds up loading of data files moderately.

- Improve logging of Flent's operations. The log file will now contain a
  proper superset of the console output, and Flent has been made
  slightly more verbose about what it is doing. Also, the log is now
  shown in a pane in the GUI.

- Fix an error breaking plots on Python 2 and some versions of
  matplotlib.

- Support PyQt5 in the GUI (and prefer it over PyQt4). If PyQt5 is not
  found, fall back to PyQt4.

- Add new SummaryFormatter that outputs mean and median values for each
  data series. This is the new default formatter, meaning that its
  output will be shown after a test run if no other formatter (or plot)
  is specified.

- Support multiprocessing in the GUI. When loading several plots at
  once, plotting will now be passed off to separate worker processes.
  This allows plotting to use all the available processors on the
  machine, and speeds up loading of many plots tremendously (initial
  load is sped up by an order of magnitude). This change also means that
  re-plotting on config changes will be done dynamically in the
  background, which makes the GUI more responsive.

- Make text completely black in the default colour scheme. This
  increases contrast, and helps legibility, especially on printed
  figures.

- Some internal code changes: Port command line parser from the old
  optparse class to the newer argparse, and fix a bunch of linter
  errors.

# Flent v0.15.0 #
Released on 2016-10-01.

This release represents eight months of development since v0.14.0. There
are several new features and a bunch of bugfixes. Also, starting from
this release, Flent will be packaged for Debian and included in upcoming
releases of both Debian and Ubuntu. Thanks to Iain Learmonth for
sponsoring this.

Changes since v0.14.0 include:

- Several new tests, including the rtt_fair_var* tests and
  tcp_n{up,down} tests which take a variable number of hostnames as
  targets.

- Fixes to the UDP tests and a new test parameter to support setting UDP
  flow bandwidth.

- Support for setting TOS values for some tests.

- Added parser for WiFi statistics such as aggregation size and airtime
  (the latter requires a patched ath9k).

- Support globbing in test plot specifications.

- Added test mixins for adding several types of extra flows by
  specifying test parameters. These include ping flows, VoIP flows, HTTP
  traffic and WiFi and Qdisc stats. The parameters are documented in the
  'tests' section of the man page and documentation.

- Generate a UUID when running a batch sequence, and support grouping
  combination plots on these. This makes it possible to turn individual
  batch sequences into data series when plotting combination plots.

- Support saving the intermedia result sets generated when creating
  combination plots. This speeds up subsequent plottings of the same
  data (which is helpful when experimenting with customising the plots).

- Added a bunch of command line options to customise lots of aspects of
  the plot appearance (labels, legend placement, etc.). See man page or
  --help output for details.

- Add a runner to parse /proc/net/netstat TCPext mib entries.

- Customise plot appearance by directly setting matplotlib RC parameters
  instead of loading an RC file. This means that plots will always use
  the included style unless --no-matplotlibrc is used.

- Allow plotting results from different test names on the same plot.
  This is especially useful with the mixins, which generate the same
  series names independent on which underlying test is used. No checking
  is done for whether two different tests make sense to plot together,
  though, so use common sense.

- Support computing Jain's fairness index as a plot combiner. This means
  that it is now possible to plot the fairness index across averages of
  datasets, for instance to compare average throughput values over whole
  test runs.

- Support computing (and plotting) MOS scores from latency and delay
  values using the ITU G.107 06/2015 E-model.

- Added rudimentary support for running a test runner on a remote host.
  I.e. Flent can now SSH to another host and run (e.g.) a netperf
  instance and add that data into a test.

- Support normalising data series by each other when plotting. This can
  be used to, for instance, normalise individual host throughput values
  by the total throughput to get a fractional value.

- Support using the raw values when reducing data series in combination
  plots.

- A bunch of bug fixes too numerous to list here.

# Flent v0.14.0 #
Released on 2016-02-03.

This release adds mixins for capturing qdisc stats and CPU usage, adds
some convenience functions to the GUI and fixes a bunch of bugs, most
notably making the GUI work on Windows.

- Batch mode: Try to estimate the total runtime of a batch and print it
  before executing the batch itself.

- GUI: Add support for pinning a metadata item open when flipping
  between tabs, and support adding columns to the open files view from
  the metadata view. Both functions are available from the context menu
  when right-clicking in the metadata view.

- Add test mixins to a bunch of tests making it possible to
  simultaneously capture qdisc stats and/or CPU stats of one or more
  hosts while the test is run. This works by setting the test parameters
  qdisc_stats_hosts, qdisc_stats_interfaces and cpu_stats_hosts to
  comma-separated lists of hosts and interface names. The functionality
  relies on the tc_iterator and stats_iterator helper scripts.

- Add a C implementation of the tc_iterator helper script that works on
  OpenWrt and also gives higher polling accuracy than the shell script.

- Add a kill_timeout setting for runners in test definitions which will
  forcibly kill a subprocess after an interval (if it hasn't exited
  already).

- Add the tcp_upload_1000 test for seriously overloading things. On most
  systems, increasing the ulimit is necessary to run this test.

- Support globbing selectors in plot configuration when specifying
  datasets for a plot.

- Record number of failed runners (non-0 exit status) as a metadata key.

- GUI: Fix bugs in plot blitting on older matplotlibs, fix test running
  without a pre-set HOST, fix bugs in draw cache handling, and restore
  the GUI to a working state on Windows.

- Various bugfixes.

# Flent v0.13.0 #
Released on 2015-11-06.

This release of Flent adds a couple of new features to the GUI, updates
Iperf support and adds a bunch of bugfixes.

- GUI: For line graphs (timeseries and CDF plots), highlight data series
  when the mouse is hovering over the lines themselves or their
  corresponding legend items. This makes it easier to pick out specific
  data series when browsing graphs. There's a toggle to turn off this
  feature, since it can perform badly on slow systems and/or causes
  flicker in some instances on OSX.

- GUI: Experimental feature to run tests from the GUI. Fairly basic thus
  far, but it is possible to run a simple test from the GUI which will
  subsequently be loaded in the graph view.

- File format: Bump file format to v3. The file format now uses UTC
  timestamps everywhere internally, which is an incompatible change;
  hence the version bump. Old data files will be loaded assuming local
  times and converted appropriately on load. File name date stamps are
  still done in local time for the box running the test.

- Bring Iperf support up-to-date. The newest git version of Iperf (2)
  adds support for sub-second timestamps. Flent now detects this and can
  use and parse Iperf results when this support is detected. So far, no
  tests actually use Iperf, though.

- Flent will now capture the module version of a running Cake shaper
  module as part of extended metadata. TCP buffer size limit sysctls are
  now also captured.

- Some bug fixes related to matplotlib and Qt version compatibility and
  weirdness of the OSX file selector dialog.

# Flent v0.12.4 #
Released on 2015-09-22.

This is a small bugfix release. Changes since v0.12.3:

- Packaging fixes for Debian.

- Support for Python 2.6 has officially been dropped (it had already
  bitrotted, so now a nicer error message is shown straight away).

- Bug in local_bind for ping commands fixed.

- More graphs for tcp_* tests and fixed labels on HTTP test graphs.

- Catch unhandled exception that caused crashed when using a null output
  formatter.

# Flent v0.12.3 #
Released on 2015-08-03.

This is a minor bugfix release, fixing an important regression in the
GUI preventing files from being loaded when running under Python 2.

# Flent v0.12.2 #
Released on 2015-07-29.

This release includes a major refactoring of the plotting code, which
should make it easier to extend in the future.

Other changes since v0.11.1:

- GUI restructuring: The plot settings now reside in a menu, the
  metadata view defaults to the bottom part of the window, and a new
  open files view has been added to make it easier to manage many open
  files at once in the GUI.

- Revert to writing data files to the current directory by default. A
  new parameter, -D, can optionally select a different output dir.

- The man page is now generated from the Sphinx documentation.

- Try to detect if the system `ping` utility produces parsable output
  before using it. Should give nicer error messages on OSX if fping is
  not installed.

- Add a new qdisc-stats test which will periodically gather qdisc
  statistics and a wlan-retries test which will gather WiFi retry
  statistics.

- New tests comparing different TCP congestion control algorithms have
  been added.

- Add a --replace-legend parameter to do search/replace on legends when
  plotting.

- A test suite has been added containing basic unittests for parts of
  the code. Test coverage is still fairly poor, but will be extended
  going forward. Run `make test` to run the test suite (requires the
  'mock' Python library).

- VoIP tests can now show loss rates.

- A bunch of bug fixes.
