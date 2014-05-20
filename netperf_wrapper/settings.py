## -*- coding: utf-8 -*-
##
## settings.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:     25 November 2012
## Copyright (c) 2012, Toke Høiland-Jørgensen
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

import sys, os, optparse, socket, subprocess, time

from datetime import datetime
from fnmatch import fnmatch
from copy import deepcopy

try:
    from configparser import RawConfigParser
except ImportError:
    from ConfigParser import RawConfigParser

try:
    from collections import OrderedDict
except ImportError:
    from netperf_wrapper.ordereddict import OrderedDict
from netperf_wrapper.build_info import DATA_DIR, VERSION
from netperf_wrapper import util, resultset

DEFAULT_SETTINGS = {
    'NAME': None,
    'HOST': None,
    'HOSTS': [],
    'LOCAL_HOST': socket.gethostname(),
    'STEP_SIZE': 0.2,
    'LENGTH': 60,
    'OUTPUT': '-',
    'FORMAT': 'default',
    'TITLE': '',
    'NOTE': '',
    'RCFILE': os.path.expanduser("~/.netperf-wrapperrc"),
    'LOG_FILE': None,
    'INPUT': [],
    'DESCRIPTION': 'No description',
    'PLOTS': {},
    'IP_VERSION': None,
    'DELAY': 5,
    'SOCKET_TIMEOUT': 2,
    'TIME': datetime.now(),
    'SCALE_DATA': [],
    'SCALE_MODE': False,
    'SUBPLOT_COMBINE': False,
    'ANNOTATE': True,
    'PRINT_TITLE': True,
    'PRINT_LEGEND': True,
    'FILTER_LEGEND': False,
    'ZERO_Y': False,
    'INVERT_Y': False,
    'LOG_SCALE': True,
    'EXTENDED_METADATA': False,
    'REMOTE_METADATA': [],
    'GUI': False,
    'NEW_GUI_INSTANCE': False,
    'DITG_CONTROL_HOST': None,
    'DITG_CONTROL_PORT': 8000,
    'DITG_CONTROL_SECRET': '',
    'BATCH_NAME': None,
    'BATCH_NAMES': [],
    'BATCH_FILES': [],
    'BATCH_OVERRIDE': [],
    'BATCH_DRY': False,
    'BATCH_REPS': None,
    'HTTP_GETTER_URLLIST': None,
    'HTTP_GETTER_DNS': None,
    'HTTP_GETTER_TIMEOUT': None,
    'HTTP_GETTER_WORKERS': 4,
    }

CONFIG_TYPES = {
    'HOSTS': 'list',
    'STEP_SIZE': 'float',
    'LENGTH': 'int',
    'OUTPUT': 'str',
    'FORMAT': 'str',
    'TITLE': 'str',
    'NOTE': 'str',
    'LOG_FILE': 'str',
    'IP_VERSION': 'int',
    'DELAY': 'int',
    'SOCKET_TIMEOUT': 'int',
    'SCALE_MODE': 'bool',
    'SUBPLOT_COMBINE': 'bool',
    'ANNOTATE': 'bool',
    'PRINT_TITLE': 'bool',
    'PRINT_LEGEND': 'bool',
    'FILTER_LEGEND': 'bool',
    'ZERO_Y': 'bool',
    'INVERT_Y': 'bool',
    'LOG_SCALE': 'bool',
    'EXTENDED_METADATA': 'bool',
    'REMOTE_METADATA': 'list',
    'DITG_CONTROL_HOST': 'str',
    'DITG_CONTROL_PORT': 'int',
    'DITG_CONTROL_SECRET': 'str',
    'NEW_GUI_INSTANCE': 'bool',
    'BATCH_FILES': 'list',
    'HTTP_GETTER_URLLIST': 'str',
    'HTTP_GETTER_DNS': 'str',
    'HTTP_GETTER_TIMEOUT': 'int',
    'HTTP_GETTER_WORKERS': 'int',
    }

