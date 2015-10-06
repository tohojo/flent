## -*- coding: utf-8 -*-
##
## settings.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:     25 November 2012
## Copyright (c) 2012-2015, Toke Høiland-Jørgensen
##
## This program is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import absolute_import, division, print_function, unicode_literals

import sys, os, optparse, socket, subprocess, time, collections, tempfile

from datetime import datetime
from copy import copy, deepcopy
from collections import OrderedDict

try:
    from configparser import RawConfigParser
except ImportError:
    from ConfigParser import RawConfigParser

from flent.build_info import VERSION
from flent.testenv import TestEnvironment, TEST_PATH
from flent import util, resultset, runners
from flent.util import Glob

OLD_RCFILE = os.path.expanduser("~/.netperf-wrapperrc")

DEFAULT_SETTINGS = {
    'NAME': None,
    'HOST': None,
    'HOSTS': [],
    'LOCAL_HOST': socket.gethostname(),
    'LOCAL_BIND': None,
    'STEP_SIZE': 0.2,
    'LENGTH': 60,
    'OUTPUT': '-',
    'DATA_DIR': None,
    'FORMAT': 'default',
    'TITLE': '',
    'OVERRIDE_TITLE': '',
    'NOTE': '',
    'RCFILE': os.path.expanduser("~/.flentrc"),
    'LOG_FILE': None,
    'INPUT': [],
    'DESCRIPTION': 'No description',
    'PLOTS': {},
    'IP_VERSION': None,
    'DELAY': 5,
    'SOCKET_TIMEOUT': 2,
    'TEST_PARAMETERS': {},
    'SWAP_UPDOWN': False,
    'TIME': datetime.utcnow(),
    'SCALE_DATA': [],
    'SCALE_MODE': False,
    'CONCATENATE': False,
    'ABSOLUTE_TIME': False,
    'SUBPLOT_COMBINE': False,
    'COMBINE_PRINT_N': True,
    'HOVER_HIGHLIGHT': None,
    'ANNOTATE': True,
    'PRINT_TITLE': True,
    'USE_MARKERS': True,
    'PRINT_LEGEND': True,
    'FILTER_LEGEND': False,
    'HORIZONTAL_LEGEND': False,
    'LOAD_MATPLOTLIBRC': True,
    'FILTER_REGEXP': [],
    'REPLACE_LEGEND': OrderedDict(),
    'ZERO_Y': False,
    'BOUNDS_X': [],
    'BOUNDS_Y': [],
    'INVERT_Y': False,
    'LOG_SCALE': True,
    'NORM_FACTORS': [],
    'FIG_WIDTH': None,
    'FIG_HEIGHT': None,
    'FIG_DPI': None,
    'EXTENDED_METADATA': False,
    'REMOTE_METADATA': [],
    'GUI': False,
    'NEW_GUI_INSTANCE': False,
    'GUI_NO_DEFER': False,
    'CONTROL_HOST': None,
    'CONTROL_LOCAL_BIND': None,
    'NETPERF_CONTROL_PORT': 12865,
    'DITG_CONTROL_PORT': 8000,
    'DITG_CONTROL_SECRET': '',
    'BATCH_NAME': None,
    'BATCH_NAMES': [],
    'BATCH_FILES': [],
    'BATCH_OVERRIDE': {},
    'BATCH_DRY': False,
    'BATCH_VERBOSE': False,
    'BATCH_REPS': None,
    'BATCH_RESUME': None,
    'HTTP_GETTER_URLLIST': None,
    'HTTP_GETTER_DNS': None,
    'HTTP_GETTER_TIMEOUT': None,
    'HTTP_GETTER_WORKERS': 4,
    'DEBUG_ERROR': False,
    }

