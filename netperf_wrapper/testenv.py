## -*- coding: utf-8 -*-
##
## testenv.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:     17 September 2014
## Copyright (c) 2014, Toke Høiland-Jørgensen
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

import os, subprocess, time
from copy import deepcopy

from netperf_wrapper import util
from netperf_wrapper.util import Glob
from netperf_wrapper.build_info import DATA_DIR
try:
    from collections import OrderedDict
except ImportError:
    from netperf_wrapper.ordereddict import OrderedDict

TEST_PATH = os.path.join(DATA_DIR, 'tests')


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
        self.orig_hosts = self.env['HOSTS']

    def execute(self, filename):
        try:
            exec(compile(open(filename).read(), filename, 'exec'), self.env)

            # Informational loading can override HOSTS to satisfy
            # require_host_count(); this should not be propagated.
            if self.informational:
                self.env['HOSTS'] = self.orig_hosts
            return self.env
        except (IOError, SyntaxError) as e:
            raise RuntimeError("Unable to read test config file '%s': '%s'." % (filename, e))

    def include_test(self, name, env=None):
        self.execute(os.path.join(TEST_PATH, name))

    @finder
    def find_ping(self, ip_version, interval, length, host, marking=None, local_bind=None):
        """Find a suitable ping executable, looking first for a compatible
        `fping`, then falling back to the `ping` binary. Binaries are checked
        for the required capabilities."""

        if ip_version == 6:
            suffix = "6"
        else:
            suffix = ""

        if local_bind is None:
            local_bind = self.env['LOCAL_BIND']


        fping = util.which('fping'+suffix)
        ping = util.which('ping'+suffix)

        if fping is not None:
            proc = subprocess.Popen([fping, '-h'],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            out,err = proc.communicate()
            # check for presence of timestamp option
            if "print timestamp before each output line" in str(out):
                return "{binary} -D -p {interval:.0f} -c {count:.0f} {marking} {local_bind} {host}".format(
                    binary=fping,
                    interval=interval * 1000, # fping expects interval in milliseconds
                    # since there's no timeout parameter for fping, calculate a total number
                    # of pings to send
                    count=length // interval + 1,
                    marking="-O {0}".format(marking) if marking else "",
                    local_bind="-I {0}".format(local_bind) if local_bind else "",
                    host=host)
            elif "must run as root?" in str(err):
                sys.stderr.write("Found fping but it seems to be missing permissions (no SUID?). Not using.\n")

        if ping is not None:
            # Ping can't handle hostnames for the -I parameter, so do a lookup first.
            if local_bind:
                local_bind=util.lookup_host(local_bind, ip_version)[4][0]

            # FIXME: check for support for -D parameter
            return "{binary} -n -D -i {interval:.2f} -w {length:d} {marking} {local_bind} {host}".format(
                binary=ping,
                interval=max(0.2, interval),
                length=length,
                marking="-Q {0}".format(marking) if marking else "",
                local_bind="-I {0}".format(local_bind) if local_bind else "",
                host=host)

        raise RuntimeError("No suitable ping tool found.")

    @finder
    def find_netperf(self, test, length, host, **args):
        """Find a suitable netperf executable, and test for the required capabilities."""

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

        args.setdefault('ip_version', self.env['IP_VERSION'])
        args.setdefault('interval', self.env['STEP_SIZE'])
        args.setdefault('control_host', self.env['CONTROL_HOST'] or host)
        args.setdefault('local_bind', self.env['LOCAL_BIND'] or "")
        args.setdefault('control_local_bind', self.env['CONTROL_LOCAL_BIND'] or args['local_bind'])
        args.setdefault('extra_args', "")
        args.setdefault('extra_test_args', "")
        args.setdefault('format', "")
        args.setdefault('marking', "")
        args.setdefault('socket_timeout', "")

        args.update({'binary': self.netperf['executable'],
                       'host': host,
                       'test': test,
                       'length': length})


        if args['marking']:
            args['marking'] = "-Y {0}".format(args['marking'])

        for c in 'local_bind', 'control_local_bind':
            if args[c]:
                args[c] = "-L {0}".format(args[c])

        if test == "UDP_RR" and self.netperf["-e"]:
            args['socket_timeout'] = "-e {0:d}".format(self.env['SOCKET_TIMEOUT'])
        elif test in ("TCP_STREAM", "TCP_MAERTS", "omni"):
            args['format'] = "-f m"

        return "{binary} -P 0 -v 0 -D -{interval:.2f} -{ip_version} {marking} -H {control_host} -t {test} " \
               "-l {length:d} {format} {control_local_bind} {extra_args} -- {socket_timeout} {local_bind} -H {host} " \
               "{extra_test_args}".format(**args)

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
