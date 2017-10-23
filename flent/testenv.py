# -*- coding: utf-8 -*-
#
# testenv.py
#
# Author:   Toke Høiland-Jørgensen (toke@toke.dk)
# Date:     17 September 2014
# Copyright (c) 2014-2016, Toke Høiland-Jørgensen
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

import os

from collections import OrderedDict
from copy import deepcopy
from itertools import cycle, islice

from flent import util, runners
from flent.util import Glob
from flent.build_info import DATA_DIR
from flent.loggers import get_logger

TEST_PATH = os.path.join(DATA_DIR, 'tests')
logger = get_logger(__name__)

try:
    from os import cpu_count
except ImportError:
    from multiprocessing import cpu_count

try:
    CPU_COUNT = cpu_count()
except NotImplementedError:
    CPU_COUNT = 1

try:
    from itertools import zip_longest
except ImportError:
    from itertools import izip_longest as zip_longest

SPECIAL_PARAM_NAMES = ['upload_streams', 'download_streams']
SPECIAL_PARAM_MAP = {'num_cpus': CPU_COUNT}


class _no_default():
    pass


def finder(fn):
    """Decorator to put on find_* methods that makes sure common operations
    (i.e. skip if self.informational is set) are carried out correctly."""

    def decorated(self, *args, **kwargs):
        if self.informational:
            return ""
        ret = fn(self, *args, **kwargs)
        return ret
    return decorated


