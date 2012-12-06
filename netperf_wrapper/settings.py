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

import sys, os, optparse, socket, gzip

from datetime import datetime

from fnmatch import fnmatch

from ordereddict import OrderedDict
from resultset import ResultSet
from build_info import DATA_DIR, VERSION

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
    'INPUT': None,
    'DESCRIPTION': 'No description',
    'PLOTS': {},
    'IP_VERSION': None,
    'DELAY': 5,
    'TIME': datetime.now(),
    'SCALE_DATA': [],
    }

TEST_PATH = os.path.join(DATA_DIR, 'tests')
DICT_SETTINGS = ('DATA_SETS', 'PLOTS')

def version(*args):
    print "Netperf-wrapper v%s." %(VERSION)
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
        return filter(lambda x: fnmatch(x, self.pattern) and x not in exclude, values)

    def __iter__(self):
        return iter((self,)) # allow list(g) to return [g]

    @classmethod
    def filter_dict(cls, d):
        # Expand glob patterns in parameters. Go through all items in the
        # dictionary looking for subkeys that is a Glob instance or a list
        # that has a Glob instance in it.
        for k,v in d.items():
            for g_k in v.keys():
                try:
                    v[g_k] = cls.expand_list(v[g_k], d.keys(), [k])
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
            })

    def execute(self, filename):
        try:
            execfile(filename, self.env)
            return self.env
        except (IOError, SyntaxError):
            raise RuntimeError("Unable to read test config file: '%s'" % filename)

    def include_test(self, name, env=None):
        self.execute(os.path.join(TEST_PATH, name))

    def require_host_count(self, count):
        if len(self.env['HOSTS']) < count and not self.env['INPUT']:
            raise RuntimeError("Need %d hosts, only %d specified" % (count, len(self.env['HOSTS'])))

parser = optparse.OptionParser(description='Wrapper to run concurrent netperf-style tests',
                               usage="usage: %prog [options] -H <host> test")

parser.add_option("-o", "--output", action="store", type="string", dest="OUTPUT",
                  help="file to write output to (default standard out)")
parser.add_option("-i", "--input", action="store", type="string", dest="INPUT",
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

class Settings(optparse.Values, object):

    def load_test(self, test_name):
        self.NAME = test_name
        if self.HOSTS:
            self.HOST = self.HOSTS[0]

        test_env = TestEnvironment(self.__dict__)
        s = test_env.execute(os.path.join(TEST_PATH, test_name + ".conf"))

        for k,v in s.items():
            if k == k.upper():
                setattr(self, k, v)

        if 'DEFAULTS' in s:
            for k,v in s['DEFAULTS'].items():
                if not hasattr(self, k):
                    setattr(self, k, v)

        if not 'TOTAL_LENGTH' in s:
            self.TOTAL_LENGTH = self.LENGTH

    def __setattr__(self, k, v):
        if k in DICT_SETTINGS and isinstance(v, list):
            v = OrderedDict(v)

        object.__setattr__(self, k, v)

    def update(self, values):
        for k,v in values.items():
            setattr(self, k, v)

settings = Settings(DEFAULT_SETTINGS)


def load():
    (dummy,args) = parser.parse_args(values=settings)

    if hasattr(settings, 'LIST_TESTS') and settings.LIST_TESTS:
        list_tests()

    if hasattr(settings, 'PLOT'):
        settings.FORMAT = 'plot'

    if settings.INPUT is not None:
        try:
            with open(settings.INPUT) as fp:
                if settings.INPUT.endswith(".gz"):
                    fp = gzip.GzipFile(fileobj=fp)
                results = ResultSet.load(fp)
                settings.load_test(results.meta("NAME"))
                settings.update(results.meta())
        except IOError:
            raise RuntimeError("Unable to read input file: '%s'" % settings.INPUT)
    else:
        if len(args) < 1:
            parser.error("Missing test name.")

        test_name = args[0]

        if os.path.exists(test_name):
            test_name = os.path.splitext(os.path.basename(test_file))[0]

        settings.load_test(test_name)
        results = ResultSet(NAME=settings.NAME,
                            HOST=settings.HOST,
                            TIME=settings.TIME,
                            LOCAL_HOST=settings.LOCAL_HOST,
                            TITLE=settings.TITLE,
                            LENGTH=settings.LENGTH,
                            TOTAL_LENGTH=settings.TOTAL_LENGTH,
                            STEP_SIZE=settings.STEP_SIZE,)

    if settings.SCALE_DATA:
        scale_data = []
        try:
            for filename in settings.SCALE_DATA:
                with open(filename) as fp:
                    if settings.INPUT.endswith(".gz"):
                        fp = gzip.GzipFile(fileobj=fp)
                    r = ResultSet.load(fp)
                    if r.meta("NAME") != settings.NAME:
                        raise RuntimeError(u"Setting name mismatch between test "
                                           "data and scale file %s" % filename)
                    scale_data.append(r)
        except IOError:
            raise RuntimeError("Unable to read input file: '%s'" % settings.INPUT)
        settings.SCALE_DATA = scale_data


    if hasattr(settings, 'LIST_PLOTS') and settings.LIST_PLOTS:
        list_plots()

    if not settings.HOSTS and not results:
        raise RuntimeError("Must specify host (-H option).")

    return settings, results

def list_tests():
    tests = sorted([os.path.splitext(i)[0] for i in os.listdir(TEST_PATH) if i.endswith('.conf')])
    sys.stderr.write('Available tests:\n')
    max_len = unicode(max([len(t) for t in tests]))
    for t in tests:
        settings.update(DEFAULT_SETTINGS)
        settings.load_test(t)
        sys.stderr.write((u"  %-"+max_len+u"s :  %s\n") % (t, settings.DESCRIPTION))
    sys.exit(0)

def list_plots():
    plots = settings.PLOTS.keys()
    if not plots:
        sys.stderr.write("No plots available for test '%s'.\n" % settings.NAME)
        sys.exit(0)

    sys.stderr.write("Available plots for test '%s':\n" % settings.NAME)
    max_len = unicode(max([len(p) for p in plots]))
    for p in plots:
        sys.stderr.write((u"  %-"+max_len+u"s :  %s\n") % (p, settings.PLOTS[p]['description']))
    sys.exit(0)