CONFIG_TYPES = {
    'HOSTS': 'list',
    'LOCAL_BIND': 'str',
    'STEP_SIZE': 'float',
    'LENGTH': 'int',
    'OUTPUT': 'str',
    'DATA_DIR': 'str',
    'FORMAT': 'str',
    'TITLE': 'str',
    'NOTE': 'str',
    'LOG_FILE': 'str',
    'IP_VERSION': 'int',
    'DELAY': 'int',
    'SOCKET_TIMEOUT': 'int',
    'TEST_PARAMETERS': 'dict',
    'SWAP_UPDOWN': 'bool',
    'SCALE_MODE': 'bool',
    'SUBPLOT_COMBINE': 'bool',
    'COMBINE_PRINT_N': 'bool',
    'ANNOTATE': 'bool',
    'PRINT_TITLE': 'bool',
    'PRINT_LEGEND': 'bool',
    'FILTER_LEGEND': 'bool',
    'ZERO_Y': 'bool',
    'INVERT_Y': 'bool',
    'LOG_SCALE': 'bool',
    'EXTENDED_METADATA': 'bool',
    'REMOTE_METADATA': 'list',
    'CONTROL_HOST': 'str',
    'CONTROL_LOCAL_BIND': 'str',
    'NETPERF_CONTROL_PORT': 'int',
    'DITG_CONTROL_PORT': 'int',
    'DITG_CONTROL_SECRET': 'str',
    'NEW_GUI_INSTANCE': 'bool',
    'BATCH_FILES': 'list',
    'HTTP_GETTER_URLLIST': 'str',
    'HTTP_GETTER_DNS': 'str',
    'HTTP_GETTER_TIMEOUT': 'int',
    'HTTP_GETTER_WORKERS': 'int',
    }

DICT_SETTINGS = ('DATA_SETS', 'PLOTS')

def version(*args):
    print("Flent v%s.\nRunning on Python %s." %(VERSION, sys.version.replace("\n", " ")))
    try:
        import matplotlib, numpy
        print("Using matplotlib version %s on numpy %s." % (matplotlib.__version__, numpy.__version__))
    except ImportError:
        print("No matplotlib found. Plots won't be available.")
    try:
        from PyQt4 import QtCore
        print("Using PyQt4 version %s" % QtCore.PYQT_VERSION_STR)
    except ImportError:
        print("No PyQt4. GUI won't work.")
    sys.exit(0)



def check_float_pair(option, opt, value):
    try:
        if not "," in value:
            return (None, float(value))
        a,b = [s.strip() for s in value.split(",", 1)]
        return (float(a) if a else None,
                float(b) if b else None)
    except ValueError:
        raise optparse.OptionValueError("Invalid pair value: %s" % value)

class ExtendedOption(optparse.Option):
    ACTIONS = optparse.Option.ACTIONS + ("update",)
    STORE_ACTIONS = optparse.Option.STORE_ACTIONS + ("update",)
    TYPED_ACTIONS = optparse.Option.TYPED_ACTIONS + ("update",)
    ALWAYS_TYPED_ACTIONS = optparse.Option.ALWAYS_TYPED_ACTIONS + ("update",)
    TYPES = optparse.Option.TYPES + ("float_pair",)
    TYPE_CHECKER = copy(optparse.Option.TYPE_CHECKER)
    TYPE_CHECKER['float_pair'] = check_float_pair

    def take_action(self, action, dest, opt, value, values, parser):
        if action == 'update':
            if not '=' in value:
                raise optparse.OptionValueError("Invalid value '%s' (missing =) for option %s." % (value,opt))
            k,v = value.split('=', 1)
            values.ensure_value(dest, {})[k] = v
        else:
            optparse.Option.take_action(self, action, dest, opt, value, values, parser)



parser = optparse.OptionParser(description='Wrapper to run concurrent netperf-style tests.',
                               usage="Usage: %prog [options] <host|test|input file ...> ",
                               option_class=ExtendedOption)

parser.add_option("-o", "--output", action="store", type="string", dest="OUTPUT",
                  help="File to write processed output to (default standard out).")
parser.add_option("-D", "--data-dir", action="store", type="string", dest="DATA_DIR",
                  help="Directory to store data files in. Defaults to the current directory.")
