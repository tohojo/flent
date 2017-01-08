# -*- coding: utf-8 -*-
#
# runners.py
#
# Author:   Toke Høiland-Jørgensen (toke@toke.dk)
# Date:     16 October 2012
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

import hashlib
import hmac
import math
import os
import re
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time

from datetime import datetime
from calendar import timegm
from threading import Event

from flent import util
from flent.build_info import DATA_DIR
from flent.util import classname, ENCODING, Glob
from flent.loggers import get_logger

mswindows = (sys.platform == "win32")

try:
    from defusedxml.xmlrpc import monkey_patch
    monkey_patch()
    del monkey_patch
    XML_DEFUSED = True
except ImportError:
    XML_DEFUSED = False

try:
    # python 2
    import xmlrpclib as xmlrpc
except ImportError:
    import xmlrpc.client as xmlrpc

logger = get_logger(__name__)

if mswindows:
    def _handle_exitstatus(sts):
        raise NotImplementedError(
            "Subprocess management currently doesn't work on Windows")
else:
    # helper function from subprocess module
    def _handle_exitstatus(sts, _WIFSIGNALED=os.WIFSIGNALED,
                           _WTERMSIG=os.WTERMSIG, _WIFEXITED=os.WIFEXITED,
                           _WEXITSTATUS=os.WEXITSTATUS):
        # This method is called (indirectly) by __del__, so it cannot
        # refer to anything outside of its local scope."""
        if _WIFSIGNALED(sts):
            return -_WTERMSIG(sts)
        elif _WIFEXITED(sts):
            return _WEXITSTATUS(sts)
        else:
            # Should never happen
            raise RuntimeError("Unknown child exit status!")


def get(name):
    cname = classname(name, "Runner")
    if cname not in globals():
        raise RuntimeError("Runner not found: '%s'" % name)
    return globals()[cname]


class RunnerBase(object):

    transformed_metadata = []

    def __init__(self, name, settings, idx=None, start_event=None,
                 finish_event=None, kill_event=None, **kwargs):
        self.name = name
        self.settings = settings
        self.idx = idx
        self.test_parameters = {}
        self.raw_values = []
        self.command = None
        self.returncode = 0
        self.out = self.err = ''

        if not hasattr(self, 'result'):
            self.result = None

        self.start_event = start_event
        self.kill_event = kill_event if kill_event is not None else Event()
        self.finish_event = finish_event

        self._pickled = False

        self.metadata = {'RUNNER': self.__class__.__name__, 'IDX': idx}

    def __getstate__(self):
        state = {}

        for k, v in self.__dict__.items():
            if k not in ('start_event', 'kill_event', 'finish_event',
                         'kill_lock', '_started', '_stderr', '_stdout',
                         'stdout', 'stderr', '_tstate_lock'):
                state[k] = v

        state['_pickled'] = True

        return state

    # Emulate threading interface to fit into aggregator usage.
    def start(self):
        if self._pickled:
            raise RuntimeError("Attempt to run a pickled runner")

    def join(self):
        pass

    def isAlive(self):
        return False

    def kill(self, graceful=False):
        pass


class TimerRunner(threading.Thread, RunnerBase):

    def __init__(self, timeout, **kwargs):
        threading.Thread.__init__(self)
        RunnerBase.__init__(self, **kwargs)
        self.timeout = timeout
        self.command = 'Timeout after %f seconds' % self.timeout

    def start(self):
        if self._pickled:
            raise RuntimeError("Attempt to run a pickled runner")

        threading.Thread.start(self)

    def run(self):
        if self.start_event is not None:
            self.start_event.wait()

        self.kill_event.wait(self.timeout)
        self.finish_event.set()

    def kill(self, graceful=False):
        self.kill_event.set()


class FileMonitorRunner(threading.Thread, RunnerBase):

    def __init__(self, filename, length, interval, delay, **kwargs):
        threading.Thread.__init__(self)
        RunnerBase.__init__(self, **kwargs)
        self.filename = filename
        self.length = length
        self.interval = interval
        self.delay = delay
        self.metadata['FILENAME'] = self.filename
        self.command = 'File monitor for %s' % self.filename

    def start(self):
        if self._pickled:
            raise RuntimeError("Attempt to run a pickled runner")

        threading.Thread.start(self)

    def run(self):
        if self.start_event is not None:
            self.start_event.wait()

        if self.delay:
            self.kill_event.wait(self.delay)

        if not self.kill_event.is_set():
            start_time = current_time = time.time()

            result = []

            # Add an extra interval to comparison to avoid getting one too few
            # samples due to small time differences.
            while (current_time < start_time + self.length + self.interval and
                   not self.kill_event.is_set()):
                try:
                    with open(self.filename, 'r') as fp:
                        val = fp.read()
                    self.out += val
                    try:
                        val = float(val)
                        result.append((current_time, val))
                    except ValueError:
                        val = val.strip()
                    self.raw_values.append({'t': current_time, 'val': val})
                except IOError as e:
                    self.err += "Error opening file {}: {}\n".format(
                        self.filename, e)
                finally:
                    self.kill_event.wait(self.interval)
                    current_time = time.time()
            if result:
                self.result = result
            else:
                self.returncode = 1

        self.finish_event.set()

    def kill(self, graceful=False):
        self.kill_event.set()


