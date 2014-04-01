## -*- coding: utf-8 -*-
##
## runners.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:     16 October 2012
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

import threading, time, shlex, subprocess, re, time, sys, math, os, tempfile, signal, hmac, hashlib, calendar

from datetime import datetime

try:
    from defusedxml.xmlrpc import monkey_patch
    monkey_patch()
    del monkey_patch
    XML_DEFUSED=True
except ImportError:
    XML_DEFUSED=False

try:
    # python 2
    import xmlrpclib as xmlrpc
except ImportError:
    import xmlrpc.client as xmlrpc


from .settings import Glob

class ProcessRunner(threading.Thread):
    """Default process runner for any process."""

    def __init__(self, name, settings, command, delay, *args, **kwargs):
        threading.Thread.__init__(self)
        self.name = name
        self.settings = settings
        self.command = command
        self.args = shlex.split(self.command)
        self.delay = delay
        self.result = None
        self.killed = False
        self.pid = None
        self.returncode = None

    def fork(self):
        # Use named temporary files to avoid errors on double-delete when
        # running on Windows/cygwin.
        self.stdout = tempfile.NamedTemporaryFile(delete=False)
        self.stderr = tempfile.NamedTemporaryFile(delete=False)

        pid = os.fork()

        if pid == 0:
            os.dup2(self.stdout.fileno(), 1)
            os.dup2(self.stderr.fileno(), 2)
            self.stdout.close()
            self.stderr.close()

            time.sleep(self.delay)

            prog = self.args[0]
            os.execvp(prog, self.args)
        else:
            self.pid = pid

    def kill(self):
        if self.killed:
            return
        if self.pid is not None:
            try:
                os.kill(self.pid, signal.SIGINT)
            except OSError:
                pass
        self.killed = True

    # helper function from subprocess module
    def _handle_exitstatus(self, sts, _WIFSIGNALED=os.WIFSIGNALED,
                           _WTERMSIG=os.WTERMSIG, _WIFEXITED=os.WIFEXITED,
                           _WEXITSTATUS=os.WEXITSTATUS):
        # This method is called (indirectly) by __del__, so it cannot
        # refer to anything outside of its local scope."""
        if _WIFSIGNALED(sts):
            self.returncode = -_WTERMSIG(sts)
        elif _WIFEXITED(sts):
            self.returncode = _WEXITSTATUS(sts)
        else:
            # Should never happen
            raise RuntimeError("Unknown child exit status!")

    def start(self):
        self.fork()
        threading.Thread.start(self)

    def run(self):
        """Runs the configured job. If a delay is set, wait for that many
        seconds, then open the subprocess, wait for it to finish, and collect
        the last word of the output (whitespace-separated)."""

        pid, sts = os.waitpid(self.pid, 0)
        self._handle_exitstatus(sts)

        self.stdout.seek(0)
        self.out = self.stdout.read().decode()
        try:
            # Close and remove the temporary file. This might fail, but we're going
            # to assume that is okay.
            filename = self.stdout.name
            self.stdout.close()
            os.unlink(filename)
        except OSError:
            pass

        self.stderr.seek(0)
        self.err = self.stderr.read().decode()
        try:
            filename = self.stderr.name
            self.stderr.close()
            os.unlink(filename)
        except OSError:
            pass

        if self.killed:
            return

        if self.returncode:
            sys.stderr.write("Warning: Program exited non-zero.\nCommand: %s\n" % self.command)
            sys.stderr.write("Program output:\n")
            sys.stderr.write("  " + "\n  ".join(self.err.splitlines()) + "\n")
            sys.stderr.write("  " + "\n  ".join(self.out.splitlines()) + "\n")
            self.result = None
        else:
            self.result = self.parse(self.out)
            if not self.result:
                sys.stderr.write("Warning: Command produced no valid data.\n"
                                 "Data series: %s\n"
                                 "Runner: %s\n"
                                 "Command: %s\n"
                                 "Standard error output:\n" % (self.name, self.__class__.__name__, self.command)
                                 )
                sys.stderr.write("  " + "\n  ".join(self.err.splitlines()) + "\n")

    def parse(self, output):
        """Default parser returns the last (whitespace-separated) word of
        output as a float."""

        return float(output.split()[-1].strip())

DefaultRunner = ProcessRunner