parser.add_option("-i", "--input", action="append", type="string", dest="INPUT",
                  help="File to read input from (instead of running tests). Input files "
                  "can also be specified as unqualified arguments without using the -i switch.")
parser.add_option("-f", "--format", action="store", type="string", dest="FORMAT",
                  help="Select output format (plot, csv, org_table, stats, metadata). Default is "
                  "no processed output (just writes the JSON data file).")
parser.add_option("-p", "--plot", action="store", type="string", dest="PLOT",
                  help="Select which plot to output for the given test (implies -f plot). "
                  "Use the --list-plots option to see available plots.")
parser.add_option("-t", "--title-extra", action="store", type="string", dest="TITLE",
                  help="Text to add to plot title and data file name.")
parser.add_option("-n", "--note", action="store", type="string", dest="NOTE",
                  help="Add arbitrary text as a note to be stored in the JSON data file "
                  "(under the NOTE key in the metadata object).")
parser.add_option("-r", "--rcfile", action="store", type="string", dest="RCFILE",
                  help="Load configuration data from RCFILE (default ~/.flentrc).")
parser.add_option("-x", "--extended-metadata", action="store_true", dest="EXTENDED_METADATA",
                  help="Collect extended metadata and store it with the data file. "
                  "May include details of your machine you don't want to distribute; see man page.")
parser.add_option("--remote-metadata", action="append", type="string", dest="REMOTE_METADATA",
                  metavar="HOSTNAME",
                  help="Collect extended metadata from a remote host. HOSTNAME is passed "
                  "verbatim to ssh, so can include hosts specified in ~/.ssh/config. This "
                  "option can be specified multiple times. Note that gathering the data can "
                  "take some time, since it involves executing several remote commands. This option "
                  "implies --extended-metadata.")
parser.add_option("--gui", action="store_true", dest="GUI",
                  help="Run the flent GUI. All other options are used as defaults "
                  "in the GUI, but can be changed once it is running.")
parser.add_option("--new-gui-instance", action="store_true", dest="NEW_GUI_INSTANCE",
                  help="Start a new GUI instance. Otherwise, flent will try to "
                  "connect to an already running GUI instance and have that load any new "
                  "data files specified as arguments. Implies --gui.")
parser.add_option("--gui-no-defer", action="store_true", dest="GUI_NO_DEFER",
                  help="Normally, the GUI defers redrawing plots until they are needed to avoid "
                  "redrawing all open plots every time an option changes. This switch turns off "
                  "that optimisation in favour of always redrawing everything straight away. "
                  "This is useful when loading a bunch of plots from the command line and then "
                  "wanting to flip through them without drawing delay.")
parser.add_option("-b", "--batch", action="append", type="string", dest="BATCH_NAMES", metavar="BATCH_NAME",
                  help="Run test batch BATCH_NAME (must be specified in a batch file loaded "
                  "by the --batch-file option). Can be supplied multiple times.")
parser.add_option("-B", "--batch-file", action="append", type="string", dest="BATCH_FILES",
                  metavar="BATCH_FILE",
                  help="Load batch file BATCH_FILE. Can be specified multiple times, in which "
                  "case the files will be combined (with identically-named sections being overridden "
                  "by later files). See the man page for an explanation of the batch file format.")
parser.add_option("--batch-override", action="update", type="string", dest="BATCH_OVERRIDE",
                  metavar="key=value",
                  help="Override parameter 'key' in the batch config and set it to 'value'. "
                  "The key name will be case folded to lower case. Can be specified multiple times.")
parser.add_option("--batch-dry-run", action="store_true", dest="BATCH_DRY",
                  help="Dry batch run. Prints what would be done, but doesn't actually run any tests.")
parser.add_option("--batch-verbose", action="store_true", dest="BATCH_VERBOSE",
                  help="Be verbose during batch run: Print all commands executed.")
parser.add_option("--batch-repetitions", action="store", type='int', dest="BATCH_REPS", metavar="REPETITIONS",
                  help="Shorthand for --batch-override 'repetitions=REPETITIONS'.")