TEST_PATH = os.path.join(DATA_DIR, 'tests')
DICT_SETTINGS = ('DATA_SETS', 'PLOTS')

def version(*args):
    print("Netperf-wrapper v%s.\nRunning on Python %s." %(VERSION, sys.version.replace("\n", " ")))
    try:
        import matplotlib, numpy
        print("Using matplotlib version %s on numpy %s." % (matplotlib.__version__, numpy.__version__))
    except ImportError:
        print("No matplotlib found. Plots won't be available.")
    sys.exit(0)


class Glob(object):
    """Object for storing glob patterns in matches"""

    def __init__(self, pattern, exclude=None):
        if exclude is None:
            self.exclude = []
        else:
            self.exclude = exclude
        self.pattern = pattern

    def filter(self, values, exclude):
        exclude += self.exclude
        return [x for x in values if fnmatch(x, self.pattern) and x not in exclude]

    def __iter__(self):
        return iter((self,)) # allow list(g) to return [g]

    @classmethod
    def filter_dict(cls, d):
        # Expand glob patterns in parameters. Go through all items in the
        # dictionary looking for subkeys that is a Glob instance or a list
        # that has a Glob instance in it.
        for k,v in list(d.items()):
            for g_k in list(v.keys()):
                try:
                    v[g_k] = cls.expand_list(v[g_k], list(d.keys()), [k])
                except TypeError:
                    continue
        return d

    @classmethod
    def expand_list(cls, l, values, exclude=None):
        l = list(l) # copy list, turns lone Glob objects into [obj]
        if exclude is None:
            exclude = []
        # Expand glob patterns in list. Go through all items in the
        # list  looking for Glob instances and expanding them.
        for i in range(len(l)):
            pattern = l[i]
            if isinstance(pattern, cls):
                l[i:i+1] = pattern.filter(values, exclude)
        return l

def finder(fn):
    """Decorator to put on find_* methods that makes sure common operations
    (i.e. skip if self.informational is set) are carried out correctly."""

    def decorated(self, *args, **kwargs):
        if self.informational:
            return ""
        return fn(self, *args, **kwargs)
    return decorated