class ProcessRunner(threading.Thread, RunnerBase):
    """Default process runner for any process."""
    silent = False
    supports_remote = True

    def __init__(self, command, delay, remote_host, **kwargs):
        threading.Thread.__init__(self)
        RunnerBase.__init__(self, **kwargs)

        # Rudimentary remote host capability. Note that this is modifying the
        # final command, so all the find_* stuff must match on the local and
        # remote hosts. I.e. the same binaries must exist in the same places.
        if remote_host:
            if not self.supports_remote:
                raise RuntimeError(
                    "%s (idx %d) does not support running on remote hosts." % (
                        self.__class__.__name__, self.idx))
            command = "ssh %s '%s'" % (remote_host, command)
            self.metadata['REMOTE_HOST'] = remote_host

        self.command = command
        self.args = shlex.split(self.command)
        self.delay = delay
        self.killed = False
        self.pid = None
        self.returncode = None
        self.kill_lock = threading.Lock()
        self.metadata['COMMAND'] = command
        self.test_parameters = {}
        self.raw_values = []
        self.stdout = None
        self.stderr = None

        if 'units' in kwargs:
            self.metadata['UNITS'] = kwargs['units']

    def handle_usr2(self, signal, frame):
        if self.start_event is not None:
            self.start_event.set()

    def fork(self):
        # Use named temporary files to avoid errors on double-delete when
        # running on Windows/cygwin.
        try:
            self.stdout = tempfile.NamedTemporaryFile(
                prefix="flent-", delete=False)
            self.stderr = tempfile.NamedTemporaryFile(
                prefix="flent-", delete=False)
        except OSError as e:
            if e.errno == 24:
                raise RuntimeError(
                    "Unable to create temporary files because too many "
                    "files are open. Try increasing ulimit.")
            else:
                raise RuntimeError("Unable to create temporary files: %s" % e)

        pid = os.fork()

        if pid == 0:
            os.dup2(self.stdout.fileno(), 1)
            os.dup2(self.stderr.fileno(), 2)
            self.stdout.close()
            self.stderr.close()

            try:
                if self.start_event is not None:
                    signal.signal(signal.SIGUSR2, self.handle_usr2)
                    self.start_event.wait()
                    signal.signal(signal.SIGUSR2, signal.SIG_DFL)

                time.sleep(self.delay)
            except:
                os._exit(0)

            prog = self.args[0]
            os.execvp(prog, self.args)
        else:
            self.pid = pid

    def kill(self, graceful=False):
        if graceful:
            # Graceful shutdown is done on a best-effort basis, and may results
            # in some errors from the test tools. We don't print these, since
            # they are expected.
            self.silent = True
        else:
            with self.kill_lock:
                self.killed = True
            self.cleanup_tmpfiles()
        if self.pid is not None:
            try:
                os.kill(self.pid, signal.SIGINT if graceful else signal.SIGTERM)
            except OSError:
                pass

    def cleanup_tmpfiles(self):
        for f in self.stdout, self.stderr:
            if f is not None:
                try:
                    f.close()
                except OSError:
                    pass
                try:
                    os.unlink(f.name)
                except OSError:
                    pass

    def is_killed(self):
        with self.kill_lock:
            return self.killed

    def start(self):
        if self._pickled:
            raise RuntimeError("Attempt to run a pickled runner")

        if mswindows:
            raise RuntimeError(
                "Process management currently doesn't work on Windows, "
                "so running tests is not possible.")
        self.fork()
        threading.Thread.start(self)

    def run(self):
        """Runs the configured job. If a delay is set, wait for that many
        seconds, then open the subprocess, wait for it to finish, and collect
        the last word of the output (whitespace-separated)."""

        if self.start_event is not None:
            self.start_event.wait()
            try:
                os.kill(self.pid, signal.SIGUSR2)
            except OSError:
                pass

        if self.kill_event is None:
            pid, sts = os.waitpid(self.pid, 0)
        else:
            pid, sts = os.waitpid(self.pid, os.WNOHANG)
            while (pid, sts) == (0, 0):
                self.kill_event.wait(1)
                if self.kill_event.is_set():
                    try:
                        os.kill(self.pid, signal.SIGTERM)
                    except OSError:
                        pass
                pid, sts = os.waitpid(self.pid, os.WNOHANG)

        self.finish_event.set()
        self.returncode = _handle_exitstatus(sts)

        # Even with locking, kill detection is not reliable; sleeping seems to
        # help. *sigh* -- threading.
        time.sleep(0.2)

        if self.is_killed():
            return

        self.stdout.seek(0)
        self.out += self.stdout.read().decode(ENCODING)
        try:
            # Close and remove the temporary file. This might fail, but we're
            # going to assume that is okay.
            filename = self.stdout.name
            self.stdout.close()
            os.unlink(filename)
        except OSError:
            pass

        self.stderr.seek(0)
        self.err += self.stderr.read().decode(ENCODING)
        try:
            filename = self.stderr.name
            self.stderr.close()
            os.unlink(filename)
        except OSError:
            pass

        if self.returncode and not self.silent:
            logger.warning("Program exited non-zero.",
                           extra={'runner': self})

        self.result = self.parse(self.out)
        if not self.result and not self.silent:
            logger.warning("Command produced no valid data.",
                           extra={'runner': self})

    def parse(self, output):
        """Default parser returns the last (whitespace-separated) word of
        output as a float."""

        return float(output.split()[-1].strip())