parser.add_option("--batch-resume", action="store", type='str', dest="BATCH_RESUME", metavar="DIR",
                  help="Try to resume a previously interrupted batch run. The argument is the top-level "
                  "output directory from the previous run. Tests for which data files already exist will "
                  "be skipped.")


test_group = optparse.OptionGroup(parser, "Test configuration",
                                  "These options affect the behaviour of the test being run "
                                  "and have no effect when parsing input files.")
test_group.add_option("-H", "--host", action="append", type="string", dest="HOSTS", metavar='HOST',
                  help="Host to connect to for tests. For tests that support it, multiple hosts "
                  "can be specified by supplying this option multiple times. Hosts can also be "
                  "specified as unqualified arguments; this parameter guarantees that the "
                  "argument be interpreted as a host name (rather than being subject to "
                  "auto-detection between input files, hostnames and test names).")
test_group.add_option("--local-bind", action="store", type="string", dest="LOCAL_BIND",
                  help="Local hostname or IP address to bind to (for test tools that support this).")
test_group.add_option("-l", "--length", action="store", type="int", dest="LENGTH",
                  help="Base test length (some tests may add some time to this).")
test_group.add_option("-s", "--step-size", action="store", type="float", dest="STEP_SIZE",
                  help="Measurement data point step size.")
test_group.add_option("-d", "--delay", action="store", type="int", dest="DELAY",
                  help="Number of seconds to delay parts of test (such as bandwidth "
                  "loaders).")
test_group.add_option("-4", "--ipv4", action="store_const", const=4, dest="IP_VERSION",
                  help="Use IPv4 for tests (some tests may ignore this).")
test_group.add_option("-6", "--ipv6", action="store_const", const=6, dest="IP_VERSION",
                  help="Use IPv6 for tests (some tests may ignore this).")
test_group.add_option("--socket-timeout", action="store", type=int, dest="SOCKET_TIMEOUT",
                  help="Socket timeout (in seconds) used for UDP delay measurement, to prevent "
                  "stalls on packet loss. Only enabled if the installed netperf version is "
                  "detected to support this (requires SVN version of netperf). "
                  "Default value: %d seconds. Set to 0 to disable." % DEFAULT_SETTINGS['SOCKET_TIMEOUT'])
test_group.add_option("--test-parameter", action="update", dest="TEST_PARAMETERS", metavar='key=value',
                  help="Arbitrary test parameter in key=value format. "
                  "Key will be case folded to lower case. Some test configurations may "
                  "alter behaviour based on values passed as test parameters. Additionally, "
                  "the values are stored with the results metadata, and so can be used for "
                  "arbitrary resultset categorisation. Can be specified multiple times.")
test_group.add_option("--swap-up-down", action="store_true", dest="SWAP_UPDOWN",
                      help="Swap upstream and downstream directions for data transfer. This means "
                      "that 'upload' will become 'download' and vice versa. Works by exchanging "
                      "netperf TCP_MAERTS and TCP_STREAM parameters, so only works for tests "
                      "that employ these as their data transfer, and only for the TCP streams.")
parser.add_option_group(test_group)

plot_group = optparse.OptionGroup(parser, "Plot configuration",
                                  "These options are used to configure the appearance of "
                                  "plot output and only make sense combined with -f plot.")

plot_group.add_option("-z", "--zero-y", action="store_true", dest="ZERO_Y",
                  help="Always start y axis of plot at zero, instead of auto-scaling the "
                  "axis (also disables log scales). Auto-scaling is still enabled for the "
                  "upper bound.")
plot_group.add_option("--bounds-x", action="append", dest="BOUNDS_X", type='float_pair',
                  help="Specify bounds of the plot X axis. If specifying one number, that will become "
                  "the upper bound. Specify two numbers separated by a comma to specify both "
                  "upper and lower bounds. To specify just the lower bound, add a comma afterwards. "
                  "Can be specified twice, corresponding to figures with multiple axes.")
