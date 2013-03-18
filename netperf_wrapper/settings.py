## -*- coding: utf-8 -*-
##
## settings.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:     25 november 2012
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

import sys, os, optparse, socket, subprocess

from datetime import datetime

from fnmatch import fnmatch

try:
    from collections import OrderedDict
except ImportError:
    from netperf_wrapper.ordereddict import OrderedDict
from netperf_wrapper.resultset import ResultSet
from netperf_wrapper.build_info import DATA_DIR, VERSION
from netperf_wrapper import util

DEFAULT_SETTINGS = {
    'HOST': None,
    'HOSTS': [],
    'LOCAL_HOST': socket.gethostname(),
    'STEP_SIZE': 0.2,
    'LENGTH': 60,
    'OUTPUT': '-',
    'FORMAT': 'default',
    'TITLE': '',
    'LOG_FILE': None,
    'INPUT': [],
    'DESCRIPTION': 'No description',
    'PLOTS': {},
    'IP_VERSION': None,
    'DELAY': 5,
    'TIME': datetime.now(),
    'SCALE_DATA': [],
    'ANNOTATE': True,
    'PRINT_TITLE': True,
    'PRINT_LEGEND': True,
    }

TEST_PATH = os.path.join(DATA_DIR, 'tests')
DICT_SETTINGS = ('DATA_SETS', 'PLOTS')

def version(*args):
    print("Netperf-wrapper v%s." %(VERSION))
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

class TestEnvironment(object):

    def __init__(self, env={}):
        self.env = dict(env)
        self.env.update({
            'glob': Glob,
            'o': OrderedDict,
            'include': self.include_test,
            'min_host_count': self.require_host_count,
            'find_ping': self.find_ping,
            })

    def execute(self, filename):
        try:
            exec(compile(open(filename).read(), filename, 'exec'), self.env)
            return self.env
        except (IOError, SyntaxError):
            raise RuntimeError("Unable to read test config file: '%s'" % filename)

    def include_test(self, name, env=None):
        self.execute(os.path.join(TEST_PATH, name))

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
            return "%s -D -i %.2f -w %d %s" % (ping, max(0.2, interval), length, host)

        raise RuntimeError("No suitable ping tool found.")


    def require_host_count(self, count):
        if len(self.env['HOSTS']) < count:
            if 'DEFAULTS' in self.env and 'HOSTS' in self.env['DEFAULTS'] and self.env['DEFAULTS']['HOSTS']:
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

parser = optparse.OptionParser(description='Wrapper to run concurrent netperf-style tests',
                               usage="usage: %prog [options] -H <host> test")

parser.add_option("-o", "--output", action="store", type="string", dest="OUTPUT",
                  help="file to write output to (default standard out)")
parser.add_option("-i", "--input", action="append", type="string", dest="INPUT",
                  help="file to read input from (instead of running tests)")
parser.add_option("-f", "--format", action="store", type="string", dest="FORMAT",
                  help="select output format (plot, csv, org_table)")
parser.add_option("-p", "--plot", action="store", type="string", dest="PLOT",
                  help="select which plot to output for the given test (implies -f plot)")
parser.add_option("-H", "--host", action="append", type="string", dest="HOSTS", metavar='HOST',
                  help="host to connect to for tests. Specify multiple hosts with multiple -H "
                  "options (not all tests support this).")
parser.add_option("-t", "--title-extra", action="store", type="string", dest="TITLE",
                  help="text to add to plot title")
parser.add_option("-L", "--log-file", action="store", type="string", dest="LOG_FILE",
                  help="write debug log (test program output) to log file")
parser.add_option("-l", "--length", action="store", type="int", dest="LENGTH",
                  help="base test length (some tests may add some time to this)")
parser.add_option("-s", "--step-size", action="store", type="float", dest="STEP_SIZE",
                  help="measurement data point step size")
parser.add_option("-d", "--delay", action="store", type="int", dest="DELAY",
                  help="number of seconds to delay second parts of test (such as bandwidth loaders)")
parser.add_option("-4", "--ipv4", action="store_const", const=4, dest="IP_VERSION",
                  help="use IPv4 for tests (some tests may ignore this)")
parser.add_option("-6", "--ipv6", action="store_const", const=6, dest="IP_VERSION",
                  help="use IPv6 for tests (some tests may ignore this)")

parser.add_option("-V", "--version", action="callback", callback=version,
                  help="show netperf-wrapper version and exit")

parser.add_option('--list-tests', action='store_true', dest="LIST_TESTS",
                  help="list available tests")