class DitgRunner(ProcessRunner):
    """Runner for D-ITG with a control server."""

    def __init__(self, name, settings, duration, interval, **kwargs):
        ProcessRunner.__init__(self, name, settings, **kwargs)
        host = self.settings.DITG_CONTROL_HOST or self.settings.HOST
        self.proxy = xmlrpc.ServerProxy("http://%s:%s" % (host, self.settings.DITG_CONTROL_PORT),
                                        allow_none=True)
        self.ditg_secret = self.settings.DITG_CONTROL_SECRET
        self.duration = duration
        self.interval = interval


    def start(self):
        try:
            interval = int(self.interval*1000)
            hm = hmac.new(self.ditg_secret.encode(), digestmod=hashlib.sha256)
            hm.update(str(self.duration).encode())
            hm.update(str(interval).encode())
            params = self.proxy.request_new_test(self.duration, interval, hm.hexdigest())
            if params['status'] != 'OK':
                if 'message' in params:
                    raise RuntimeError("Unable to request D-ITG test. Control server reported error: %s" % params['message'])
                else:
                    raise RuntimeError("Unable to request D-ITG test. Control server reported an unspecified error.")
            self.test_id = params['test_id']
        except xmlrpc.Fault as e:
            raise RuntimeError("Error while requesting D-ITG test: %s" % e)
        self.command = self.command.format(signal_port = params['port'], dest_port=params['port']+1)
        self.args = shlex.split(self.command)
        ProcessRunner.start(self)

    def parse(self, output):
        data = ""
        utc_offset = 0
        results = {}
        try:
            # The control server has a grace period after the test ends, so we don't know exactly
            # when the test results are going to be ready. We assume that
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
                    self.err = "Error while getting results. Control server reported error: %s" % res['message']
                else:
                    self.err = "Error while getting results. Control server reported unknown error."
        except xmlrpc.Fault as e:
            self.err = "Error while getting results: %s" % e

        dt = datetime.utcfromtimestamp(utc_offset)
        offset = float(calendar.timegm(dt.timetuple())) + dt.microsecond / 10**6

        for line in data.splitlines():
            if not line.strip():
                continue
            parts = [float(i) for i in line.split()]
            timestamp = parts.pop(0) + offset
            for i,n in enumerate(('bitrate', 'delay', 'jitter', 'loss')):
                if not n in results:
                    results[n] = []
                results[n].append([timestamp, parts[i]])

        return results

class NetperfDemoRunner(ProcessRunner):
    """Runner for netperf demo mode."""

    def parse(self, output):
        """Parses the interim result lines and returns a list of (time,value)
        pairs."""

        result = []
        lines = output.split("\n")
        for line in lines:
            if line.startswith("Interim"):
                parts = line.split()
                result.append([float(parts[9]), float(parts[2])])

        return result

class PingRunner(ProcessRunner):
    """Runner for ping/ping6 in timestamped (-D) mode."""

    pingline_regex = re.compile(r'^\[([0-9]+\.[0-9]+)\].*time=([0-9]+(?:\.[0-9]+)?) ms$')
    fpingline_regex = re.compile(r'^\[([0-9]+\.[0-9]+)\].*:.*, ([0-9]+(?:\.[0-9]+)?) ms \(.*\)$')

    def parse(self, output):
        result = []
        lines = output.split("\n")
        for line in lines:
            match = self.pingline_regex.match(line)
            if not match:
                match = self.fpingline_regex.match(line)
            if match:
                result.append([float(match.group(1)), float(match.group(2))])

        return result

class IperfCsvRunner(ProcessRunner):
    """Runner for iperf csv output (-y C), possibly with unix timestamp patch."""

    def parse(self, output):
        result = []
        lines = output.strip().split("\n")
        for line in lines[:-1]: # The last line is an average over the whole test
            parts = line.split(",")
            if len(parts) < 8:
                continue

            timestamp = parts[0]
            bandwidth = parts[8]

            # If iperf is patched to emit sub-second resolution unix timestamps,
            # there'll be a dot as the decimal marker; in this case, just parse
            # the time as a float. Otherwise, assume that iperf is unpatched
            # (and so emits YMDHMS timestamps).
            #
            # The patch for iperf (v2.0.5) is in the misc/ directory.
            if "." in timestamp:
                result.append([float(timestamp), float(bandwidth)])
            else:
                dt = datetime.strptime(timestamp, "%Y%m%d%H%M%S")
                result.append([time.mktime(dt.timetuple()), float(bandwidth)])

        return result