plot_group.add_option("--bounds-y", action="append", dest="BOUNDS_Y", type='float_pair',
                  help="Specify bounds of the plot Y axis. If specifying one number, that will become "
                  "the upper bound. Specify two numbers separated by a comma to specify both "
                  "upper and lower bounds. To specify just the lower bound, add a comma afterwards. "
                  "Can be specified twice, corresponding to figures with multiple axes.")
plot_group.add_option("-I", "--invert-latency-y", action="store_true", dest="INVERT_Y",
                  help="Invert the y-axis for latency data series (making plots show 'better values "
                  "upwards').")
plot_group.add_option("--disable-log", action="store_false", dest="LOG_SCALE",
                  help="Disable log scales on plots.")
plot_group.add_option("--norm-factor", action="append", type='float', dest="NORM_FACTORS", metavar="FACTOR",
                  help="Factor to normalise data by. I.e. divide all data points by this value. "
                  "Can be specified multiple times, in which case each value corresponds to a "
                  "data series.")
plot_group.add_option("--scale-data", action="append", type="string", dest="SCALE_DATA",
                  help="Additional data files to consider when scaling the plot axes "
                  "(for plotting several plots with identical axes). Note, this displays "
                  "only the first data set, but with axis scaling taking into account the "
                  "additional data sets. Can be supplied multiple times; see also --scale-mode.")
plot_group.add_option("-S", "--scale-mode", action="store_true", dest="SCALE_MODE",
                  help="Treat file names (except for the first one) passed as unqualified "
                  "arguments as if passed as --scale-data (default as if passed as --input).")
plot_group.add_option("--concatenate", action="store_true", dest="CONCATENATE",
                  help="Concatenate multiple result sets into one data series.")
plot_group.add_option("--absolute-time", action="store_true", dest="ABSOLUTE_TIME",
                  help="Plot data points with absolute UNIX time on the x-axis.")
plot_group.add_option("--subplot-combine", action="store_true", dest="SUBPLOT_COMBINE",
                  help="When plotting multiple data series, plot each one on a separate subplot "
                  "instead of combining them into one plot (not supported for all plot types).")
plot_group.add_option("--no-print-n", action="store_false", dest="COMBINE_PRINT_N",
                  help="Do not print the number of data points on combined plots.")
plot_group.add_option("--no-annotation", action="store_false", dest="ANNOTATE",
                  help="Exclude annotation with hostnames, time and test length from plots.")
plot_group.add_option("--no-title", action="store_false", dest="PRINT_TITLE",
                  help="Exclude title from plots.")
plot_group.add_option("--override-title", action="store", type='string', dest="OVERRIDE_TITLE",
                  metavar="TITLE", help="Override plot title with this string. This parameter takes "
                  "precedence over --no-title.")
plot_group.add_option("--no-markers", action="store_false", dest="USE_MARKERS",
                  help="Don't use line markers to differentiate data series on plots.")
plot_group.add_option("--no-legend", action="store_false", dest="PRINT_LEGEND",
                  help="Exclude legend from plots.")
plot_group.add_option("--horizontal-legend", action="store_true", dest="HORIZONTAL_LEGEND",
                  help="Place a horizontal legend below the plot instead of a vertical one next to it. "
                  "Doesn't work well if there are too many items in the legend, obviously.")
plot_group.add_option("--filter-legend", action="store_true", dest="FILTER_LEGEND",
                  help="Filter legend labels by removing the longest common substring from all entries.")
plot_group.add_option("--filter-regexp", action="append", dest="FILTER_REGEXP", metavar="REGEXP",
                  help="Filter out supplied regular expression from legend names. Can be specified "
                  "multiple times, in which case the regular expressions will be filtered in the order "
                  "specified.")
plot_group.add_option("--replace-legend", action="update", dest="REPLACE_LEGEND", metavar="src=dest",
                  help="Replace 'src' with 'dst' in legends. Can be specified multiple times.")
plot_group.add_option("--figure-width", action="store", type='float', dest="FIG_WIDTH",
                  help="Figure width in inches. Used when saving plots to file and for default size of "
                  "the interactive plot window.")