parser.add_option('--list-plots', action='store_true', dest="LIST_PLOTS",
                  help="list available plots for selected test")
parser.add_option("--scale-data", action="append", type="string", dest="SCALE_DATA",
                  help="additional data files to use for scaling the plot axes "
                  "(can be supplied multiple times)")
parser.add_option("--no-annotation", action="store_false", dest="ANNOTATE",
                  help="do not annotate plots with hosts, time and test length")
parser.add_option("--no-legend", action="store_false", dest="PRINT_LEGEND",
                  help="do not print plot legend")
parser.add_option("--no-title", action="store_false", dest="PRINT_TITLE",
                  help="do not print plot title")

class Settings(optparse.Values, object):

    def load_test(self, test_name):
        self.NAME = test_name
        if self.HOSTS:
            self.HOST = self.HOSTS[0]

        self.lookup_hosts()

        test_env = TestEnvironment(self.__dict__)
        filename = os.path.join(TEST_PATH, test_name + ".conf")
        if not os.path.exists(filename):
            raise RuntimeError("No config file found for test '%s'" % test_name)
        s = test_env.execute(filename)

        for k,v in list(s.items()):
            if k == k.upper():
                setattr(self, k, v)

        if 'DEFAULTS' in s:
            for k,v in list(s['DEFAULTS'].items()):
                if not hasattr(self, k):
                    setattr(self, k, v)

        if not 'TOTAL_LENGTH' in s:
            self.TOTAL_LENGTH = self.LENGTH

    def lookup_hosts(self):
        """If no explicit IP version is set, do a hostname lookup and try to"""
        version = 4
        for h in self.HOSTS:
            try:
                hostnames = socket.getaddrinfo(h, None, socket.AF_UNSPEC,
                                               socket.SOCK_STREAM)
                if not hostnames:
                    raise RuntimeError("Found no hostnames on lookup of %s" % h)
                hostname = hostnames[0]
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

settings = Settings(DEFAULT_SETTINGS)


def load():
    (dummy,args) = parser.parse_args(values=settings)

    if hasattr(settings, 'LIST_TESTS') and settings.LIST_TESTS:
        list_tests()

    if hasattr(settings, 'PLOT'):
        settings.FORMAT = 'plot'

    if settings.INPUT:
        results = []
        test_name = None
        for filename in settings.INPUT:
            r = ResultSet.load_file(filename)
            if test_name is not None and test_name != r.meta("NAME"):
                raise RuntimeError("Result sets must be from same test (found %s/%s)" % (test_name, r.meta("NAME")))
            test_name = r.meta("NAME")
            results.append(r)


        settings.update(results[0].meta())
        settings.load_test(test_name)
    else:
        if len(args) < 1:
            parser.error("Missing test name.")

        test_name = args[0]

        settings.load_test(test_name)
        results = [ResultSet(NAME=settings.NAME,
                            HOST=settings.HOST,
                            HOSTS=settings.HOSTS,
                            TIME=settings.TIME,
                            LOCAL_HOST=settings.LOCAL_HOST,
                            TITLE=settings.TITLE,
                            LENGTH=settings.LENGTH,
                            TOTAL_LENGTH=settings.TOTAL_LENGTH,
                            STEP_SIZE=settings.STEP_SIZE,)]

    if settings.SCALE_DATA:
        scale_data = []
        for filename in settings.SCALE_DATA:
            if filename == settings.INPUT:
                # Do not load input file twice - makes it easier to select a set
                # of files for plot scaling and supply each one to -i without
                # having to change the other command line options each time.
                continue
            r = ResultSet.load_file(filename)
            if r.meta("NAME") != settings.NAME:
                raise RuntimeError("Setting name mismatch between test "
                                   "data and scale file %s" % filename)
            scale_data.append(r)
        settings.SCALE_DATA = scale_data


    if hasattr(settings, 'LIST_PLOTS') and settings.LIST_PLOTS:
        list_plots()

    if not settings.HOSTS and not results:
        raise RuntimeError("Must specify host (-H option).")

    return settings, results

def list_tests():
    tests = sorted([os.path.splitext(i)[0] for i in os.listdir(TEST_PATH) if i.endswith('.conf')])
    sys.stderr.write('Available tests:\n')
    max_len = str(max([len(t) for t in tests]))
    for t in tests:
        settings.update(DEFAULT_SETTINGS)
        settings.load_test(t)
        sys.stderr.write(("  %-"+max_len+"s :  %s\n") % (t, settings.DESCRIPTION))
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
