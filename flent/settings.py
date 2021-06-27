# -*- coding: utf-8 -*-
#
# settings.py
#
# Author:   Toke Høiland-Jørgensen (toke@toke.dk)
# Date:     25 November 2012
# Copyright (c) 2012-2016, Toke Høiland-Jørgensen
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import absolute_import, division, print_function, unicode_literals

import argparse
import os
import socket
import sys

from datetime import datetime
from copy import deepcopy
from collections import OrderedDict

try:
    from configparser import RawConfigParser
except ImportError:
    from ConfigParser import RawConfigParser

from flent.build_info import VERSION
from flent.testenv import TestEnvironment, TEST_PATH
from flent.loggers import get_logger
from flent.util import FuncAction, Update, AddHost, append_host, keyval, \
    keyval_int, keyval_transformer, ArgParser, token_split
from flent.plotters import add_plotting_args
from flent import loggers, util, resultset, runners

# Python 2/3 compatibility
try:
    unicode
except NameError:
    unicode = str

logger = get_logger(__name__)

OLD_RCFILE = os.path.expanduser("~/.netperf-wrapperrc")

DEFAULT_SETTINGS = {
    'NAME': None,
    'HOST': None,
    'LOCAL_HOST': socket.gethostname(),
    'DESCRIPTION': 'No description',
    'PLOTS': {},
    'TIME': datetime.utcnow(),
    'BATCH_NAME': None,
    'BATCH_UUID': None,
}

DICT_SETTINGS = ('DATA_SETS', 'PLOTS')


class _LOG_DEFER:
    pass


class Version(FuncAction):

    def __call__(*args):
        logger.info("Flent v%s.\nRunning on Python %s.",
                    VERSION, sys.version.replace("\n", " "))
        try:
            import matplotlib
            import numpy
            logger.info("Using matplotlib version %s on numpy %s.",
                        matplotlib.__version__, numpy.__version__)
        except ImportError:
            logger.info("No matplotlib found. Plots won't be available.")
        try:
            import qtpy
            from qtpy import QtCore
            logger.info("Using Qt: %s v%s.", qtpy.API, QtCore.__version__)
        except ImportError:
            logger.info("No usable Qt version found. GUI won't work.")
        sys.exit(0)


class LogLevel(FuncAction):

    def __init__(self, option_strings, dest, level=None, **kwargs):
        super(LogLevel, self).__init__(option_strings, dest, **kwargs)
        self.level = level

    def __call__(self, parser, namespace, values, option_string=None):
        loggers.set_console_level(self.level)
        setattr(namespace, self.dest, self.level)