plot_group.add_option("--figure-height", action="store", type='float', dest="FIG_HEIGHT",
                  help="Figure height in inches. Used when saving plots to file and for default size of "
                  "the interactive plot window.")
plot_group.add_option("--figure-dpi", action="store", type='float', dest="FIG_DPI",
                  help="Figure DPI. Used when saving plots to raster format files.")
plot_group.add_option("--no-matplotlibrc", action="store_false", dest="LOAD_MATPLOTLIBRC",
                  help="Don't load included matplotlibrc values. Use this if autodetection of custom "
                  "matplotlibrc fails and flent is inadvertently overriding rc values.")
plot_group.add_option("--no-hover-highlight", action="store_false", dest="HOVER_HIGHLIGHT",
                  help="Don't highlight data series on hover in interactive plot views. Use this if "
                      "redrawing is too slow, or the highlighting is undesired for other reasons.")
parser.add_option_group(plot_group)

combine_group = optparse.OptionGroup(parser, "Data combination configuration",
                                     "These options are used to combine several datasets, "
                                     "for instance to make aggregate plots.")

parser.add_option_group(combine_group)



tool_group = optparse.OptionGroup(parser, "Test tool-related options")
tool_group.add_option("--control-host", action="store", type="string", dest="CONTROL_HOST",
                      metavar="HOST",
                      help="Hostname for control connection for test tools that support it (netperf and D_ITG). "
                      "If not supplied, this will be the same as the test target.")
tool_group.add_option("--control-local-bind", action="store", type="string", dest="CONTROL_LOCAL_BIND",
                      metavar="IP",
                      help="Local IP to bind control connection to (for test tools that support it;"
                      " currently netperf). If not supplied, the value for --local-bind will be used.")
tool_group.add_option("--netperf-control-port", action="store", type=int, dest="NETPERF_CONTROL_PORT",
                      metavar="PORT",
                      help="Port for Netperf control server. Default: %d." % DEFAULT_SETTINGS['NETPERF_CONTROL_PORT'])
tool_group.add_option("--ditg-control-port", action="store", type=int, dest="DITG_CONTROL_PORT",
                      metavar="PORT",
                      help="Port for D-ITG control server. Default: %d." % DEFAULT_SETTINGS['DITG_CONTROL_PORT'])
tool_group.add_option("--ditg-control-secret", action="store", type="string", dest="DITG_CONTROL_SECRET",
                      metavar="SECRET",
                      help="Secret for D-ITG control server authentication. Default: '%s'." % DEFAULT_SETTINGS['DITG_CONTROL_SECRET'])
tool_group.add_option("--http-getter-urllist", action="store", type="string", dest="HTTP_GETTER_URLLIST",
                      metavar="FILENAME",
                      help="Filename containing the list of HTTP URLs to get. Can also be a URL, which will then "
                      "be downloaded as part of each test iteration. If not specified, this is set to "
                      "http://<hostname>/filelist.txt where <hostname> is the first test hostname.")
tool_group.add_option("--http-getter-dns-servers", action="store", type="string", dest="HTTP_GETTER_DNS",
                      metavar="DNS_SERVERS",
                      help="DNS servers to use for http-getter lookups. Format is host[:port][,host[:port]]... "
                      "This option will only work if libcurl supports it (needs to be built with the ares resolver). "
                      "Default is none (use the system resolver).")
tool_group.add_option("--http-getter-timeout", action="store", type="int", dest="HTTP_GETTER_TIMEOUT",
                      metavar="MILLISECONDS",
                      help="Timeout for HTTP connections. Default is to use the test length.")
tool_group.add_option("--http-getter-workers", action="store", type="int", dest="HTTP_GETTER_WORKERS",
                      metavar="NUMBER",
                      help="Number of workers to use for getting HTTP urls. Default is 4.")
parser.add_option_group(tool_group)


misc_group = optparse.OptionGroup(parser, "Misc and debugging options")
misc_group.add_option("-L", "--log-file", action="store", type="string", dest="LOG_FILE",
                  help="Write debug log (test program output) to log file.")