DefaultRunner = ProcessRunner


class SilentProcessRunner(ProcessRunner):
    silent = True

    def parse(self, output):
        return None


class DitgRunner(ProcessRunner):
    """Runner for D-ITG with a control server."""
    supports_remote = False

    def __init__(self, duration, interval, **kwargs):
        ProcessRunner.__init__(self, **kwargs)
        if 'control_host' in kwargs:
            control_host = kwargs['control_host']
        else:
            control_host = self.settings.CONTROL_HOST or self.settings.HOST
        self.proxy = xmlrpc.ServerProxy("http://%s:%s"
                                        % (control_host,
                                           self.settings.DITG_CONTROL_PORT),
                                        allow_none=True)
        self.ditg_secret = self.settings.DITG_CONTROL_SECRET
        self.duration = duration
        self.interval = interval

    def start(self):
        try:
            interval = int(self.interval * 1000)
            hm = hmac.new(self.ditg_secret.encode(
                'UTF-8'), digestmod=hashlib.sha256)
            hm.update(str(self.duration).encode('UTF-8'))
            hm.update(str(interval).encode('UTF-8'))
            params = self.proxy.request_new_test(
                self.duration, interval, hm.hexdigest(), True)
            if params['status'] != 'OK':
                if 'message' in params:
                    raise RuntimeError(
                        "Unable to request D-ITG test. "
                        "Control server reported error: %s" % params['message'])
                else:
                    raise RuntimeError(
                        "Unable to request D-ITG test. "
                        "Control server reported an unspecified error.")
            self.test_id = params['test_id']
            self.out += "Test ID: %s\n" % self.test_id
        except (xmlrpc.Fault, socket.error) as e:
            raise RuntimeError(
                "Error while requesting D-ITG test: '%s'. "
                "Is the control server listening (see man page)?" % e)
        self.command = self.command.format(
            signal_port=params['port'], dest_port=params['port'] + 1)
        self.args = shlex.split(self.command)
        ProcessRunner.start(self)

    def parse(self, output):
        data = ""
        utc_offset = 0
        results = {}
        try:
            # The control server has a grace period after the test ends, so we
            # don't know exactly when the test results are going to be ready. We
            # assume that it will be within ten seconds.
            for i in range(10):
                res = self.proxy.get_test_results(self.test_id)
                if res['status'] == 'OK':
                    data = res['data']
                    self.out += data
                    utc_offset = res['utc_offset']
                    break
                time.sleep(1)
            if res['status'] != 'OK':
                if 'message' in res:
                    self.err += "Error while getting results. " \
                                "Control server reported error: %s.\n" \
                                % res['message']
                else:
                    self.err += "Error while getting results. " \
                                "Control server reported unknown error.\n"
        except xmlrpc.Fault as e:
            self.err += "Error while getting results: %s.\n" % e

        # D-ITG *should* output about 50 bytes of data per data point. However,
        # sometimes it runs amok and outputs megabytes of erroneous data. So, if
        # the length of the data is more than ten times the expected value,
        # abort rather than try to process the data.
        if len(data) > (self.duration / self.interval) * 500:
            self.err += "D-ITG output too much data (%d bytes).\n" % len(data)
            return results

        if 'raw' in res:
            self.parse_raw(res['raw'])

        for line in data.splitlines():
            if not line.strip():
                continue
            parts = [float(i) for i in line.split()]
            timestamp = parts.pop(0) + utc_offset
            for i, n in enumerate(('bitrate', 'delay', 'jitter', 'loss')):
                if n not in results:
                    results[n] = []
                results[n].append([timestamp, parts[i]])

        return results

    def parse_raw(self, data):
        raw_values = []

        for line in data.splitlines():
            parts = re.split(r">?\s*", line)
            vals = dict(zip(parts[::2], parts[1::2]))
            times = {}
            for v in ('txTime', 'rxTime'):
                t, microsec = vals[v].split(".")
                h, m, s = t.split(":")
                # FIXME: This is definitely going to break if a test is run
                # around midnight
                dt = datetime.utcnow().replace(hour=int(h),
                                               minute=int(m),
                                               second=int(s),
                                               microsecond=int(microsec))
                times[v] = float(timegm(dt.timetuple())) + dt.microsecond / 10**6

            raw_values.append({
                't': times['rxTime'],
                'val': 1000.0 * (times['rxTime'] - times['txTime']),
                'seq': int(vals['Seq']),
                'size': int(vals['Size'])
            })

        self.raw_values = raw_values


class NetperfDemoRunner(ProcessRunner):
    """Runner for netperf demo mode."""
    transformed_metadata = ('MEAN_VALUE',)

    def parse(self, output):
        """Parses the interim result lines and returns a list of (time,value)
        pairs."""

        result = []
        raw_values = []
        lines = output.strip().splitlines()
        avg_dur = None
        alpha = 0.5
        for line in lines:
            if line.startswith("Interim"):
                parts = line.split()

                # Calculate an EWMA of the netperf sampling duration and exclude
                # data points from a sampling period that is more than an order
                # of magnitude higher or lower than this average; these are
                # probably the result of netperf spitting out a measurement at
                # the end of a run after having lost the measurement flow during
                # the run, or a very short interval giving a very high bandwidth
                # measurement
                dur = float(parts[5])
                time = float(parts[9])
                value = float(parts[2])
                if avg_dur is None:
                    avg_dur = dur

                raw_values.append({'dur': dur, 't': time, 'val': value})

                if dur < avg_dur * 10.0 and dur > avg_dur / 10.0:
                    result.append([time, value])
                    avg_dur = alpha * avg_dur + (1.0 - alpha) * dur
        self.raw_values = raw_values
        try:
            self.metadata['MEAN_VALUE'] = float(lines[-1])
        except (ValueError, IndexError):
            pass

        return result