class TcRunner(ProcessRunner):
    """Runner for iterated `tc -s qdisc`. Expects iterations to be separated by
    '\n---\n and a timestamp to be present in the form 'Time: xxxxxx.xxx' (e.g.
    the output of `date '+Time: %s.%N'`)."""

    def __init__(tc_parameter, *args, **kwargs):
        ProcessRunner.__init__(self, *args, **kwargs)
        self.tc_parameter = tc_parameter

    time_re   = re.compile(r"^Time: (?P<timestamp>\d+\.\d+)", re.MULTILINE)
    split_re  = re.compile(r"^qdisc ", re.MULTILINE)
    qdisc_res = [
        re.compile(r"Sent (?P<sent_bytes>\d+) bytes (?P<sent_pkts>\d+) pkt "
                   r"\(dropped (?P<dropped>\d+), "
                   r"overlimits (?P<overlimits>\d+) "
                   r"requeues (?P<requeues>\d+)\)"),
        re.compile(r"backlog (?P<backlog_bytes>\d+)b "
                   r"(?P<backlog_pkts>\d+)p "
                   r"requeues (?P<backlog_requeues>\d+)"),
        re.compile(r"maxpacket (?P<maxpacket>\d+) "
                   r"drop_overlimit (?P<drop_overlimit>\d+) "
                   r"new_flow_count (?P<new_flow_count>\d+) "
                   r"ecn_mark (?P<ecn_mark>\d+)"),
        re.compile(r"new_flows_len (?P<new_flows_len>\d+) "
                   r"old_flows_len (?P<old_flows_len>\d+)")
        ]


    def parse(self, output):
        result = []
        parts = output.split("\n---\n")
        for part in parts:
            # Split out individual qdisc entries (in case there are more than
            # one). If so, discard the root qdisc and sum the rest.
            qdiscs = self.split_re.split(part)
            if len(qdiscs) > 2:
                part = "qdisc ".join([i for i in qdiscs if not 'root' in i])

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
                    for k,v in list(m.groupdict().items()):
                        if not k in matches:
                            matches[k] = float(v)
                        else:
                            matches[k] += float(v)
                    m = r.search(part, m.end(0))
            key = self.tc_parameter
            if key in matches:
                result.append([timestamp, matches[key]])
            else:
                sys.stderr.write("Warning: Missing value for %s" % key)
        return result

class NullRunner(object):
    def __init__(self, *args, **kwargs):
        self.result = None
        self.command = 'null'
        self.returncode = 0
        self.out = self.err = ''
    # Emulate threading interface to fit into aggregator usage.
    def start(self):
        pass
    def join(self):
        pass
    def isAlive(self):
        return False
    def kill(self):
        pass

class ComputingRunner(object):
    command = "Computed"
    def __init__(self, name, apply_to=None, *args, **kwargs):
        self.name = name
        if apply_to is None:
            self.keys = []
        else:
            self.keys = apply_to

        # These are use for debug logging
        self.returncode = 0
        self.out = ""
        self.err = ""

    # Emulate threading interface to fit into aggregator usage.
    def start(self):
        pass
    def join(self):
        pass
    def isAlive(self):
        return False
    def kill(self):
        pass

    def result(self, res):
        if not self.keys:
            return res

        new_res = []
        keys = Glob.expand_list(self.keys,res.series_names,[self.name])

        for r in res.zipped(keys):
            values = [v for v in r[1:] if v is not None]
            if not values:
                new_res.append(None)
            else:
                new_res.append(self.compute(values))

        res.add_result(self.name, new_res)
        return res

    def compute(self, values):
        """Compute the function on the values this runner should be applied to.

        Default implementation returns None."""
        return None

class AverageRunner(ComputingRunner):
    command = "Average (computed)"
    def compute(self,values):
        return math.fsum(values)/len(values)

class SmoothAverageRunner(ComputingRunner):
    command = "Smooth average (computed)"
    def __init__(self, smooth_steps=5, *args, **kwargs):
        ComputingRunner.__init__(self, *args, **kwargs)
        self._smooth_steps = smooth_steps
        self._avg_values = []

    def compute(self, values):
        self._avg_values.append(math.fsum(values)/len(values))
        while len(self._avg_values) > self._smooth_steps:
            self._avg_values.pop(0)
        return math.fsum(self._avg_values)/len(self._avg_values)

class SumRunner(ComputingRunner):
    command = "Sum (computed)"
    def compute(self,values):
        return math.fsum(values)