misc_group.add_option('--list-tests', action='store_true', dest="LIST_TESTS",
                  help="List available tests and exit.")
misc_group.add_option('--list-plots', action='store_true', dest="LIST_PLOTS",
                  help="List available plots for selected test and exit.")
misc_group.add_option("-V", "--version", action="callback", callback=version,
                  help="Show flent version information and exit.")
misc_group.add_option("--debug-error", action="store_true", dest="DEBUG_ERROR",
                  help="Debug errors: Don't catch unhandled exceptions.")
parser.add_option_group(misc_group)



class Settings(optparse.Values, object):

    FLENT_VERSION = VERSION

    def __init__(self, defs):

        # Copy everything from defaults to make sure the defaults are not modified.
        defaults = {}
        for k,v in defs.items():
            defaults[k] = deepcopy(v)
        optparse.Values.__init__(self, defaults)

    def load_test_or_host(self, test_name):
        filename = os.path.join(TEST_PATH, test_name + ".conf")

        if not os.path.exists(filename):
            # Test not found, assume it's a hostname
            self.HOSTS.append(test_name)
        elif self.NAME is not None and self.NAME != test_name:
            raise RuntimeError("Multiple test names specified.")
        else:
            self.NAME = test_name

    def load_rcfile(self):
        if self.RCFILE == DEFAULT_SETTINGS['RCFILE'] and \
           not os.path.exists(self.RCFILE) and os.path.exists(OLD_RCFILE):
            sys.stderr.write("Warning: Old rcfile found at %s, please rename to %s.\n" \
                             % (OLD_RCFILE, self.RCFILE))
            self.RCFILE = OLD_RCFILE
        if os.path.exists(self.RCFILE):

            config = RawConfigParser()
            config.optionxform = lambda x: x.upper()
            config.read(self.RCFILE)

            items = []

            if config.has_section('global'):
                items.extend(config.items('global'))
            if self.NAME is not None and config.has_section(self.NAME):
                items.extend(config.items(self.NAME))
            self.load_rcvalues(items)
        self.update_implications()

    def load_rcvalues(self, items, override=False):

        for k,v in items:
            k = k.upper()
            if k in CONFIG_TYPES and (override or getattr(self,k) == DEFAULT_SETTINGS[k]):
                if CONFIG_TYPES[k] == 'str':
                    setattr(self, k, v)
                elif CONFIG_TYPES[k] == 'int':
                    setattr(self, k, int(v))
                elif CONFIG_TYPES[k] == 'float':
                    setattr(self, k, float(v))
                elif CONFIG_TYPES[k] == 'list':
                    setattr(self, k, [i.strip() for i in v.split(",")])
                elif CONFIG_TYPES[k] == 'dict':
                    setattr(self, k, dict([[j.strip() for j in i.split('=',1)] for i in v.split(',')]))
                elif CONFIG_TYPES[k] == 'bool':
                    if type(v) == bool:
                        setattr(self, k, v)
                    elif v.lower() in ('1', 'yes', 'true', 'on'):
                        setattr(self, k, True)
                    elif v.lower() in ('0', 'no', 'false', 'off'):
                        setattr(self, k, False)
                    else:
                        raise ValueError("Not a boolean: %s" % v)
        self.update_implications()

    def load_test(self, test_name=None, informational=False):
        if test_name is not None:
            self.NAME=test_name
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
        s = test_env.execute(filename)

        for k,v in list(s.items()):
             if k == k.upper():
                 setattr(self, k, v)

        if 'DEFAULTS' in s:
            for k,v in list(s['DEFAULTS'].items()):
                if not hasattr(self, k):
                    setattr(self, k, v)



    def compute_missing_results(self, results):
        for dname, dvals in self.DATA_SETS.items():
            if not dname in results:
                runner = runners.get(dvals['runner'])
                if hasattr(runner, 'result') and isinstance(runner.result, collections.Callable):
                    try:
                        runner = runner(dname, settings, **dvals)
                        runner.result(results)
                    except Exception as e:
                        sys.stderr.write("Unable to compute missing data series '%s': '%s'.\n" % (dname, e))
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
                raise RuntimeError("Hostname lookup failed for host %s: %s" % (h,e))

        if self.IP_VERSION is None:
            self.IP_VERSION = version

    def __setattr__(self, k, v):
        if k in DICT_SETTINGS and isinstance(v, list):
            v = OrderedDict(v)

        object.__setattr__(self, k, v)

    def update(self, values):
        for k,v in list(values.items()):
            setattr(self, k, v)

    def items(self):
        return self.__dict__.items()

    def copy(self):
        return Settings(self)

    def update_implications(self):
        # If run with no args and no controlling TTY, launch the GUI by default
        if not sys.stdin.isatty() and not sys.stdout.isatty() and not sys.stderr.isatty() \
          and len(sys.argv) < 2:
          self.GUI = True
        # Passing --new-gui-instance on the command line implies --gui, but setting
        # it in the rc file does not. When set here, before the rc file is loaded,
        # this has the desired effect.
        elif self.NEW_GUI_INSTANCE:
            self.GUI = True

        if self.REMOTE_METADATA:
            self.EXTENDED_METADATA = True

        if hasattr(self, 'PLOT'):
            self.FORMAT = 'plot'

        if self.BATCH_REPS is not None:
            self.BATCH_OVERRIDE['repetitions'] = self.BATCH_REPS

        if self.HOST is None and self.HOSTS:
            self.HOST = self.HOSTS[0]

        if self.DATA_DIR is None:
            self.DATA_DIR = os.path.dirname(self.OUTPUT) or '.'

        for k,v in self.BATCH_OVERRIDE.items():
            if not hasattr(v, 'lower'):
                continue
            if v.lower() in ('no', 'false', '0'):
                self.BATCH_OVERRIDE[k] = False
            elif v.lower() in ('yes', 'true', '0'):
                self.BATCH_OVERRIDE[k] = True