class LogFile(argparse.Action):

    def __init__(self, option_strings, dest, level=None, **kwargs):
        super(LogFile, self).__init__(option_strings, dest, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        if values is None:
            setattr(namespace, self.dest, _LOG_DEFER)
        else:
            loggers.setup_logfile(values)
            setattr(namespace, self.dest, values)


class Debug(argparse.Action):
    def __init__(self, option_strings, dest, help=None):
        super(Debug, self).__init__(option_strings, dest,
                                    default=False, nargs=0,
                                    help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        loggers.enable_exceptions()
        setattr(namespace, self.dest, True)


class ListTests(FuncAction):

    @classmethod
    def get_tests(cls, settings):
        settings = settings.copy()
        tests = []
        for t in sorted([os.path.splitext(i)[0] for i in os.listdir(TEST_PATH)
                         if i.endswith('.conf')]):
            try:
                settings.load_test(t, informational=True)
                tests.append((t, settings.DESCRIPTION))
            except Exception as e:
                logger.exception(str(e))
        return tests

    def __call__(self, parser, namespace, values, option_string=None):
        tests = self.get_tests(namespace)
        logger.info('Available tests:')
        max_len = max([len(t[0]) for t in tests])
        for t, desc in tests:
            desc = desc.replace("\n", "\n" + " " * (max_len + 6))
            logger.info("  %-" + str(max_len) + "s :  %s", t, desc)
        sys.exit(0)


parser = ArgParser(description='The FLExible Network Tester.')

parser.add_argument(
    "args", nargs="*", type=unicode, metavar="host|test|input_file",
    help="Hostname, test name or input filenames.")

parser.add_argument(
    "-o", "--output",
    action="store", type=unicode, dest="OUTPUT", default="-",
    help="File to write processed output to (default standard out).")

parser.add_argument(
    "-D", "--data-dir",
    action="store", type=unicode, dest="DATA_DIR",
    help="Directory to store data files in. Defaults to the current directory.")

parser.add_argument(
    "-i", "--input",
    action="append", type=unicode, dest="INPUT", default=[],
    help="File to read input from (instead of running tests). "
    "Input files can also be specified as unqualified arguments "
    "without using the -i switch.")

parser.add_argument(
    "-f", "--format",
    action="store", type=unicode, dest="FORMAT", default='default',
    help="Select output format (one of plot, csv, org_table, stats, "
    "metadata, summary). Default: 'summary'.")

parser.add_argument(
    "-p", "--plot",
    action="store", type=unicode, dest="PLOT",
    help="Select which plot to output for the given test (implies -f plot if no"
    "formatter is selected). Use the --list-plots option to see available plots.")

parser.add_argument(
    "-t", "--title-extra",
    action="store", type=unicode, dest="TITLE", default="",
    help="Text to add to plot title and data file name.")

parser.add_argument(
    "-n", "--note",
    action="store", type=unicode, dest="NOTE",
    help="Add arbitrary text as a note to be stored in the JSON data file "
    "(under the NOTE key in the metadata object).")

parser.add_argument(
    "-r", "--rcfile",
    action="store", type=unicode, dest="RCFILE",
    default=os.path.expanduser("~/.flentrc"),
    help="Load configuration data from RCFILE (default ~/.flentrc).")

parser.add_argument(
    "-x", "--extended-metadata",
    action="store_true", dest="EXTENDED_METADATA",
    help="Collect extended metadata and store it with the data file. "
    "May include details of your machine you don't want to distribute; "
    "see man page.")

parser.add_argument(
    "--remote-metadata",
    action="append", type=unicode, dest="REMOTE_METADATA",
    metavar="HOSTNAME", default=[],
    help="Collect extended metadata from a remote host. HOSTNAME is passed "
    "verbatim to ssh, so can include hosts specified in ~/.ssh/config. This "
    "option can be specified multiple times. Note that gathering the data can "
    "take some time, since it involves executing several remote commands. "
    "This option implies --extended-metadata.")

parser.add_argument(
    "--gui",
    action="store_true", dest="GUI",
    help="Run the Flent GUI. All other options are used as defaults "
    "in the GUI, but can be changed once it is running.")

parser.add_argument(
    "--new-gui-instance",
    action="store_true", dest="NEW_GUI_INSTANCE",
    help="Start a new GUI instance. Otherwise, flent will try to "
    "connect to an already running GUI instance and have that load any new "
    "data files specified as arguments. Implies --gui.")

parser.add_argument(
    "--gui-no-defer", action="store_true", dest="GUI_NO_DEFER",
    help="Normally, the GUI defers redrawing plots until they are needed to "
    "avoid redrawing all open plots every time an option changes. This switch "
    "turns off that optimisation in favour of always redrawing everything "
    "straight away. This is useful when loading a bunch of plots from the "
    "command line and then wanting to flip through them without drawing delay.")

parser.add_argument(
    "-b", "--batch",
    action="append", type=unicode, dest="BATCH_NAMES", metavar="BATCH_NAME",
    default=[], help="Run test batch BATCH_NAME (must be specified in a batch "
    "file loaded by the --batch-file option). Can be supplied multiple times.")

parser.add_argument(
    "-B", "--batch-file", action="append", type=unicode, dest="BATCH_FILES",
    metavar="BATCH_FILE", default=[],
    help="Load batch file BATCH_FILE. Can be specified multiple times, in which "
    "case the files will be combined (with identically-named sections being "
    "overridden by later files). See the man page for an explanation of the "
    "batch file format.")

parser.add_argument(
    "--batch-override",
    action=Update, type=keyval, dest="BATCH_OVERRIDE", metavar="key=value",
    help="Override parameter 'key' in the batch config and set it to 'value'. "
    "The key name will be case folded to lower case. Can be specified multiple "
    "times.")

parser.add_argument(
    "--batch-dry-run",
    action="store_true", dest="BATCH_DRY",
    help="Dry batch run. Prints what would be done, but doesn't actually run any "
    "tests.")

parser.add_argument(
    "--batch-verbose",
    action="store_true", dest="BATCH_VERBOSE",
    help="Be verbose during batch run: Print all commands executed.")

parser.add_argument(
    "--batch-no-shuffle",
    action="store_false", dest="BATCH_SHUFFLE",
    help="Do not randomise the order of test runs within each batch.")

parser.add_argument(
    "--batch-no-timestamp",
    action="store_false", dest="BATCH_TIMESTAMP",
    help="Do not add a timestamp to batch output filenames. This keeps filenames "
    "stable, but requires that the filename_extra variable be unique for each "
    "test run. Results will be overwritten and a warning emitted if not.")

parser.add_argument(
    "--batch-repetitions", action="store", type=int, dest="BATCH_REPS",
    metavar="REPETITIONS",
    help="Shorthand for --batch-override 'repetitions=REPETITIONS'.")

parser.add_argument(
    "--batch-title",
    action="store", type=unicode, dest="BATCH_TITLE", metavar="TITLE",
    help="Shorthand for --batch-override 'batch_title=TITLE'.")

parser.add_argument(
    "--batch-resume",
    action="store", type=unicode, dest="BATCH_RESUME", metavar="DIR",
    help="Try to resume a previously interrupted batch run. The argument is "
    "the top-level output directory from the previous run. Tests for which "
    "data files already exist will be skipped.")

test_group = parser.add_argument_group(
    "Test configuration",
    "These options affect the behaviour of the test being run "
    "and have no effect when parsing input files.")

test_group.add_argument(
    "-H", "--host",
    action=AddHost, type=unicode, dest="HOSTS", metavar='HOST', default=[],
    help="Host to connect to for tests. For tests that support it, multiple "
    "hosts can be specified by supplying this option multiple times. Hosts can "
    "also be specified as unqualified arguments; this parameter guarantees that "
    "the argument be interpreted as a host name (rather than being subject to "
    "auto-detection between input files, hostnames and test names).")

test_group.add_argument(
    "--local-bind",
    action="append", type=unicode, dest="LOCAL_BIND", metavar='IP', default=[],
    help="Local hostname or IP address to bind to (for test tools that support "
    "this). Can be specified multiple times to get different local bind address "
    "per host.")

test_group.add_argument(
    "--remote-host",
    action=Update, type=keyval_int, dest="REMOTE_HOSTS", metavar='idx=HOSTNAME',
    help="A remote hostname to connect to when starting a test. The idx is "
    "the runner index, which is assigned sequentially by the number of *runners* "
    "(which is *not* the same as the number of hosts). Look for the 'IDX' key in "
    "SERIES_META for a test get the idx used here. This works by simply "
    "prepending 'ssh HOSTNAME' to the runner command, so it relies on the same "
    "binaries being in the same places on both machines, and won't work for all "
    "runners. Can be specified multiple times.")

test_group.add_argument(
    "-l", "--length",
    action="store", type=int, dest="LENGTH", default=60,
    help="Base test length (some tests may add some time to this).")

test_group.add_argument(
    "-s", "--step-size",
    action="store", type=float, dest="STEP_SIZE", default=0.2,
    help="Measurement data point step size.")

test_group.add_argument(
    "-d", "--delay",
    action="store", type=int, dest="DELAY", default=5,
    help="Number of seconds to delay parts of test (such as bandwidth loaders).")

test_group.add_argument(
    "-4", "--ipv4",
    action="store_const", const=4, dest="IP_VERSION",
    help="Use IPv4 for tests (some tests may ignore this).")

test_group.add_argument(
    "-6", "--ipv6",
    action="store_const", const=6, dest="IP_VERSION",
    help="Use IPv6 for tests (some tests may ignore this).")

test_group.add_argument(
    "--socket-timeout",
    action="store", type=int, dest="SOCKET_TIMEOUT", default=2,
    help="Socket timeout (in seconds) used for UDP delay measurement, to prevent "
    "stalls on packet loss. Only enabled if the installed netperf version is "
    "detected to support this (requires netperf version 2.7 or newer). Set to 0 "
    "to disable.")

test_group.add_argument(
    "--send-size",
    action="append", type=unicode, dest="SEND_SIZE", default=[],
    help="Send size (in bytes) used for TCP tests. netperf uses the socket "
    "buffer size by default, which if too large can cause spikes in the "
    "throughput results. Lowering this value will increase CPU usage but "
    "also improves the fidelity of the throughput results without having "
    "to decrease the socket buffer size. Can be specified multiple times, "
    "with each value corresponding to a stream of a test.")

test_group.add_argument(
    "--test-parameter",
    action=Update, type=keyval, dest="TEST_PARAMETERS", metavar='key=value',
    help="Arbitrary test parameter in key=value format. "
    "Key will be case folded to lower case. Some test configurations may "
    "alter behaviour based on values passed as test parameters. Additionally, "
    "the values are stored with the results metadata, and so can be used for "
    "arbitrary resultset categorisation. Can be specified multiple times.")

test_group.add_argument(
    "--swap-up-down",
    action="store_true", dest="SWAP_UPDOWN",
    help="Swap upstream and downstream directions for data transfer. This means "
    "that 'upload' will become 'download' and vice versa. Works by exchanging "
    "netperf TCP_MAERTS and TCP_STREAM parameters, so only works for tests "
    "that employ these as their data transfer, and only for the TCP streams.")

test_group.add_argument(
    "--socket-stats",
    action="store_true", dest="SOCKET_STATS",
    help="Parse socket stats during test. This will capture and parse socket "
    "statistics for all TCP upload flows during a test, adding TCP cwnd and RTT "
    "values to the test data. Requires the 'ss' utility to be present on the "
    "system, and can fail if there are too many simultaneous upload flows; which "
    "is why this option is not enabled by default.")

test_group.add_argument(
    "--marking-name",
    action=Update, dest="MARKING_NAMES", metavar='name=hexcode',
    type=keyval_transformer(keyfunc=lambda x: x.upper(),
                            valfunc=util.parse_int,
                            errmsg="Values must be integers"),
    help="Define a new symbolic name that can be used when specifying flow "
    "markings using the 'markings' test parameter. This can be used to make "
    "it easier to specify custom diffserv markings on flows by using symbolic "
    "names for each marking value instead of the hex codes. Values specified "
    "here will be used in addition to the common values (AFxx, CSx and EF - "
    "see man page for full list), and cannot override the built-in names. "
    "Names will be case-folded when matching.")

plot_group = parser.add_argument_group(
    "Plot configuration",
    "These options are used to configure the appearance of "
    "plot output and only make sense combined with -f plot.")

add_plotting_args(plot_group)

tool_group = parser.add_argument_group("Test tool-related options")

tool_group.add_argument(
    "--control-host",
    action="store", type=unicode, dest="CONTROL_HOST", metavar="HOST",
    help="Hostname for control connection for test tools that support it "
    "(netperf and D_ITG). If not supplied, this will be the same as the test "
    "target host. The per-flow test parameter setting takes precedence of this "
    "for multi-target tests.")

tool_group.add_argument(
    "--control-local-bind",
    action="store", type=unicode, dest="CONTROL_LOCAL_BIND", metavar="IP",
    help="Local IP to bind control connection to (for test tools that support it;"
    " currently netperf). If not supplied, the value for --local-bind will be "
    "used.")

tool_group.add_argument(
    "--netperf-control-port",
    action="store", type=int, dest="NETPERF_CONTROL_PORT", metavar="PORT",
    default=12865, help="Port for Netperf control server.")

tool_group.add_argument(
    "--ditg-control-port",
    action="store", type=int, dest="DITG_CONTROL_PORT", metavar="PORT",
    default=8000, help="Port for D-ITG control server.")

tool_group.add_argument(
    "--ditg-control-secret",
    action="store", type=unicode, dest="DITG_CONTROL_SECRET", metavar="SECRET",
    default='', help="Secret for D-ITG control server authentication.")

tool_group.add_argument(
    "--http-getter-urllist",
    action="append", type=unicode, dest="HTTP_GETTER_URLLIST", metavar="FILENAME",
    help="Filename containing the list of HTTP URLs to get. Can also be a URL, "
    "which will then be downloaded as part of each test iteration. If not "
    "specified, this is set to http://<hostname>/filelist.txt where <hostname> "
    "is the first test hostname. Can be specified multiple times, in which case "
    "one http-getter instance will be run for each URL list.")

tool_group.add_argument(
    "--http-getter-dns-servers",
    action="store", type=unicode, dest="HTTP_GETTER_DNS", metavar="DNS_SERVERS",
    help="DNS servers to use for http-getter lookups. Format is "
    "host[:port][,host[:port]]... This option will only work if libcurl supports "
    "it (needs to be built with the ares resolver). "
    "Default is none (use the system resolver).")

tool_group.add_argument(
    "--http-getter-timeout",
    action="store", type=int, dest="HTTP_GETTER_TIMEOUT", metavar="MILLISECONDS",
    help="Timeout for HTTP connections. Default is to use the test length.")

tool_group.add_argument(
    "--http-getter-workers",
    action="store", type=int, dest="HTTP_GETTER_WORKERS", metavar="NUMBER",
    default=4, help="Number of workers to use for getting HTTP urls. "
    "Default is 4.")

tool_group.add_argument(
    "--irtt-sampling-interval",
    action="store", type=int, dest="IRTT_INTERVAL", metavar="MILLISECONDS",
    help="Override the sampling interval passed to irtt, in milliseconds. Can be "
    "used to run irtt with a higher sampling frequency than the rest of the test. "
    "If set, this will override the sampling interval for all instances of irtt "
    "used in the test.")

misc_group = parser.add_argument_group("Misc and debugging options")

misc_group.add_argument(
    "-L", "--log-file",
    action=LogFile, type=unicode, dest="LOG_FILE", nargs='?',
    help="Write debug log (test program output) to log file. If the option is "
    "enabled but no file name is given, the log file name is derived from the "
    "test data filename.")

misc_group.add_argument(
    '--list-tests',
    action=ListTests,
    help="List available tests and exit.")

misc_group.add_argument(
    '--list-plots',
    action='store_true', dest="LIST_PLOTS",
    help="List available plots for selected test and exit.")

misc_group.add_argument(
    "-V", "--version",
    action=Version,
    help="Show flent version information and exit.")

misc_group.add_argument(
    "-v", "--verbose",
    action=LogLevel, level=loggers.DEBUG, dest="LOG_LEVEL",
    help="Enable verbose logging to console.")

misc_group.add_argument(
    "-q", "--quiet",
    action=LogLevel, level=loggers.WARNING, dest="LOG_LEVEL",
    help="Disable normal logging to console (and only log warnings and errors).")

misc_group.add_argument(
    "--debug-error",
    action=Debug, dest="DEBUG_ERROR",
    help="Print full exception backtraces to console.")


def new():
    return parser.parse_args([], namespace=Settings(DEFAULT_SETTINGS))


class Settings(argparse.Namespace):

    FLENT_VERSION = VERSION

    def __init__(self, defs):

        # Copy everything from defaults to make sure the defaults are not
        # modified.
        defaults = {}
        for k, v in defs.items():
            defaults[k] = deepcopy(v)
        argparse.Namespace.__init__(self, **defaults)

    def load_test_or_host(self, test_name):
        filename = os.path.join(TEST_PATH, test_name + ".conf")

        if not os.path.exists(filename):
            # Test not found, assume it's a hostname
            append_host(self.HOSTS, test_name)
        elif self.NAME is not None and self.NAME != test_name:
            raise RuntimeError("Multiple test names specified.")
        else:
            self.NAME = test_name

    def load_rcfile(self):
        self.process_args()
        if self.RCFILE == parser.get_default('RCFILE') and \
           not os.path.exists(self.RCFILE) and os.path.exists(OLD_RCFILE):
            logger.warning("Using old rcfile found at %s, "
                           "please rename to %s.",
                           OLD_RCFILE, self.RCFILE)
            self.RCFILE = OLD_RCFILE
        if os.path.exists(self.RCFILE):
            logger.debug("Loading rc file %s", self.RCFILE)

            config = RawConfigParser()
            config.optionxform = lambda x: x.upper()
            config.read(self.RCFILE)

            items = []

            if config.has_section('global'):
                items.extend(config.items('global'))
            if self.NAME is not None and config.has_section(self.NAME):
                items.extend(config.items(self.NAME))
            try:
                return self.parse_rcvalues(items)
            except (ValueError, argparse.ArgumentTypeError) as e:
                raise RuntimeError("Unable to parse RC values: %s" % e)
        return {}

    def parse_rcvalues(self, items):

        vals = {}

        for k, v in items:
            k = k.upper()
            t = parser.get_type(k)
            if t == bool:
                if type(v) == bool:
                    vals[k] = v
                elif v.lower() in ('1', 'yes', 'true', 'on'):
                    vals[k] = True
                elif v.lower() in ('0', 'no', 'false', 'off'):
                    vals[k] = False
                else:
                    raise ValueError("Not a boolean: %s" % v)
                logger.debug("Set value %s=%s from rc file", k, vals[k])
                continue

            elif t:

                val = t(v)
                c = parser.get_choices(k)
                if c and val not in c:
                    logger.warning("Invalid RC value '%s' for key %s. Ignoring",
                                   val, k)
                    continue
                if isinstance(val, dict) and k in vals:
                    vals[k].update(val)
                elif parser.is_list(k):
                    vals[k] = [t(i.strip()) for i in token_split(v)]
                else:
                    vals[k] = val
                logger.debug("Set value %s=%s from rc file", k, vals[k])

        return vals

    def load_rcvalues(self, vals, override=False):

        try:
            vals = self.parse_rcvalues(vals)
        except (ValueError, argparse.ArgumentTypeError) as e:
            raise RuntimeError("Unable to parse RC values: %s" % e)

        for k, v in vals.items():
            if override or getattr(self, k) == parser.get_default(k):
                setattr(self, k, v)

        self.update_implications()

    def load_test(self, test_name=None, informational=False):
        if test_name is not None:
            self.NAME = test_name
        if self.HOSTS:
            self.HOST = self.HOSTS[0]
        if hasattr(self, 'TOTAL_LENGTH'):
            self.TOTAL_LENGTH = self.LENGTH

        if not informational:
            self.lookup_hosts()

        if self.NAME is None:
            if informational:
                # Informational lookups should not fail
                return
            raise RuntimeError("Missing test name.")
        test_env = TestEnvironment(self.__dict__, informational)
        filename = os.path.join(TEST_PATH, self.NAME + ".conf")
        logger.debug("Executing test environment file %s", filename)
        s = test_env.execute(filename)

        for k, v in list(s.items()):
            if k == k.upper():
                setattr(self, k, v)

        self.update_defaults()

    def update_defaults(self):
        if hasattr(self, 'DEFAULTS'):
            for k, v in list(self.DEFAULTS.items()):
                if not hasattr(self, k) or getattr(self, k) is None:
                    setattr(self, k, v)

    def compute_missing_results(self, results):
        if "FROM_COMBINER" in results.meta():
            return
        for dname, dvals in self.DATA_SETS.items():
            if dname not in results:
                runner = runners.get(dvals['runner'])
                if issubclass(runner, runners.ComputingRunner):
                    logger.debug("Computing missing data series %s", dname)
                    try:
                        runner = runner(name=dname, settings=self,
                                        post=True, **dvals)
                        runner.compute_result(results)
                    except Exception as e:
                        logger.exception("Unable to compute missing data "
                                         "series '%s': '%s'.", dname, e)
                        raise

    def lookup_hosts(self):
        """If no explicit IP version is set, do a hostname lookup and try to"""
        version = 4
        for h in self.HOSTS:
            try:
                hostname = util.lookup_host(h)
                if hostname[0] == socket.AF_INET6:
                    version = 6
            except socket.gaierror as e:
                raise RuntimeError("Hostname lookup failed for host %s: %s"
                                   % (h, e))

        if self.IP_VERSION is None:
            self.IP_VERSION = version

    def __setattr__(self, k, v):
        if k in DICT_SETTINGS and isinstance(v, list):
            v = OrderedDict(v)

        object.__setattr__(self, k, v)

    def update(self, values):
        updated = False
        for k, v in list(values.items()):
            if not hasattr(self, k) or getattr(self, k) != v:
                updated = True
                setattr(self, k, v)
        return updated

    def items(self):
        return self.__dict__.items()

    def copy(self):
        return Settings(self)

    def process_args(self):
        for v in 'INPUT', 'SCALE_DATA', 'HOSTS':
            if not getattr(self, v):
                setattr(self, v, [])
        while self.args:
            a = self.args.pop(0)
            if os.path.exists(a):
                if self.SCALE_MODE and self.INPUT:
                    self.SCALE_DATA.append(a)
                else:
                    self.INPUT.append(a)
            else:
                self.load_test_or_host(a)

    def update_implications(self):
        # If run with no args and no controlling TTY, launch the GUI by default
        if not sys.stdin.isatty() and not sys.stdout.isatty() and \
           not sys.stderr.isatty() and len(sys.argv) < 2:
            self.GUI = True
        # Passing --new-gui-instance on the command line implies --gui, but
        # setting it in the rc file does not. When set here, before the rc file
        # is loaded, this has the desired effect.
        elif self.NEW_GUI_INSTANCE:
            self.GUI = True

        if self.REMOTE_METADATA:
            self.EXTENDED_METADATA = True

        if self.PLOT is not None and self.FORMAT == 'default':
            self.FORMAT = 'plot'

        if self.BATCH_REPS is not None:
            self.BATCH_OVERRIDE['repetitions'] = self.BATCH_REPS

        if self.BATCH_TITLE is not None:
            self.BATCH_OVERRIDE['batch_title'] = self.BATCH_TITLE

        if self.HOST is None and self.HOSTS:
            self.HOST = self.HOSTS[0]

        if self.DATA_DIR is None:
            self.DATA_DIR = os.path.dirname(self.OUTPUT) or '.'

        # For per-stream options, if only specified once duplicate them for each
        # host so they apply to all flows
        if len(self.LOCAL_BIND) == 1 and len(self.HOSTS) > 1:
            self.LOCAL_BIND *= len(self.HOSTS)
        if len(self.SEND_SIZE) == 1 and len(self.HOSTS) > 1:
            self.SEND_SIZE *= len(self.HOSTS)

        for k, v in self.BATCH_OVERRIDE.items():
            if not hasattr(v, 'lower'):
                continue
            if v.lower() in ('no', 'false', '0'):
                self.BATCH_OVERRIDE[k] = False
            elif v.lower() in ('yes', 'true', '0'):
                self.BATCH_OVERRIDE[k] = True


def load_gui(settings):
    from flent import gui
    gui.run_gui(settings)  # does not return


def load(argv):
    logger.info("Starting Flent %s using Python %s.", VERSION,
                sys.version.split()[0])

    # We parse the args twice - the first pass is just to get the test name and
    # the name of the rcfile to parse in order to get the defaults
    settings = parser.parse_args(argv, namespace=Settings(DEFAULT_SETTINGS))
    parser.set_defaults(**{k: v for k, v in settings.load_rcfile().items()
                           if getattr(settings, k) == parser.get_default(k)})

    settings = parser.parse_args(argv, namespace=Settings(DEFAULT_SETTINGS))
    settings.process_args()
    settings.update_implications()

    if settings.SCALE_DATA:
        scale_data = []
        for filename in settings.SCALE_DATA:
            if filename in settings.INPUT:
                # Do not load input file twice - makes it easier to select a set
                # of files for plot scaling and supply each one to -i without
                # having to change the other command line options each time.
                continue
            r = resultset.load(filename)
            scale_data.append(r)
        settings.SCALE_DATA = scale_data

    settings.load_test(informational=True)

    if settings.LIST_PLOTS:
        list_plots(settings)

    return settings


def list_plots(settings):
    plots = list(settings.PLOTS.keys())
    if not plots:
        logger.error("No plots available for test '%s'.", settings.NAME)
        sys.exit(0)

    logger.info("Available plots for test '%s':", settings.NAME)
    max_len = str(max([len(p) for p in plots]))
    for p in plots:
        logger.info("  %-" + max_len + "s :  %s",
                    p, settings.PLOTS[p]['description'])
    sys.exit(0)