class TestEnvironment(object):

    def __init__(self, env={}, informational=False):
        self.env = self.replace_testparms(deepcopy(env))
        self.env.update({
            'glob': Glob,
            'o': OrderedDict,
            'include': self.include_test,
            'min_host_count': self.require_host_count,
            'find_ping': self.find_ping,
            'find_iperf': self.find_iperf,
            'find_netperf': self.find_netperf,
            'find_itgsend': self.find_itgsend,
            'find_http_getter': self.find_http_getter,
            'find_tc_iterate': self.find_tc_iterate,
            'find_stat_iterate': self.find_stat_iterate,
            'find_wifistats_iterate': self.find_wifistats_iterate,
            'find_netstat_iterate': self.find_netstat_iterate,
            'set_test_parameter': self.set_test_parameter,
            'get_test_parameter': self.get_test_parameter,
            'try_test_parameters': self.try_test_parameters,
            'parse_int': self.parse_int,
            'zip_longest': zip_longest,
        })
        self.informational = informational
        self.itgsend = None
        self.http_getter = None
        self.orig_hosts = self.env['HOSTS']

    def execute(self, filename):
        try:
            with open(filename) as fp:
                exec(compile(fp.read(), filename, 'exec'), self.env)

            # Informational loading can override HOSTS to satisfy
            # require_host_count(); this should not be propagated.
            if self.informational:
                self.env['HOSTS'] = self.orig_hosts
            return self.expand_duplicates(self.env)
        except Exception as e:
            raise RuntimeError(
                "Unable to read test config file '%s': '%s'." % (filename, e))

    def replace_testparms(self, env):
        if 'TEST_PARAMETERS' not in env:
            return env

        tp = env['TEST_PARAMETERS']
        for k in SPECIAL_PARAM_NAMES:
            if k in tp and tp[k] in SPECIAL_PARAM_MAP:
                tp[k] = SPECIAL_PARAM_MAP[tp[k]]
        return env

    def expand_duplicates(self, env):
        new_data_sets = []
        if 'DATA_SETS' not in env:
            return env
        for k, v in env['DATA_SETS'].items():
            try:
                for i in range(int(v['duplicates'])):
                    new_data_sets.append(
                        ("%s::%d" % (k, i + 1), dict(v,
                                                     id=str(i + 1),
                                                     duplicates=None)))
            except (KeyError, TypeError):
                new_data_sets.append((k, v))
            except ValueError:
                raise RuntimeError(
                    "Invalid number of duplicates: %s" % v['duplicates'])
            env['DATA_SETS'] = OrderedDict(new_data_sets)
        return env

    def include_test(self, name, env=None):
        self.execute(os.path.join(TEST_PATH, name))

    def set_test_parameter(self, name, value):
        self.env['TEST_PARAMETERS'][name] = value

    def get_test_parameter(self, name, default=_no_default, split=False):
        try:
            ret = self.env['TEST_PARAMETERS'][name]
            if split:
                ret = ret.split(",")
            return ret
        except KeyError:
            if default is not _no_default:
                return default
            if self.informational:
                return None
            raise RuntimeError("Missing required test parameter: %s" % name)

    def try_test_parameters(self, names, default=_no_default):
        for name in names:
            if name in self.env['TEST_PARAMETERS']:
                return self.env['TEST_PARAMETERS'][name]

        # Didn't find a value; hand over to get_test_parameter for error
        # handling
        return self.get_test_parameter(names[0], default)

    def parse_int(self, val):
        try:
            try:
                return int(val)
            except ValueError:
                if val.startswith("0x"):
                    return int(val, 16)
                raise
        except:
            raise RuntimeError("Invalid integer value: %s" % val)

    def find_ping(self, ip_version, interval, length, host, **args):
        """Find a suitable ping."""

        args.setdefault('local_bind', (self.env['LOCAL_BIND'][0]
                                       if self.env['LOCAL_BIND'] else None))
        args['ip_version'] = ip_version
        args['interval'] = interval
        args['length'] = length
        args['host'] = host

        return args

    @finder
    def find_iperf(self, host, interval, length, ip_version, local_bind=None,
                   no_delay=False, udp=False, bw=None):
        """Find a suitable iperf."""
        if local_bind is None:
            local_bind = self.env['LOCAL_BIND'][
                0] if self.env['LOCAL_BIND'] else None

        # Main code moved to the PingRunner class to be able to take advantage
        # of the parser code there.
        return runners.IperfCsvRunner.find_binary(host, interval, length,
                                                  ip_version, udp=udp, bw=bw,
                                                  local_bind=local_bind)

    def find_netperf(self, test, length, host, **args):
        """Find a suitable netperf executable, and test for the required
        capabilities."""

        if test.lower() == 'omni':
            raise RuntimeError("Use of netperf 'omni' test is not supported")

        args.setdefault('ip_version', self.env['IP_VERSION'])
        args.setdefault('interval', self.env['STEP_SIZE'])
        args.setdefault('control_host', self.env['CONTROL_HOST'] or host)
        args.setdefault('control_port', self.env['NETPERF_CONTROL_PORT'])
        args.setdefault('local_bind', self.env['LOCAL_BIND'][
                        0] if self.env['LOCAL_BIND'] else "")
        args.setdefault('control_local_bind', self.env[
                        'CONTROL_LOCAL_BIND'] or args['local_bind'])
        args.setdefault('extra_args', "")
        args.setdefault('extra_test_args', "")
        args.setdefault('format', "")
        args.setdefault('marking', "")
        args.setdefault('cong_control',
                        self.get_test_parameter('tcp_cong_control', ''))
        args.setdefault('socket_timeout', self.env['SOCKET_TIMEOUT'])

        if self.env['SWAP_UPDOWN']:
            if test == 'TCP_STREAM':
                test = 'TCP_MAERTS'
            elif test == 'TCP_MAERTS':
                test = 'TCP_STREAM'

        args['test'] = test
        args['length'] = length
        args['host'] = host

        return args

    @finder
    def find_itgsend(self, test_args, length, host, local_bind=None):

        if local_bind is None:
            local_bind = self.env['LOCAL_BIND'][
                0] if self.env['LOCAL_BIND'] else None

        if self.itgsend is None:
            self.itgsend = util.which("ITGSend", fail=True)

        # We put placeholders in the command string to be filled out by string
        # format expansion by the runner once it has communicated with the control
        # server and obtained the port values.
        return "{binary} -Sdp {{signal_port}} -t {length} {local_bind} " \
            "-a {dest_host} -rp {{dest_port}} {args}".format(
                binary=self.itgsend,
                length=int(length * 1000),
                dest_host=host,
                local_bind="-sa {0} -Ssa {0}".format(
                    local_bind) if local_bind else "",
                args=test_args)

    @finder
    def find_http_getter(self, interval, length, workers=None, ip_version=None,
                         dns_servers=None, url_file=None, timeout=None):

        args = "-i %d -l %d" % (int(interval * 1000.0), length)

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

    @finder
    def find_tc_iterate(self, *args, **kwargs):
        """Find a suitable tc_iterate script."""

        return runners.TcRunner.find_binary(*args, **kwargs)

    @finder
    def find_stat_iterate(self, *args, **kwargs):
        """Find a suitable stat_iterate script."""

        return runners.CpuStatsRunner.find_binary(*args, **kwargs)

    @finder
    def find_wifistats_iterate(self, *args, **kwargs):
        """Find a suitable wifistats_iterate script."""

        return runners.WifiStatsRunner.find_binary(*args, **kwargs)

    @finder
    def find_netstat_iterate(self, *args, **kwargs):
        """Find a suitable netstat_iterate script."""

        return runners.NetstatRunner.find_binary(*args, **kwargs)

    def require_host_count(self, count):
        if len(self.env['HOSTS']) < count:
            if self.informational:
                self.env['HOSTS'] = ['dummy'] * count
            elif 'DEFAULTS' in self.env and 'HOSTS' in self.env['DEFAULTS'] \
                 and self.env['DEFAULTS']['HOSTS']:
                # If a default HOSTS list is set, populate the HOSTS list with
                # values from this list, repeating as necessary up to count
                def_hosts = cycle(self.env['DEFAULTS']['HOSTS'])
                missing_c = count - len(self.env['HOSTS'])
                self.env['HOSTS'].extend(islice(def_hosts, missing_c))
                if not self.env['HOST']:
                    self.env['HOST'] = self.env['HOSTS'][0]
            else:
                raise RuntimeError("Need %d hosts, only %d specified" %
                                   (count, len(self.env['HOSTS'])))