class RegexpRunner(ProcessRunner):

    """Runner that matches each line to one or more regular expressions,
    returning the values from the first matched.

    The regular expressions must define symbolic groups 'time' and 'value'."""

    regexes = []
    metadata_regexes = []

    # Parse is split into a stateless class method in _parse to be able to call
    # it from find_binary.
    def parse(self, output):
        result, raw_values, metadata = self._parse(output)
        self.raw_values = raw_values
        self.metadata.update(metadata)
        return result

    @classmethod
    def _parse(cls, output):
        result = []
        raw_values = []
        metadata = {}
        lines = output.split("\n")
        for line in lines:
            for regexp in cls.regexes:
                match = regexp.match(line)
                if match:
                    result.append([float(match.group('t')),
                                   float(match.group('val'))])
                    rw = match.groupdict()
                    for k, v in rw.items():
                        try:
                            rw[k] = float(v)
                        except ValueError:
                            pass
                    raw_values.append(rw)
                    break  # only match one regexp per line
            for regexp in cls.metadata_regexes:
                match = regexp.match(line)
                if match:
                    for k, v in match.groupdict().items():
                        try:
                            metadata[k] = float(v)
                        except ValueError:
                            metadata[k] = v
        return result, raw_values, metadata


class PingRunner(RegexpRunner):
    """Runner for ping/ping6 in timestamped (-D) mode."""

    # For some reason some versions of ping output icmp_req and others icmp_seq
    # for sequence numbers.
    regexes = [re.compile(r'^\[(?P<t>[0-9]+\.[0-9]+)\]'
                          r'(?:.*icmp_.eq=(?P<seq>[0-9]+))?'
                          r'.*time=(?P<val>[0-9]+(?:\.[0-9]+)?) ms$'),
               re.compile(r'^\[(?P<t>[0-9]+\.[0-9]+)\].*:'
                          r'(?: \[(?P<seq>[0-9]+)\])?.*, '
                          r'(?P<val>[0-9]+(?:\.[0-9]+)?) ms \(.*\)$')]
    metadata_regexes = [re.compile(r'^.*min/avg/max(?:/mdev)? = '
                                   r'(?P<MIN_VALUE>[0-9]+(?:\.[0-9]+)?)/'
                                   r'(?P<MEAN_VALUE>[0-9]+(?:\.[0-9]+)?)/'
                                   r'(?P<MAX_VALUE>[0-9]+(?:\.[0-9]+)?).*$')]
    transformed_metadata = ('MEAN_VALUE', 'MIN_VALUE', 'MAX_VALUE')

    @classmethod
    def find_binary(cls, ip_version, interval, length, host,
                    marking=None, local_bind=None):
        """Find a suitable ping executable, looking first for a compatible
        `fping`, then falling back to the `ping` binary. Binaries are checked
        for the required capabilities."""

        if ip_version == 6:
            suffix = "6"
        else:
            suffix = ""

        fping = util.which('fping' + suffix)
        ping = util.which('ping' + suffix)

        if fping is not None:
            proc = subprocess.Popen([fping, '-h'],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            out, err = proc.communicate()
            # check for presence of timestamp option
            if "print timestamp before each output line" in str(out):
                return "{binary} -D -p {interval:.0f} -c {count:.0f} " \
                    "{marking} {local_bind} {host}".format(
                        binary=fping,
                        interval=interval * 1000,  # fping expects interval in ms
                        # since there's no timeout parameter for fping,
                        # calculate a total number of pings to send
                        count=length // interval + 1,
                        marking="-O {0}".format(marking) if marking else "",
                        local_bind=("-I {0}".format(local_bind)
                                    if local_bind else ""),
                        host=host)
            elif "must run as root?" in str(err):
                logger.warning(
                    "Found fping but it seems to be missing "
                    "permissions (no SUID?). Not using.")

        if ping is not None:
            # Ping can't handle hostnames for the -I parameter, so do a lookup
            # first.
            if local_bind:
                local_bind = util.lookup_host(local_bind, ip_version)[4][0]

            # Try parsing the output of 'ping' and complain if no data is
            # returned from the parser. This should pick up e.g. the ping on OSX
            # not having a -D option and allow us to supply a better error
            # message.
            proc = subprocess.Popen([ping, '-D', '-n', '-c', '1', 'localhost'],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            out, err = proc.communicate()
            if hasattr(out, 'decode'):
                out = out.decode(ENCODING)
            if not cls._parse(out)[0]:
                raise RuntimeError(
                    "Cannot parse output of the system ping binary ({ping}). "
                    "Please install fping v3.5+.".format(ping=ping))

            return "{binary} -n -D -i {interval:.2f} -w {length:d} {marking} " \
                "{local_bind} {host}".format(
                    binary=ping,
                    interval=max(0.2, interval),
                    length=length,
                    marking="-Q {0}".format(marking) if marking else "",
                    local_bind="-I {0}".format(local_bind) if local_bind else "",
                    host=host)

        raise RuntimeError("No suitable ping tool found.")


class HttpGetterRunner(RegexpRunner):

    regexes = [re.compile(
        r'^\[(?P<t>[0-9]+\.[0-9]+)\].*in (?P<val>[0-9]+(?:\.[0-9]+)?) seconds.$')]
    metadata_regexes = [re.compile(r'^.*min/avg/max(?:/mdev)? = '
                                   r'(?P<MIN_VALUE>[0-9]+(?:\.[0-9]+)?)/'
                                   r'(?P<MEAN_VALUE>[0-9]+(?:\.[0-9]+)?)/'
                                   r'(?P<MAX_VALUE>[0-9]+(?:\.[0-9]+)?).*$')]
    transformed_metadata = ('MEAN_VALUE', 'MIN_VALUE', 'MAX_VALUE')


class IperfCsvRunner(ProcessRunner):
    """Runner for iperf csv output (-y C), possibly with unix timestamp patch."""

    transformed_metadata = ('MEAN_VALUE',)

    def __init__(self, **kwargs):
        if 'udp' in kwargs:
            self.udp = kwargs['udp']
            del kwargs['udp']
        else:
            self.udp = False
        ProcessRunner.__init__(self, **kwargs)

    def parse(self, output):
        result = []
        raw_values = []
        lines = output.strip().split("\n")
        dest = None
        for line in lines[:-1]:  # The last line is an average over the whole test
            parts = line.split(",")
            if len(parts) < 9:
                continue

            timestamp = parts[0]
            bandwidth = parts[8]

            if dest is None:
                dest = parts[3]

            # Newer versions of iperf2 emits sub-second timestamps if given the
            # --enhancedreports argument. Since we detect this in find_iperf, we
            # only support this format.

            try:
                sec, mil = timestamp.split(".")
                dt = datetime.strptime(sec, "%Y%m%d%H%M%S")
                timestamp = time.mktime(dt.timetuple()) + float(mil) / 1000
                val = float(bandwidth)
                result.append([timestamp, val])
                raw_values.append({'t': timestamp, 'val': val})
            except ValueError:
                pass

        self.raw_values = raw_values
        try:
            parts = lines[-1].split(",")
            # src and dest should be reversed if this was a reply from the
            # server. Track this for UDP where it may be missing.
            if parts[1] == dest or not self.udp:
                self.metadata['MEAN_VALUE'] = float(parts[8])
            else:
                self.metadata['MEAN_VALUE'] = None
        except (ValueError, IndexError):
            pass
        return result

    @classmethod
    def find_binary(cls, host, interval, length, ip_version, local_bind=None,
                    no_delay=False, udp=False, bw=None):
        iperf = util.which('iperf')

        if iperf is not None:
            proc = subprocess.Popen([iperf, '-h'],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            out, err = proc.communicate()

            if "--enhancedreports" in str(err):
                if udp:
                    udp_args = "--udp --bandwidth {}".format(bw if bw else "100M")
                else:
                    udp_args = ""
                return "{binary} --enhancedreports --reportstyle C --format m " \
                    "--client {host} --time {length} --interval {interval} " \
                    "{local_bind} {no_delay} {udp} {ip6}".format(
                        host=host,
                        binary=iperf,
                        length=length,
                        interval=interval,
                        # --help output is wrong
                        ip6="--ipv6_domain" if ip_version == 6 else "",
                        local_bind="--bind {0}".format(
                            local_bind) if local_bind else "",
                        no_delay="--nodelay" if no_delay else "",
                        udp=udp_args)
            else:
                logger.warning(
                    "Found iperf binary, but it does not have "
                    "an --enhancedreport option. Not using.")

        raise RuntimeError("No suitable Iperf binary found.")


class TcRunner(ProcessRunner):
    """Runner for iterated `tc -s qdisc`. Expects iterations to be separated by
    '\n---\n and a timestamp to be present in the form 'Time: xxxxxx.xxx' (e.g.
    the output of `date '+Time: %s.%N'`)."""

    time_re = re.compile(r"^Time: (?P<timestamp>\d+\.\d+)", re.MULTILINE)
    split_re = re.compile(r"^qdisc ", re.MULTILINE)
    qdisc_res = [
        re.compile(r"Sent (?P<sent_bytes>\d+) bytes (?P<sent_pkts>\d+) pkt "
                   r"\(dropped (?P<dropped>\d+), "
                   r"overlimits (?P<overlimits>\d+) "
                   r"requeues (?P<requeues>\d+)\)"),
        re.compile(r"backlog (?P<backlog_bytes>\d+)b "
                   r"(?P<backlog_pkts>\d+)p "
                   r"requeues (?P<backlog_requeues>\d+)"),

        # codel
        re.compile(r"count (?P<count>\d+) "
                   r"lastcount (?P<lastcount>\d+) "
                   r"ldelay (?P<delay>[0-9\.]+[mu]?s) "
                   r"(?P<dropping>dropping)? ?"
                   r"drop_next (?P<drop_next>-?[0-9\.]+[mu]?s)"),
        re.compile(r"maxpacket (?P<maxpacket>\d+) "
                   r"ecn_mark (?P<ecn_mark>\d+) "
                   r"drop_overlimit (?P<drop_overlimit>\d+)"),
        # fq_codel
        re.compile(r"maxpacket (?P<maxpacket>\d+) "
                   r"drop_overlimit (?P<drop_overlimit>\d+) "
                   r"new_flow_count (?P<new_flow_count>\d+) "
                   r"ecn_mark (?P<ecn_mark>\d+)"),
        re.compile(r"new_flows_len (?P<new_flows_len>\d+) "
                   r"old_flows_len (?P<old_flows_len>\d+)"),

        # pie
        re.compile(r"prob (?P<prob>[0-9\.]+) "
                   r"delay (?P<delay>[0-9\.]+[mu]?s) "
                   r"avg_dq_rate (?P<avg_dq_rate>\d+)"),
        re.compile(r"pkts_in (?P<pkts_in>\d+) "
                   r"overlimit (?P<overlimit_pie>\d+) "
                   r"dropped (?P<dropped_pie>\d+) "
                   r"maxq (?P<maxq>\d+) "
                   r"ecn_mark (?P<ecn_mark>\d+)"),
    ]

    cake_tin_re = r"(Tin \d|Bulk|Best Effort|Video|Voice)"
    cake_alltins_re = re.compile(r"(\s*" + cake_tin_re + r")+")
    cake_1tin_re = re.compile(cake_tin_re)
    cake_keys = ["av_delay", "sp_delay", "pkts", "bytes",
                 "drops", "marks", "sp_flows", "bk_flows", "max_len"]

    # Normalise time values (seconds, ms, us) to milliseconds and bit values
    # (bit, Kbit, Mbit) to bits
    def parse_val(self, v):
        if v is None:
            return None
        elif v.endswith("us"):
            return float(v[:-2]) / 1000
        elif v.endswith("ms"):
            return float(v[:-2])
        elif v.endswith("s"):
            return float(v[:-1]) * 1000
        elif v.endswith("Kbit"):
            return float(v[:-4]) * 1000
        elif v.endswith("Mbit"):
            return float(v[:-4]) * 10**6
        elif v.endswith("bit"):
            return float(v[:-3])
        else:
            try:
                return float(v)
            except ValueError:
                return v

    def parse(self, output):
        results = {}
        parts = output.split("\n---\n")
        for part in parts:
            # Split out individual qdisc entries (in case there are more than
            # one). If so, discard the root qdisc and sum the rest.
            qdiscs = self.split_re.split(part)
            if len(qdiscs) > 2:
                part = "qdisc ".join([i for i in qdiscs
                                      if 'root' not in i])

            matches = {}
            timestamp = self.time_re.search(part)
            if timestamp is None:
                continue
            timestamp = float(timestamp.group('timestamp'))

            for r in self.qdisc_res:
                m = r.search(part)
                # Keep searching from the end of the last match until no more
                # matches are found; this should find all qdisc outputs in case
                # there are several qdiscs installed on the interface. The
                # values for the qdiscs are summed for the result (discarding
                # what should be the root qdisc as per above).
                while m is not None:
                    for k, v in list(m.groupdict().items()):
                        v = self.parse_val(v)
                        if k not in matches or not isinstance(v, float):
                            matches[k] = v
                        else:
                            matches[k] += v
                    m = r.search(part, m.end(0))

            m = self.cake_alltins_re.search(part)
            if m:
                tins = self.cake_1tin_re.findall(m.group(0))
                start = m.end()
                for key in self.cake_keys:
                    m = re.search(
                        "^  %s(:?\s*([0-9\.kmbitus]+)){%d}\s*$" % (key,
                                                                   len(tins)),
                        part[start:],
                        re.IGNORECASE | re.MULTILINE)
                    if m:
                        k = "cake_%s" % key
                        matches[k] = dict(
                            zip(tins, map(self.parse_val,
                                          m.group(0).split()[1:])))

            # The cake stats, being multi-dimensional, is not actually plottable
            # yet. For now, add in an 'ecn_marks' key that is the sum of all
            # cake tins, for comparability with other qdiscs
            if "cake_marks" in matches and "ecn_mark" not in matches:
                matches['ecn_mark'] = sum(matches['cake_marks'].values())

            for k, v in matches.items():
                if not isinstance(v, float):
                    continue
                if k not in results:
                    results[k] = [[timestamp, v]]
                else:
                    results[k].append([timestamp, v])
            matches['t'] = timestamp
            self.raw_values.append(matches)
        return results

    @classmethod
    def find_binary(cls, interface, interval, length, host='localhost'):
        script = os.path.join(DATA_DIR, 'scripts', 'tc_iterate.sh')
        if not os.path.exists(script):
            raise RuntimeError("Cannot find tc_iterate.sh.")

        bash = util.which('bash')
        if not bash:
            raise RuntimeError("TC stats requires a Bash shell.")

        if interface is None:
            logger.warning(
                "Warning: No interface given for tc runner. "
                "Defaulting to 'eth0'.")
            interface = 'eth0'

        return "{bash} {script} -i {interface} -I {interval:.2f} " \
            "-c {count:.0f} -H {host}".format(
                bash=bash,
                script=script,
                interface=interface,
                interval=interval,
                count=length // interval + 1,
                host=host)


class CpuStatsRunner(ProcessRunner):
    """Runner for getting CPU usage stats from /proc/stat. Expects iterations to be
    separated by '\n---\n and a timestamp to be present in the form 'Time:
    xxxxxx.xxx' (e.g. the output of `date '+Time: %s.%N'`).

    """
    time_re = re.compile(r"^Time: (?P<timestamp>\d+\.\d+)", re.MULTILINE)
    value_re = re.compile(r"^\d+ \d+ (?P<load>\d+\.\d+)$", re.MULTILINE)

    def parse(self, output):
        results = {}
        parts = output.split("\n---\n")
        for part in parts:
            # Split out individual qdisc entries (in case there are more than
            # one). If so, discard the root qdisc and sum the rest.
            timestamp = self.time_re.search(part)
            if timestamp is None:
                continue
            timestamp = float(timestamp.group('timestamp'))
            value = self.value_re.search(part)

            if value is None:
                continue
            matches = {}

            for k, v in list(value.groupdict().items()):
                v = float(v)
                if k not in matches:
                    matches[k] = v
                else:
                    matches[k] += v

            for k, v in matches.items():
                if not isinstance(v, float):
                    continue
                if k not in results:
                    results[k] = [[timestamp, v]]
                else:
                    results[k].append([timestamp, v])
            matches['t'] = timestamp
            self.raw_values.append(matches)
        return results

    @classmethod
    def find_binary(cls, interval, length, host='localhost'):
        script = os.path.join(DATA_DIR, 'scripts', 'stat_iterate.sh')
        if not os.path.exists(script):
            raise RuntimeError("Cannot find stat_iterate.sh.")

        bash = util.which('bash')
        if not bash:
            raise RuntimeError("CPU stats requires a Bash shell.")

        return "{bash} {script} -I {interval:.2f} " \
            "-c {count:.0f} -H {host}".format(
                bash=bash,
                script=script,
                interval=interval,
                count=length // interval + 1,
                host=host)


class WifiStatsRunner(ProcessRunner):
    """Runner for getting WiFi debug stats from /sys/kernel/debug. Expects
    iterations to be separated by '\n---\n and a timestamp to be present in the
    form 'Time: xxxxxx.xxx' (e.g. the output of `date '+Time: %s.%N'`).

    """
    time_re = re.compile(r"^Time: (?P<timestamp>\d+\.\d+)", re.MULTILINE)
    station_re = re.compile(
        r"^Station: (?P<mac>(?:[0-9a-f]{2}:){5}[0-9a-f]{2})\n", re.MULTILINE)
    airtime_re = re.compile(
        r"^Airtime:\nRX: (?P<rx>\d+) us\nTX: (?P<tx>\d+) us", re.MULTILINE)

    def __init__(self, **kwargs):
        if 'stations' in kwargs:
            if kwargs['stations'] in (["all"], ["ALL"]):
                self.stations = []
                # disabled as it doesn't work properly yet
                self.all_stations = False
            else:
                self.stations = kwargs['stations']
                self.all_stations = False
            del kwargs['stations']
        else:
            self.stations = []
        ProcessRunner.__init__(self, **kwargs)

    def parse(self, output):
        results = {}
        parts = output.split("\n---\n")
        for part in parts:
            matches = {}
            timestamp = self.time_re.search(part)
            if timestamp is None:
                continue
            timestamp = float(timestamp.group('timestamp'))

            # Split by station regex: First entry is everything before the
            # per-station stats, the rest is a pair of (<station mac>, contents).
            station_parts = self.station_re.split(part)[1:]
            stations = {}

            for s, v in zip(station_parts[::2], station_parts[1::2]):
                if s not in self.stations:
                    if self.all_stations:
                        self.stations.append(s)
                    else:
                        continue
                sv = {}
                airtime = self.airtime_re.search(v)
                if airtime is not None:
                    sv['airtime_rx'] = float(airtime.group('rx'))
                    sv['airtime_tx'] = float(airtime.group('tx'))

                rcs = v.find("RC stats:\n")

                # For now, just parse the average aggregation size, which is the
                # last field of each csv line output.
                if rcs > -1:
                    nl = v.find("\n", rcs + 10)
                    if nl > -1:
                        line = v[rcs + 10:nl]
                        sv['avg_aggr_size'] = float(line.split(",")[-1])
                stations[s] = sv

                # Flatten for results array
                for k, v in sv.items():
                    if not isinstance(v, float):
                        continue
                    rk = "::".join([k, s])
                    if rk not in results:
                        results[rk] = [[timestamp, v]]
                    else:
                        results[rk].append([timestamp, v])

            for k, v in matches.items():
                if not isinstance(v, float):
                    continue
                if k not in results:
                    results[k] = [[timestamp, v]]
                else:
                    results[k].append([timestamp, v])
            matches['t'] = timestamp
            matches['stations'] = stations
            self.raw_values.append(matches)

        if self.all_stations:
            self.test_parameters['wifi_stats_stations'] = ",".join(self.stations)
        return results

    @classmethod
    def find_binary(cls, interface, interval, length, host='localhost'):
        script = os.path.join(DATA_DIR, 'scripts', 'wifistats_iterate.sh')
        if not os.path.exists(script):
            raise RuntimeError("Cannot find wifistats_iterate.sh.")

        bash = util.which('bash')
        if not bash:
            raise RuntimeError("WiFi stats requires a Bash shell.")

        return "{bash} {script} -i {interface} -I {interval:.2f} " \
            "-c {count:.0f} -H {host}".format(
                bash=bash,
                script=script,
                interface=interface,
                interval=interval,
                count=length // interval + 1,
                host=host)


class NetstatRunner(ProcessRunner):
    """Runner for getting TCP stats from /proc/net/netstat. Expects
    iterations to be separated by '\n---\n and a timestamp to be present in the
    form 'Time: xxxxxx.xxx' (e.g. the output of `date '+Time: %s.%N'`).

    """
    time_re = re.compile(r"^Time: (?P<timestamp>\d+\.\d+)", re.MULTILINE)
    tcpext_header_re = re.compile(
        r"^TcpExt: (?P<header>[A-Z][0-9a-zA-Z ]+)\n", re.MULTILINE)
    tcpext_data_re = re.compile(r"^TcpExt: (?P<data>[0-9 ]+)\n", re.MULTILINE)

    def parse(self, output):
        results = {}
        parts = output.split("\n---\n")
        for part in parts:
            matches = {}
            timestamp = self.time_re.search(part)
            if timestamp is None:
                continue
            timestamp = float(timestamp.group('timestamp'))
            hdr = self.tcpext_header_re.search(part)
            data = self.tcpext_data_re.search(part)

            if hdr is None or data is None:
                continue

            h = hdr.group("header").split()
            d = data.group("data").split()

            if len(h) != len(d):
                continue

            matches = dict(zip(h, [float(i) for i in d]))

            for k, v in matches.items():
                if not isinstance(v, float):
                    continue
                if k not in results:
                    results[k] = [[timestamp, v]]
                else:
                    results[k].append([timestamp, v])
            matches['t'] = timestamp
            self.raw_values.append(matches)
        return results

    @classmethod
    def find_binary(cls, interval, length, host='localhost'):
        script = os.path.join(DATA_DIR, 'scripts', 'netstat_iterate.sh')
        if not os.path.exists(script):
            raise RuntimeError("Cannot find netstat_iterate.sh.")

        bash = util.which('bash')
        if not bash:
            raise RuntimeError("Capturing netstat requires a Bash shell.")

        return "{bash} {script} -I {interval:.2f} -c {count:.0f} " \
            "-H {host}".format(
                bash=bash,
                script=script,
                interval=interval,
                count=length // interval + 1,
                host=host)


class NullRunner(RunnerBase):
    pass


class ComputingRunner(RunnerBase):
    command = "Computed"
    supported_meta = ['MEAN_VALUE']
    copied_meta = ['UNITS']

    def __init__(self, apply_to=None, post=False, **kwargs):
        RunnerBase.__init__(self, **kwargs)
        if apply_to is None:
            self.keys = []
        else:
            self.keys = apply_to
        self.metadata['COMPUTED_LATE'] = post

    def result(self, res):
        if not self.keys:
            return res

        new_res = []
        keys = Glob.expand_list(self.keys, res.series_names, [self.name])

        for r in res.zipped(keys):
            values = [v for v in r[1:] if v is not None]
            if not values:
                new_res.append(None)
            else:
                new_res.append(self.compute(values))

        meta = res.meta('SERIES_META') if 'SERIES_META' in res.meta() else {}
        meta[self.name] = self.metadata
        for mk in self.supported_meta:
            vals = []
            for k in keys:
                if k in meta and mk in meta[k] and meta[k][mk] is not None:
                    vals.append(meta[k][mk])
            if vals:
                try:
                    meta[self.name][mk] = self.compute(vals)
                except TypeError:
                    meta[self.name][mk] = None

        for mk in self.copied_meta:
            vals = []
            for k in keys:
                if k in meta and mk in meta[k]:
                    vals.append(meta[k][mk])
            if vals:
                # If all the source values of the copied metadata are the same,
                # just use that value, otherwise include all of them.
                meta[self.name][mk] = vals if len(set(vals)) > 1 else vals[0]

        res.add_result(self.name, new_res)
        return res

    def compute(self, values):
        """Compute the function on the values this runner should be applied to.

        Default implementation returns None."""
        return None


class AverageRunner(ComputingRunner):
    command = "Average (computed)"

    def compute(self, values):
        return math.fsum(values) / len(values)


class SmoothAverageRunner(ComputingRunner):
    command = "Smooth average (computed)"

    def __init__(self, smooth_steps=5, **kwargs):
        ComputingRunner.__init__(self, **kwargs)
        self._smooth_steps = smooth_steps
        self._avg_values = []

    def compute(self, values):
        self._avg_values.append(math.fsum(values) / len(values))
        while len(self._avg_values) > self._smooth_steps:
            self._avg_values.pop(0)
        return math.fsum(self._avg_values) / len(self._avg_values)


class SumRunner(ComputingRunner):
    command = "Sum (computed)"

    def compute(self, values):
        return math.fsum(values)


class DiffMinRunner(ComputingRunner):
    command = "Diff from min (computed)"

    def result(self, res):
        if not self.keys:
            return res

        key = self.keys[0]

        data = [i for i in res[key] if i is not None]
        if not data:
            res.add_result(self.name, [None] * len(res[key]))
        else:
            min_val = min(data)
            res.add_result(
                self.name, [i - min_val if i is not None else None
                            for i in res[key]])
        return res


class FairnessRunner(ComputingRunner):
    command = "Fairness (computed)"

    def compute(self, values):
        if not len(values):
            return None
        valsum = math.fsum([x**2 for x in values])
        if not valsum:
            return None
        return math.fsum(values)**2 / (len(values) * valsum)