class TestEnvironment(object):

    def __init__(self, env={}, informational=False):
        self.env = deepcopy(env)
        self.env.update({
            'glob': Glob,
            'o': OrderedDict,
            'include': self.include_test,
            'min_host_count': self.require_host_count,
            'find_ping': self.find_ping,
            'find_netperf': self.find_netperf,
            'find_itgsend': self.find_itgsend,
            'find_http_getter': self.find_http_getter,
            })
        self.informational = informational
        self.netperf = None
        self.itgsend = None
        self.http_getter = None

    def execute(self, filename):
        try:
            exec(compile(open(filename).read(), filename, 'exec'), self.env)
            return self.env
        except (IOError, SyntaxError) as e:
            raise RuntimeError("Unable to read test config file '%s': '%s'." % (filename, e))

    def include_test(self, name, env=None):
        self.execute(os.path.join(TEST_PATH, name))

    @finder
    def find_ping(self, ip_version, interval, length, host):
        """Find a suitable ping executable, looking first for a compatible
        `fping`, then falling back to the `ping` binary. Binaries are checked
        for the required capabilities."""

        if ip_version == 6:
            suffix = "6"
        else:
            suffix = ""

        fping = util.which('fping'+suffix)
        ping = util.which('ping'+suffix)

        if fping is not None:
            proc = subprocess.Popen([fping, '-h'],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            out,err = proc.communicate()
            if "print timestamp before each output line" in str(out):
                # fping has timestamp option, use it
                # there's no timeout parameter for fping, calculate a total number
                # of pings to send
                count = length // interval + 1
                interval = int(interval * 1000)

                return "%s -D -p %d -c %d %s" % (fping, interval, count, host)

        if ping is not None:
            # No checks atm; should check for presence of -D parameter
            return "%s -n -D -i %.2f -w %d %s" % (ping, max(0.2, interval), length, host)

        raise RuntimeError("No suitable ping tool found.")

    @finder
    def find_netperf(self, test, length, host, ip_version=None, marking=None, interval=None, extra_args=None):
        """Find a suitable netperf executable, and test for the required capabilities."""
        if ip_version is None:
            ip_version = self.env['IP_VERSION']

        if interval is None:
            interval = self.env['STEP_SIZE']

        args = "-P 0 -v 0 -D -%.1f" % interval
        if ip_version == 4:
            args += " -4"
        elif ip_version == 6:
            args += " -6"

        if marking is not None:
            args += " -Y %s" % marking

        args += " -H %s -t %s -l %d" % (host, test, length)

        if self.netperf is None:
            netperf = util.which('netperf', fail=True)

            # Try to figure out whether this version of netperf supports the -e
            # option for socket timeout on UDP_RR tests, and whether it has been
            # compiled with --enable-demo. Unfortunately, the --help message is
            # not very helpful for this, so the only way to find out is try to
            # invoke it and check for an error message. This has the side-effect
            # of having netperf attempt a connection to localhost, which can
            # stall, so we kill the process almost immediately.

            proc = subprocess.Popen([netperf, '-l', '1', '-D', '-0.2', '--', '-e', '1'],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            time.sleep(0.1) # should be enough time for netperf to output any error messages
            proc.kill()
            out,err = proc.communicate()
            if "Demo Mode not configured" in str(out):
                raise RuntimeError("%s does not support demo mode." % netperf)

            if "invalid option -- '0'" in str(err):
                raise RuntimeError("%s does not support accurate intermediate time reporting. You need netperf v2.6.0 or newer." % netperf)

            self.netperf = {'executable': netperf, "-e": False}

            if not "netperf: invalid option -- 'e'" in str(err):
                self.netperf['-e'] = True


        if extra_args is not None:
            args += " " + extra_args

        if test == "UDP_RR" and self.netperf["-e"]:
            # -- might have been passed as extra_args
            if not "--" in args:
                args += " --"
            args += " -e %d" % self.env['SOCKET_TIMEOUT']
        elif test in ("TCP_STREAM", "TCP_MAERTS", "omni"):
            args += " -f m"

        return "%s %s" % (self.netperf['executable'], args)

    @finder
    def find_itgsend(self, test_args, length, host):

        if self.itgsend is None:
            self.itgsend = util.which("ITGSend", fail=True)

        # We put placeholders in the command string to be filled out by string
        # format expansion by the runner once it has communicated with the control
        # server and obtained the port values.
        return "{binary} -Sdp {{signal_port}} -t {length} -a {dest_host} -rp {{dest_port}} {args}".format(
            binary=self.itgsend,
            length=int(length*1000),
            dest_host=host,
            args=test_args)

    @finder
    def find_http_getter(self, interval, length, workers = None, ip_version = None,
                         dns_servers = None, url_file = None, timeout = None):

        args = "-i %d -l %d" % (int(interval*1000.0), length)

        if url_file is None:
            url_file = self.env['HTTP_GETTER_URLLIST']

        if dns_servers is None:
            dns_servers = self.env['HTTP_GETTER_DNS']

        if timeout is None:
            timeout = self.env['HTTP_GETTER_TIMEOUT']

        if workers is None:
            workers = self.env['HTTP_GETTER_WORKERS']

        if ip_version is None:
            ip_version = self.env['IP_VERSION']

        if ip_version == 4:
            args += " -4"
        elif ip_version == 6:
            args += " -6"

        if timeout is None:
            args += " -t %d" % int(length * 1000)
        else:
            args += " -t %d" % timeout

        if workers is not None:
            args += " -n %d" % workers

        if dns_servers is not None:
            args += " -d '%s'" % dns_servers

        if url_file is None:
            args += " http://%s/filelist.txt" % self.env['HOST']
        else:
            args += " %s" % url_file

        if self.http_getter is None:
            self.http_getter = util.which('http-getter', fail=True)

        return "%s %s" % (self.http_getter, args)

    def require_host_count(self, count):
        if len(self.env['HOSTS']) < count:
            if self.informational:
                self.env['HOSTS'] = ['dummy']*count
            elif 'DEFAULTS' in self.env and 'HOSTS' in self.env['DEFAULTS'] and self.env['DEFAULTS']['HOSTS']:
                # If a default HOSTS list is set, populate the HOSTS list with
                # values from this list, repeating as necessary up to count
                def_hosts = self.env['DEFAULTS']['HOSTS']
                host_c = len(self.env['HOSTS'])
                missing_c = count-host_c
                self.env['HOSTS'].extend((def_hosts * (missing_c//len(def_hosts)+1))[:missing_c])
                if not self.env['HOST']:
                    self.env['HOST'] = self.env['HOSTS'][0]
            else:
                raise RuntimeError("Need %d hosts, only %d specified" % (count, len(self.env['HOSTS'])))

parser = optparse.OptionParser(description='Wrapper to run concurrent netperf-style tests.',
                               usage="Usage: %prog [options] <host|test|input file ...> ")

parser.add_option("-o", "--output", action="store", type="string", dest="OUTPUT",
                  help="File to write processed output to (default standard out). The JSON "
                  "data file is written to the same directory as this file, if provided. "
                  "Otherwise, the data file is written to the current directory.")
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
                  help="Load configuration data from RCFILE (default ~/.netperf-wrapperrc).")
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
                  help="Run the netperf-wrapper GUI. All other options are used as defaults "
                  "in the GUI, but can be changed once it is running.")
parser.add_option("--new-gui-instance", action="store_true", dest="NEW_GUI_INSTANCE",
                  help="Start a new GUI instance. Otherwise, netperf-wrapper will try to "
                  "connect to an already running GUI instance and have that load any new "
                  "data files specified as arguments. Implies --gui.")
parser.add_option("-b", "--batch", action="append", type="string", dest="BATCH_NAMES", metavar="BATCH_NAME",
                  help="Run test batch BATCH_NAME (must be specified in a batch file loaded "
                  "by the --batch-file option). Can be supplied multiple times.")
parser.add_option("-B", "--batch-file", action="append", type="string", dest="BATCH_FILES",
                  metavar="BATCH_FILE",
                  help="Load batch file BATCH_FILE. Can be specified multiple times, in which "
                  "case the files will be combined (with identically-named sections being overridden "
                  "by later files). See the man page for an explanation of the batch file format.")
parser.add_option("--batch-override", action="append", type="string", dest="BATCH_OVERRIDE",
                  metavar="OVERRIDE",
                  help="Specify a parameter to override in the batch config. Format is name=value. "
                  "Name will be case folded to lower case. Can be specified multiple times.")
parser.add_option("--batch-dry-run", action="store_true", dest="BATCH_DRY",
                  help="Dry batch run. Prints what would be done, but doesn't actually run any tests.")
parser.add_option("--batch-repetitions", action="store", type='int', dest="BATCH_REPS", metavar="REPETITIONS",
                  help="Shorthand for --batch-override 'repetitions=REPETITIONS'.")


test_group = optparse.OptionGroup(parser, "Test configuration",
                                  "These options affect the behaviour of the test being run "
                                  "and have no effect when parsing input files.")
test_group.add_option("-H", "--host", action="append", type="string", dest="HOSTS", metavar='HOST',
                  help="Host to connect to for tests. For tests that support it, multiple hosts "
                  "can be specified by supplying this option multiple times. Hosts can also be "
                  "specified as unqualified arguments; this parameter guarantees that the "
                  "argument be interpreted as a host name (rather than being subject to "
                  "auto-detection between input files, hostnames and test names).")
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
parser.add_option_group(test_group)

plot_group = optparse.OptionGroup(parser, "Plot configuration",
                                  "These options are used to configure the appearance of "
                                  "plot output and only make sense combined with -f plot.")

plot_group.add_option("-z", "--zero-y", action="store_true", dest="ZERO_Y",
                  help="Always start y axis of plot at zero, instead of auto-scaling the "
                  "axis (also disables log scales). Auto-scaling is still enabled for the "
                  "upper bound.")
plot_group.add_option("-I", "--invert-latency-y", action="store_true", dest="INVERT_Y",
                  help="Invert the y-axis for latency data series (making plots show 'better values "
                  "upwards').")
plot_group.add_option("--disable-log", action="store_false", dest="LOG_SCALE",
                  help="Disable log scales on plots.")
plot_group.add_option("--scale-data", action="append", type="string", dest="SCALE_DATA",
                  help="Additional data files to consider when scaling the plot axes "
                  "(for plotting several plots with identical axes). Note, this displays "
                  "only the first data set, but with axis scaling taking into account the "
                  "additional data sets. Can be supplied multiple times; see also --scale-mode.")
plot_group.add_option("-S", "--scale-mode", action="store_true", dest="SCALE_MODE",
                  help="Treat file names (except for the first one) passed as unqualified "
                  "arguments as if passed as --scale-data (default as if passed as --input).")
plot_group.add_option("--subplot-combine", action="store_true", dest="SUBPLOT_COMBINE",
                  help="When plotting multiple data series, plot each one on a separate subplot "
                  "instead of combining them into one plot (not supported for all plot types).")
plot_group.add_option("--no-annotation", action="store_false", dest="ANNOTATE",
                  help="Exclude annotation with hostnames, time and test length from plots.")
plot_group.add_option("--no-legend", action="store_false", dest="PRINT_LEGEND",
                  help="Exclude legend from plots.")
plot_group.add_option("--no-title", action="store_false", dest="PRINT_TITLE",
                  help="Exclude title from plots.")
plot_group.add_option("--filter-legend", action="store_true", dest="FILTER_LEGEND",
                  help="Filter legend labels by removing the longest common substring from all entries.")
parser.add_option_group(plot_group)


tool_group = optparse.OptionGroup(parser, "Test tool-related options")
tool_group.add_option("--ditg-control-host", action="store", type="string", dest="DITG_CONTROL_HOST",
                      metavar="HOST",
                      help="Hostname for D-ITG control server. Default: First hostname of test target.")
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
                  help="Show netperf-wrapper version information and exit.")
parser.add_option_group(misc_group)



class Settings(optparse.Values, object):

    NETPERF_WRAPPER_VERSION = VERSION

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
                elif CONFIG_TYPES[k] == 'bool':
                    if type(v) == bool:
                        setattr(self, k, v)
                    elif v.lower() in ('1', 'yes', 'true', 'on'):
                        setattr(self, k, True)
                    elif v.lower() in ('0', 'no', 'false', 'off'):
                        setattr(self, k, False)
                    else:
                        raise ValueError("Not a boolean: %s" % v)

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
            self.BATCH_OVERRIDE.append('repetitions=%d' % self.BATCH_REPS)



settings = Settings(DEFAULT_SETTINGS)

def load_gui(settings):
    from netperf_wrapper import gui
    gui.run_gui(settings) # does not return

def load():
    (dummy,args) = parser.parse_args(values=settings)

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

def list_tests():
    tests = sorted([os.path.splitext(i)[0] for i in os.listdir(TEST_PATH) if i.endswith('.conf')])
    sys.stderr.write('Available tests:\n')
    max_len = max([len(t) for t in tests])
    for t in tests:
        settings.update(DEFAULT_SETTINGS)
        settings.load_test(t, informational=True)
        desc = settings.DESCRIPTION.replace("\n", "\n"+" "*(max_len+6))
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