settings = Settings(DEFAULT_SETTINGS)

def load_gui(settings):
    from flent import gui
    gui.run_gui(settings) # does not return

def load(argv):
    (dummy,args) = parser.parse_args(argv, values=settings)

    if hasattr(settings, 'LIST_TESTS') and settings.LIST_TESTS:
        list_tests()

    for a in args:
        if os.path.exists(a):
            if settings.SCALE_MODE and settings.INPUT:
                settings.SCALE_DATA.append(a)
            else:
                settings.INPUT.append(a)
        else:
            settings.load_test_or_host(a)

    settings.load_rcfile()

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

    if hasattr(settings, 'LIST_PLOTS') and settings.LIST_PLOTS:
        list_plots()

    return settings

def get_tests():
    tests = []
    settings = Settings(DEFAULT_SETTINGS)
    for t in sorted([os.path.splitext(i)[0] for i in os.listdir(TEST_PATH) if i.endswith('.conf')]):
        settings.update(DEFAULT_SETTINGS)
        settings.load_test(t, informational=True)
        tests.append((t,settings.DESCRIPTION))
    return tests

def list_tests():
    tests = get_tests()
    sys.stderr.write('Available tests:\n')
    max_len = max([len(t[0]) for t in tests])
    for t,desc in tests:
        desc = desc.replace("\n", "\n"+" "*(max_len+6))
        sys.stderr.write(("  %-"+str(max_len)+"s :  %s\n") % (t, desc))
    sys.exit(0)

def list_plots():
    plots = list(settings.PLOTS.keys())
    if not plots:
        sys.stderr.write("No plots available for test '%s'.\n" % settings.NAME)
        sys.exit(0)

    sys.stderr.write("Available plots for test '%s':\n" % settings.NAME)
    max_len = str(max([len(p) for p in plots]))
    for p in plots:
        sys.stderr.write(("  %-"+max_len+"s :  %s\n") % (p, settings.PLOTS[p]['description']))
    sys.exit(0)
