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
import io
import itertools
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

from flent import util, transformers
from flent.build_info import DATA_DIR
from flent.util import classname, ENCODING, Glob, normalise_host, utcnow
from flent.loggers import get_logger

try:
    import ujson as json
except ImportError:
    import json

try:
    from multiprocessing.reduction import DupFd
except ImportError:
    DupFd = None


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


class ParseError(Exception):
    pass


class RunnerCheckError(Exception):
    pass


def get(name):
    cname = classname(name, "Runner")
    if cname not in globals():
        raise RuntimeError("Runner not found: '%s'" % name)
    return globals()[cname]


MARKING_MAP = {'AF11': 0x28,
               'AF12': 0x30,
               'AF13': 0x38,
               'AF21': 0x48,
               'AF22': 0x50,
               'AF23': 0x58,
               'AF31': 0x68,
               'AF32': 0x70,
               'AF33': 0x78,
               'AF41': 0x88,
               'AF42': 0x90,
               'AF43': 0x98,
               'CS0':  0x00,
               'CS1':  0x20,
               'CS2':  0x40,
               'CS3':  0x60,
               'CS4':  0x80,
               'CS5':  0xa0,
               'CS6':  0xc0,
               'CS7':  0xe0,
               'EF':   0xb8}


class RunnerBase(object):

    transformed_metadata = []

    def __init__(self, name, settings, idx=None, start_event=None,
                 finish_event=None, kill_event=None, parent=None,
                 watchdog_timer=None, **kwargs):
        super(RunnerBase, self).__init__()
        self.runner_name = name
        self.settings = settings
        self.idx = idx
        self.test_parameters = {}
        self._raw_values = []
        self._result = []
        self.command = None
        self.returncode = 0
        self.out_buf = self.err_buf = ''
        self.stdout = None
        self.stderr = None
        self._parent = parent
        self.result = None

        self.start_event = start_event
        self.kill_event = kill_event or Event()
        self.finish_event = finish_event or Event()
        self.watchdog_timer = watchdog_timer
        self._watchdog = None

        self._child_runners = []

        self._pickled = False

        self.metadata = {'RUNNER': self.__class__.__name__, 'IDX': idx}
        self.runner_args = kwargs

        self._cache = None
        self._thread = None

    def __getstate__(self):
        state = {}

        for k, v in self.__dict__.items():
            if k not in ('start_event', 'kill_event', 'finish_event',
                         'stdout', 'stderr') \
                    and not k.startswith("_"):
                state[k] = v

        state['_pickled'] = True

        if DupFd is not None:
            if self.stdout is not None:
                state['_stdout_fd'] = DupFd(self.stdout.fileno())
            if self.stderr is not None:
                state['_stderr_fd'] = DupFd(self.stderr.fileno())

        return state

    def __setstate__(self, state):
        stdout_fd = state.pop("_stdout_fd")
        if stdout_fd is not None:
            self.stdout = io.open(stdout_fd.detach(), "w+", encoding=ENCODING)

        stderr_fd = state.pop("_stderr_fd")
        if stderr_fd is not None:
            self.stderr = io.open(stderr_fd.detach(), "w+", encoding=ENCODING)

        self.__dict__.update(state)

    def __del__(self):
        self.close()

    @property
    def name(self):
        return f"{self.__class__.__name__}({self.runner_name})"

    def debug(self, msg, *args, **kwargs):
        logger.debug("%s: " + msg,
                     self.name, *args, **kwargs)

    @property
    def out(self):
        if self.stdout is None:
            return self.out_buf
        self.stdout.seek(0)
        return self.out_buf + self.stdout.read()

    @property
    def err(self):
        if self.stderr is None:
            return self.err_buf
        self.stderr.seek(0)
        return self.err_buf + self.stderr.read()

    @property
    def cache(self):
        if self._cache is None:
            self._cache = util.get_cache(self.__class__.__name__)
        return self._cache

    def check(self):
        pass

    def do_parse(self, pool):
        res = []
        for c in self._child_runners:
            res.extend(c.do_parse(pool))
        return res

    def post_parse(self):
        for c in self._child_runners:
            c.post_parse()

    # Emulate threading interface to fit into aggregator usage.
    def start(self):
        if self._pickled:
            raise RuntimeError("Attempt to run a pickled runner")

        count = 0
        for c in self._child_runners:
            count += c.start()
        return count

    def join(self, timeout=None):
        if self._thread is not None:
            self._thread.join(timeout)

        for c in self._child_runners:
            c.join(timeout)

    def is_alive(self):
        alive = []
        if self._thread is not None:
            alive.append(self._thread.is_alive())

        alive.extend([c.is_alive() for c in self._child_runners])
        return any(alive)

    def kill(self):
        for c in self._child_runners:
            c.kill()
        self.kill_event.set()

    def close(self):
        if getattr(self, "_closed", False):
            return

        for c in getattr(self, "_child_runners", []):
            c.close()
        if self.stdout is not None:
            self.stdout.close()
            self.stdout = None
        if self.stderr is not None:
            self.stderr.close()
            self.stderr = None

        self._closed = True
        self._parent = None # break reference cycle

    def run(self):
        if self.start_event is not None:
            self.start_event.wait()
        self._run()
        self.finish_event.set()
        self.debug("Finished", extra={'runner': self})

    def add_child(self, cls, **kwargs):
        self.debug("Adding child %s", cls.__name__)
        c = cls(name="%s :: child %d" % (self.runner_name, len(self._child_runners)),
                settings=self.settings,
                idx=self.idx,
                start_event=self.start_event,
                kill_event=self.kill_event,
                parent=self, **kwargs)
        c.check()
        self._child_runners.append(c)
        return c

    @property
    def child_results(self):
        for c in self._child_runners:
            res = c.result
            if res and hasattr(res, 'items'):
                yield res

    def get_raw_values(self):
        if not self._child_runners:
            return self._raw_values

        vals = list(self._raw_values)

        for c in self._child_runners:
            vals.extend(c.raw_values)
        return sorted(vals, key=lambda v: v['t'])

    def set_raw_values(self, val):
        self._raw_values = val

    raw_values = property(get_raw_values, set_raw_values)


class DelegatingRunner(RunnerBase):

    @property
    def child_results(self):
        return iter([])

    def get_metadata(self):
        md = {}
        for c in self._child_runners:
            md.update(c.metadata)
        return md

    def set_metadata(self, val):
        pass

    metadata = property(get_metadata, set_metadata)

    def _combine(self, vals):
        if not vals:
            return vals

        if hasattr(vals[0], 'keys'):
            r = {}
            for v in vals:
                if v:
                    r.update(v)
        else:
            r = []
            for v in vals:
                if v:
                    r.extend(v)

        return r

    def get_result(self):
        return self._combine([c.result for c in self._child_runners])

    def set_result(self, val):
        pass

    result = property(get_result, set_result)

    def fork(self):
        count = 0
        for c in self._child_runners:
            count += c.fork()
        return count

    def _run(self):
        for c in self._child_runners:
            c.join()


class ProcessRunner(RunnerBase):
    """Default process runner for any process."""
    silent = False
    silent_exit = False
    supports_remote = True
    success_return = [0]
    _env = {}

    def __init__(self, delay=0, remote_host=None, units=None, command=None, **kwargs):
        super(ProcessRunner, self).__init__(**kwargs)

        self.delay = delay
        self.remote_host = normalise_host(remote_host)
        self.units = units
        self.pid = None
        self.pid_fd = None
        self.returncode = None
        self.test_parameters = {}
        self.command = command
        self.start_time = None

    def check(self):

        if self.command is None:
            raise RunnerCheckError("No command set for %s" %
                                   self.__class__.__name__)
        if self.units:
            self.metadata['UNITS'] = self.units

        # Rudimentary remote host capability. Note that this is modifying the
        # final command, so all the find_* stuff must match on the local and
        # remote hosts. I.e. the same binaries must exist in the same places.
        if self.remote_host:
            if not self.supports_remote:
                raise RunnerCheckError(
                    "%s (idx %d) does not support running on remote hosts." % (
                        self.__class__.__name__, self.idx))
            self.command = "ssh %s '%s'" % (self.remote_host, self.command)
            self.metadata['REMOTE_HOST'] = self.remote_host

        self.args = shlex.split(self.command)
        self.metadata['COMMAND'] = self.command

    def handle_usr2(self, signal, frame):
        if self.start_event is not None:
            self.start_event.set()

    def cleanup(self):
        pass

    def fork(self):
        if mswindows:
            raise RuntimeError(
                "Process management currently doesn't work on Windows, "
                "so running tests is not possible.")

        count = 0

        for c in self._child_runners:
            count += c.fork()

        # Use named temporary files to avoid errors on double-delete when
        # running on Windows/cygwin.
        try:
            self.stdout = tempfile.TemporaryFile(mode="w+", prefix="flent-",
                                                 encoding=ENCODING)
            self.stderr = tempfile.TemporaryFile(mode="w+", prefix="flent-",
                                                 encoding=ENCODING)
        except OSError as e:
            if e.errno == 24:
                raise RuntimeError(
                    "Unable to create temporary files because too many "
                    "files are open. Try increasing ulimit.")
            else:
                raise RuntimeError("Unable to create temporary files: %s" % e)

        self.debug("Forking to run command %s", self.command)
        try:
            pid = os.fork()
        except OSError as e:
            raise RuntimeError(f"{self.name}: Error during fork(): {e}")

        if pid == 0:
            signal.signal(signal.SIGTERM, signal.SIG_DFL)
            devnull = os.open(os.devnull, os.O_RDWR)
            os.dup2(devnull, 0)
            os.dup2(self.stdout.fileno(), 1)
            os.dup2(self.stderr.fileno(), 2)
            self.stdout.close()
            self.stderr.close()
            os.closerange(3, 65535)
            pid = os.getpid()

            try:
                if self.start_event is not None:
                    os.write(2, f"{time.time()}: PID {pid} waiting for SIGUSR2\n".encode("utf-8"))
                    signal.signal(signal.SIGUSR2, self.handle_usr2)
                    self.start_event.wait()
                    signal.signal(signal.SIGUSR2, signal.SIG_DFL)

                os.write(2, f"{time.time()}: PID {pid} sleeping for {self.delay} seconds\n".encode("utf-8"))
                time.sleep(self.delay)
            except:
                os._exit(0)

            env = dict(os.environ)
            env.update(self._env)
            prog = self.args[0]
            os.write(2, f"{time.time()}: PID {pid} running execvpe({' '.join(self.args)})\n".encode("utf-8"))
            os.execvpe(prog, self.args, env)
        else:
            self.debug("Forked %s as pid %d", self.args[0], pid)
            self.pid = pid
            self.start_time = time.monotonic()
            return count + 1

    def start(self):
        count = super().start()
        self._thread = threading.Thread(target=self.run)
        self._thread.start()
        return count + 1

    def kill(self):
        super().kill()
        if self._thread is None and self.pid is not None:
            self._kill_child(immediate=True)

    def _try_kill_child(self, sig):
        self.debug("Sending signal %d to pid %d", sig, self.pid)
        try:
            os.kill(self.pid, sig)

            for _ in range(10):
                if os.waitpid(self.pid, os.WNOHANG) != (0, 0):
                    return True
                time.sleep(0.1)
        except (OSError, ChildProcessError):
            pass

        return False

    def _kill_child(self, immediate=False):
        self.silent_exit = True

        if not immediate:
            if self._try_kill_child(signal.SIGINT):
                return
            if self._try_kill_child(signal.SIGTERM):
                return
        try:
            if os.waitpid(self.pid, os.WNOHANG) == (0, 0):
                self.debug("Sending SIGKILL to pid %d", self.pid)
                os.kill(self.pid, signal.SIGKILL)

                # Do a final waitpid() to reap the zombie process
                os.waitpid(self.pid, 0)

        except (OSError, ChildProcessError):
            pass

        self.cleanup()

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

        timeout = False
        pid, sts = os.waitpid(self.pid, os.WNOHANG)
        while (pid, sts) == (0, 0):
            self.kill_event.wait(1)

            if self.watchdog_timer:
                runtime = time.monotonic() - self.start_time
                timeout = runtime > self.watchdog_timer

            if self.kill_event.is_set() or timeout:
                self.debug("Killed by %s", "timeout" if timeout else "event",
                           extra={'runner': self})
                self._kill_child()
                return

            pid, sts = os.waitpid(self.pid, os.WNOHANG)

        self.finish_event.set()

        self.returncode = _handle_exitstatus(sts)
        if self.returncode not in self.success_return and not (self.silent or self.silent_exit):
            logger.warning("Program exited non-zero.",
                           extra={'runner': self})

        self.cleanup()

        self.debug("Finished", extra={'runner': self})

    def parse(self, output, error):
        raise NotImplementedError()

    def parse_error(self, error):
        logger.exception("Parse error in %s: %s", self.__class__.__name__, error,
                         exc_info=error.__cause__)

    # Wrap parse() so that we only read from self.stdout and self.stderr in
    # the subprocess (since we pass around the stdout and stderr fds and
    # only read them when we need to access the output)
    def parse_output(self):
        # Make sure we start from the beginning (we could already have read the
        # data through self.{out,err})
        self.stdout.seek(0)
        self.stderr.seek(0)
        return self.parse(self.stdout, self.stderr)

    def parse_string(self, string):
        out = io.StringIO(string)
        err = io.StringIO()
        return self.parse(out, err)

    def do_parse_direct(self):
        try:
            res = self.parse_output()
            self.recv_result(res)
        except Exception as e:
            self.parse_error(e)

        for c in self._child_runners:
            c.do_parse(None)

        return []

    def do_parse(self, pool):
        if pool is None:
            return self.do_parse_direct()

        res = [pool.apply_async(self.parse_output,
                                callback=self.recv_result,
                                error_callback=self.parse_error)]
        for c in self._child_runners:
            res.extend(c.do_parse(pool))
        return res

    def recv_result(self, res):
        result, raw_values, metadata = res
        self.result = result
        self.raw_values = raw_values
        self.metadata.update(metadata)
        if not result and not self.silent:
            logger.warning("Command produced no valid data.",
                           extra={'runner': self})

    def run_simple(self, args, kill=None, errmsg=None):
        if self.remote_host:
            args = ['ssh', self.remote_host, ' '.join(args)]
            if kill:
                kill = max(kill, 1)
        try:
            proc = subprocess.run(args, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=kill)
            out = proc.stdout.decode(ENCODING)
            err = proc.stderr.decode(ENCODING)
            ret = proc.returncode
        except subprocess.TimeoutExpired as e:
            out = e.stdout.decode(ENCODING) if e.stdout else ""
            err = e.stderr.decode(ENCODING) if e.stderr else ""
            ret = 1

        if ret != 0 and errmsg:
            raise RunnerCheckError(errmsg.format(err=err))

        return out, err

    def _get_marking(self, marking):
        mk = marking.upper()

        if mk in MARKING_MAP:
            mkval = MARKING_MAP[mk]
        elif mk in self.settings.MARKING_NAMES:
            mkval = self.settings.MARKING_NAMES[mk]
        else:
            try:
                mkval = util.parse_int(marking)
            except ValueError:
                raise RuntimeError("Invalid marking: %s" % marking)

        return "0x%x" % mkval

    def parse_marking(self, marking, fmtstr, paired=False):
        """Convert netperf-style textual marking specs into integers"""
        if marking is not None:
            try:
                mk = marking.split(",")
                if paired and len(mk) > 1:
                    return fmtstr.format("{},{}".format(self._get_marking(mk[0]),
                                                        self._get_marking(mk[1])))
                return fmtstr.format(self._get_marking(mk[0]))
            except (AttributeError, KeyError):
                return fmtstr.format(self.marking)

        return ""

    def split_stream(self, stream, delim="---"):
        part = ""
        for line in stream:
            if line.strip() == delim:
                yield part.strip()
                part = ""
                continue
            part += line

        if part:
            yield part.strip()


DefaultRunner = ProcessRunner


class SilentProcessRunner(ProcessRunner):
    silent = True

    def parse(self, output, error=""):
        return {}, [], {}


class DitgRunner(ProcessRunner):
    """Runner for D-ITG with a control server."""
    supports_remote = False
    transformers = {'delay': transformers.s_to_ms,
                    'jitter': transformers.s_to_ms,
                    'bitrate': transformers.identity,
                    'loss': transformers.identity}

    def __init__(self, test_args, host, length, interval,
                 local_bind=None, control_host=None, **kwargs):
        super(DitgRunner, self).__init__(**kwargs)

        if not control_host:
            control_host = self.settings.CONTROL_HOST or self.settings.HOST
        control_host = normalise_host(control_host)

        if not local_bind and self.settings.LOCAL_BIND:
            local_bind = self.settings.LOCAL_BIND[0]

        self.proxy = xmlrpc.ServerProxy("http://%s:%s"
                                        % (control_host,
                                           self.settings.DITG_CONTROL_PORT),
                                        allow_none=True)
        self.ditg_secret = self.settings.DITG_CONTROL_SECRET

        self.test_args = test_args
        self.length = length
        self.host = normalise_host(host)
        self.interval = interval
        self.local_bind = local_bind

    def check(self):
        try:
            # We want to request a test that is long enough to keep the server
            # alive for the duration of the whole test, even though we may not
            # start ITGSend until after a delay
            length = max(self.length, self.settings.TOTAL_LENGTH)

            interval = int(self.interval * 1000)
            hm = hmac.new(self.ditg_secret.encode(
                'UTF-8'), digestmod=hashlib.sha256)
            hm.update(str(length).encode('UTF-8'))
            hm.update(str(interval).encode('UTF-8'))
            params = self.proxy.request_new_test(length, interval,
                                                 hm.hexdigest(), True)
            if params['status'] != 'OK':
                if 'message' in params:
                    raise RunnerCheckError(
                        "Unable to request D-ITG test. "
                        "Control server reported error: %s" % params['message'])
                else:
                    raise RunnerCheckError(
                        "Unable to request D-ITG test. "
                        "Control server reported an unspecified error.")
            self.test_id = params['test_id']
            self.out_buf += "Test ID: %s\n" % self.test_id
        except (xmlrpc.Fault, socket.error) as e:
            raise RunnerCheckError(
                "Error while requesting D-ITG test: '%s'. "
                "Is the control server listening (see man page)?" % e)

        itgsend = util.which("ITGSend", fail=RunnerCheckError)

        # We put placeholders in the command string to be filled out by string
        # format expansion by the runner once it has communicated with the control
        # server and obtained the port values.
        self.command = "{binary} -Sdp {signal_port} -t {length} {local_bind} " \
                       "-a {dest_host} -rp {dest_port} {args}".format(
                           binary=itgsend,
                           length=int(self.length * 1000),
                           dest_host=self.host,
                           local_bind="-sa {0} -Ssa {0}".format(
                               self.local_bind) if self.local_bind else "",
                           args=self.test_args,
                           signal_port=params['port'],
                           dest_port=params['port'] + 1)

        super(DitgRunner, self).check()

    def parse_output(self):
        data = ""
        utc_offset = 0
        results = {}
        raw_values = []
        metadata = {}
        try:
            # The control server has a grace period after the test ends, so we
            # don't know exactly when the test results are going to be ready. We
            # assume that it will be within ten seconds.
            for i in range(10):
                res = self.proxy.get_test_results(self.test_id)
                if res['status'] == 'OK':
                    data = res['data']
                    self.out_buf += data
                    utc_offset = res['utc_offset']
                    break
                time.sleep(1)
            if res['status'] != 'OK':
                if 'message' in res:
                    self.err_buf += "Error while getting results. " \
                                 "Control server reported error: %s.\n" \
                                 % res['message']
                else:
                    self.err_buf += "Error while getting results. " \
                                 "Control server reported unknown error.\n"
        except xmlrpc.Fault as e:
            self.err_buf += "Error while getting results: %s.\n" % e

        # D-ITG *should* output about 50 bytes of data per data point. However,
        # sometimes it runs amok and outputs megabytes of erroneous data. So, if
        # the length of the data is more than ten times the expected value,
        # abort rather than try to process the data.
        if len(data) > (self.length / self.interval) * 500:
            self.err_buf += "D-ITG output too much data (%d bytes).\n" % len(data)
            return results

        if 'raw' in res:
            raw_values = self.parse_raw(res['raw'])

        for line in data.splitlines():
            if not line.strip():
                continue
            parts = [float(i) for i in line.split()]
            timestamp = parts.pop(0) + utc_offset
            for i, n in enumerate(('bitrate', 'delay', 'jitter', 'loss')):
                if n not in results:
                    results[n] = []
                results[n].append([timestamp, self.transformers[n](parts[i])])

        return results, raw_values, metadata

    def parse_raw(self, data):
        raw_values = []

        for line in data.splitlines():
            parts = list(filter(None, re.split(r"(\S+)>\s*", line)))
            vals = dict(zip(parts[::2], parts[1::2]))
            times = {}
            for v in ('txTime', 'rxTime'):
                t, microsec = vals[v].split(".")
                h, m, s = t.split(":")
                # FIXME: This is definitely going to break if a test is run
                # around midnight
                dt = utcnow().replace(hour=int(h),
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

        return raw_values


class NetperfDemoRunner(ProcessRunner):
    """Runner for netperf demo mode."""
    transformed_metadata = ('MEAN_VALUE',)
    output_vars = 'THROUGHPUT,LOCAL_CONG_CONTROL,REMOTE_CONG_CONTROL,' \
                  'TRANSPORT_MSS,LOCAL_TRANSPORT_RETRANS,' \
                  'REMOTE_TRANSPORT_RETRANS,LOCAL_SOCKET_TOS,' \
                  'REMOTE_SOCKET_TOS,DIRECTION,ELAPSED_TIME,PROTOCOL,' \
                  'LOCAL_SEND_SIZE,LOCAL_RECV_SIZE,' \
                  'REMOTE_SEND_SIZE,REMOTE_RECV_SIZE,' \
                  'LOCAL_BYTES_SENT,LOCAL_BYTES_RECVD,' \
                  'REMOTE_BYTES_SENT,REMOTE_BYTES_RECVD'
    _env = {"DUMP_TCP_INFO": "1"}

    def __init__(self, test, length, host, bytes=None, **kwargs):
        self.test = test
        self.length = length
        self.host = normalise_host(host)
        self.bytes = bytes
        super(NetperfDemoRunner, self).__init__(**kwargs)

    def parse(self, output, error):
        """Parses the interim result lines and returns a list of (time,value)
        pairs."""

        result = []
        raw_values = []
        metadata = {}
        avg_dur = None
        alpha = 0.5
        data_dict = {}

        # We use the -k output option for netperf, so we will get data in
        # KEY=VALUE lines. The interim points will be NETPERF_*[id] lines,
        # end-of-test data points will be straight KEY=VAL lines
        for line in output:
            line = line.strip()
            try:
                k, v = line.split("=", 1)
                if k.endswith(']'):
                    k, i = k.split('[', 1)
                    i = i[:-1]
                    if k not in data_dict:
                        data_dict[k] = []
                    data_dict[k].append(v)
                else:
                    if k in data_dict:
                        logger.warning("Duplicate key in netperf results: %s", k)
                    data_dict[k] = v
            except ValueError:
                pass

        # TCP_INFO values are output to stderr
        for line in error:
            line = line.strip()
            if line.startswith("tcpi"):
                parts = line.split()
                data_dict.update(dict(zip(parts[::2], parts[1::2])))

        try:
            for dur, t, value in zip(data_dict['NETPERF_INTERVAL'],
                                     data_dict['NETPERF_ENDING'],
                                     data_dict['NETPERF_INTERIM_RESULT']):

                dur = float(dur)
                t = float(t)
                value = float(value)

                if self.test == 'UDP_RR':
                    value = transformers.rr_to_ms(value)

                # Calculate an EWMA of the netperf sampling duration and exclude
                # data points from a sampling period that is more than an order
                # of magnitude higher or lower than this average; these are
                # probably the result of netperf spitting out a measurement at
                # the end of a run after having lost the measurement flow during
                # the run, or a very short interval giving a very high bandwidth
                # measurement
                if avg_dur is None:
                    avg_dur = dur

                if dur < avg_dur * 10.0 and dur > avg_dur / 10.0:
                    raw_values.append({'dur': dur, 't': t, 'val': value})
                    result.append([t, value])
                    avg_dur = alpha * avg_dur + (1.0 - alpha) * dur

            try:
                # The THROUGHPUT key contains the mean value even for UDP_RR tests
                metadata['MEAN_VALUE'] = float(data_dict['THROUGHPUT'])
                if self.test == 'UDP_RR':
                    metadata['MEAN_VALUE'] = transformers.rr_to_ms(metadata['MEAN_VALUE'])

                metadata['ELAPSED_TIME'] = float(data_dict.get('ELAPSED_TIME', 0))
                metadata['UPSTREAM_TOS'] = int(data_dict.get('LOCAL_SOCKET_TOS', 0),
                                                    base=0)
                metadata['DOWNSTREAM_TOS'] = int(data_dict.get(
                    'REMOTE_SOCKET_TOS', 0), base=0)

                if data_dict['PROTOCOL'] == 'TCP':
                    metadata['TCP_MSS'] = int(data_dict.get('TRANSPORT_MSS',
                                                                 0))
                    if data_dict['DIRECTION'] == 'Send':
                        metadata['CONG_CONTROL'] = data_dict.get(
                            'LOCAL_CONG_CONTROL')
                        metadata['TCP_RETRANSMIT'] = data_dict.get(
                            'LOCAL_TRANSPORT_RETRANS')
                        metadata['SEND_SIZE'] = int(data_dict.get(
                            'LOCAL_SEND_SIZE', -1))
                        metadata['RECV_SIZE'] = int(data_dict.get(
                            'REMOTE_RECV_SIZE', -1))
                        metadata['BYTES_SENT'] = int(data_dict.get(
                            'LOCAL_BYTES_SENT', -1))
                        metadata['BYTES_RECVD'] = int(data_dict.get(
                            'REMOTE_BYTES_RECVD', -1))
                        metadata['DATA_TOS'] = metadata['UPSTREAM_TOS']
                    else:
                        metadata['CONG_CONTROL'] = data_dict.get(
                            'REMOTE_CONG_CONTROL')
                        metadata['TCP_RETRANSMIT'] = int(data_dict.get(
                            'REMOTE_TRANSPORT_RETRANS', 0))
                        metadata['SEND_SIZE'] = int(data_dict.get(
                            'REMOTE_SEND_SIZE', -1))
                        metadata['RECV_SIZE'] = int(data_dict.get(
                            'LOCAL_RECV_SIZE', -1))
                        metadata['BYTES_SENT'] = int(data_dict.get(
                            'REMOTE_BYTES_SENT', -1))
                        metadata['BYTES_RECVD'] = int(data_dict.get(
                            'LOCAL_BYTES_RECVD', -1))
                        metadata['DATA_TOS'] = metadata['DOWNSTREAM_TOS']

                    for k in data_dict.keys():
                        if k.startswith("tcpi"):
                            metadata[k.upper()] = int(data_dict[k])
            except KeyError as e:
                logger.warning("Missing required netperf metadata: %s", e.args[0])

        except KeyError:
            pass  # No valid data

        return result, raw_values, metadata

    def check(self):
        args = self.runner_args.copy()

        if self.test.lower() == 'omni':
            raise RunnerCheckError("Use of netperf 'omni' test is not supported")

        args.setdefault('ip_version', self.settings.IP_VERSION)
        args.setdefault('interval', self.settings.STEP_SIZE)
        args.setdefault('control_host', self.settings.CONTROL_HOST or self.host)
        args.setdefault('control_port', self.settings.NETPERF_CONTROL_PORT)
        args.setdefault('local_bind',
                        self.settings.LOCAL_BIND[0]
                        if self.settings.LOCAL_BIND else "")
        args.setdefault('control_local_bind',
                        self.settings.CONTROL_LOCAL_BIND or args['local_bind'])
        args.setdefault('extra_args', "")
        args.setdefault('extra_test_args', "")
        args.setdefault('format', "")
        args.setdefault('marking', "")
        args.setdefault('cong_control',
                        self.settings.TEST_PARAMETERS.get('tcp_cong_control', ''))
        args.setdefault('socket_timeout', self.settings.SOCKET_TIMEOUT)
        args.setdefault('send_size',
                        self.settings.SEND_SIZE[0]
                        if self.settings.SEND_SIZE else "")
        args.setdefault('test_payload', self.settings.TEST_PAYLOAD)

        if self.settings.SWAP_UPDOWN:
            if self.test == 'TCP_STREAM':
                self.test = 'TCP_MAERTS'
            elif self.test == 'TCP_MAERTS':
                self.test = 'TCP_STREAM'

        cache_key = self.remote_host or ""
        if cache_key in self.cache:
            netperf = self.cache[cache_key]
        else:
            nperf = util.which('netperf', fail=RunnerCheckError,
                               remote_host=self.remote_host)

            # Try to figure out whether this version of netperf supports the -e
            # option for socket timeout on UDP_RR tests, and whether it has been
            # compiled with --enable-demo. Unfortunately, the --help message is
            # not very helpful for this, so the only way to find out is try to
            # invoke it and check for an error message. This has the side-effect
            # of having netperf attempt a connection to localhost, which can
            # stall, so we kill the process almost immediately.

            # should be enough time for netperf to output any error messages
            out, err = self.run_simple([nperf, '-l', '1', '-D', '-0.2',
                                        '--', '-e', '1'], kill=0.1)

            if "Demo Mode not configured" in out:
                raise RunnerCheckError("%s does not support demo mode." % nperf)

            if "invalid option -- '0'" in err:
                raise RunnerCheckError(
                    "%s does not support accurate intermediate time reporting. "
                    "You need netperf v2.6.0 or newer." % nperf)

            netperf = {'executable': nperf, '-e': False}

            if "netperf: invalid option -- 'e'" not in err:
                netperf['-e'] = True

            try:
                # If --test-payload option is specified, use data from that file
                # else use the default value /dev/urandom.
                fill_file = args['test_payload']
                # Sanity check; is /dev/urandom or the custom file readable? If so, use it to
                # pre-fill netperf's buffers
                self.run_simple(['dd', 'if='+fill_file, 'of=/dev/null', 'bs=1', 'count=1'], errmsg="Err")
                netperf['buffer'] = '-F '+fill_file
            except RunnerCheckError:
                if(fill_file == '/dev/urandom'):
                    netperf['buffer'] = ''
                else:
                    # If the custom file is not readable, fail noisily
                    raise RunnerCheckError("The specified test payload file does not exist or is not readable.")

            # cache the value keyed on the remote_host, since the outcome might
            # differ depending on which host we're running on
            self.cache[cache_key] = netperf

        args['binary'] = netperf['executable']
        args['buffer'] = netperf['buffer']
        args['output_vars'] = self.output_vars
        args['test'] = self.test
        args['host'] = self.host
        args['control_host'] = normalise_host(args['control_host'])

        # make sure all unset args are empty strings (and not e.g. None)
        for k, v in args.items():
            if v is None:
                args[k] = ""

        if self.bytes:
            args['length'] = -self.bytes
        else:
            args['length'] = self.length
            self.watchdog_timer = self.length + self.delay + 10

        if args['marking']:
            args['marking'] = self.parse_marking(args['marking'], "-Y {}", True)

        if args['cong_control']:
            args['cong_control'] = "-K {0}".format(args['cong_control'])

        for c in 'local_bind', 'control_local_bind':
            if args[c]:
                args[c] = "-L {0},{1}".format(args[c], args['ip_version'])

        if self.test == "UDP_RR" and netperf["-e"]:
            args['socket_timeout'] = "-e {0:d}".format(args['socket_timeout'])
        else:
            args['socket_timeout'] = ""

        if self.test in ("TCP_STREAM", "TCP_MAERTS"):
            args['format'] = "-f m"
            if args['send_size']:
                args['send_size'] = "-m {0} -M {0}".format(args['send_size'])
            self.units = 'Mbits/s'

            if args['test'] == 'TCP_STREAM' and self.settings.SOCKET_STATS:
                self.add_child(SsRunner,
                               exclude_ports=(args['control_port'],),
                               delay=self.delay,
                               remote_host=None,
                               host=self.remote_host or 'localhost',
                               interval=args['interval'],
                               length=self.length,
                               target=self.host,
                               ip_version=args['ip_version'])
            args['host'] = f"-H {args['host']}"

        elif self.test == 'UDP_RR':
            self.units = 'ms'
            if args['ip_version'] == 6:
                if args['control_host'] != args['host'] or \
                   args['control_local_bind'] != args['local_bind']:

                    logger.warning("UDP_RR test doesn't support setting separate control host parameters for IPv6, ignoring")
                    args['control_host'] = args['host']
                    args['control_local_bind'] = args['local_bind']

                args['host'] = ""
                args['local_bind'] = ""
            else:
                args['host'] = f"-H {args['host']}"
        else:
            raise RunnerCheckError(f"Unknown netperf test type: {self.test}")


        self.command = "{binary} -P 0 -v 0 -D -{interval:.2f} -{ip_version} " \
                       "{marking} -H {control_host} -p {control_port} " \
                       "-t {test} -l {length:d} {buffer} {format} " \
                       "{control_local_bind} {extra_args} -- " \
                       "{socket_timeout} {send_size} {local_bind} {host} -k {output_vars} " \
                       "{cong_control} {extra_test_args}".format(**args)

        super(NetperfDemoRunner, self).check()


class RegexpRunner(ProcessRunner):

    """Runner that matches each line to one or more regular expressions,
    returning the values from the first matched.

    The regular expressions must define symbolic groups 'time' and 'value'."""

    regexes = []
    metadata_regexes = []
    transformers = {}

    def parse(self, output, error):
        result = []
        raw_values = []
        metadata = {}
        for line in itertools.chain(output, error):
            for regexp in self.regexes:
                match = regexp.match(line)
                if match:
                    rw = match.groupdict()
                    for k, v in rw.items():
                        try:
                            rw[k] = float(v)
                            if k in self.transformers:
                                rw[k] = self.transformers[k](rw[k])
                        except ValueError:
                            if k in self.transformers:
                                rw[k] = self.transformers[k](rw[k])
                    raw_values.append(rw)
                    if 'val' in rw:
                        result.append([rw['t'], rw['val']])
                    break  # only match one regexp per line
            for regexp in self.metadata_regexes:
                match = regexp.match(line)
                if match:
                    for k, v in match.groupdict().items():
                        if k == 't':
                            continue
                        try:
                            metadata[k] = float(v)
                            if k in self.transformed_metadata and \
                               'val' in self.transformers:
                                metadata[k] = self.transformers['val'](
                                    metadata[k])
                        except ValueError:
                            metadata[k] = v
        return result, raw_values, metadata


class PingRunner(RegexpRunner):
    """Runner for ping/ping6 in timestamped (-D) mode."""

    # Ping will change the comma separator for command line arguments based on
    # locale, which will break sub-second intervals. Override locale settings to
    # avoid this breaking stuff.
    _env = {"LC_ALL": "C", "LANG": "C"}

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

    def __init__(self, host, **kwargs):
        self.host = normalise_host(host)
        super(PingRunner, self).__init__(**kwargs)

    def check(self):
        args = self.runner_args.copy()
        args.setdefault('local_bind', (self.settings.LOCAL_BIND[0]
                                       if self.settings.LOCAL_BIND else None))
        args.setdefault('ip_version', self.settings.IP_VERSION)
        args.setdefault('interval', self.settings.STEP_SIZE)
        args.setdefault('length', self.settings.TOTAL_LENGTH)

        self.command = self.find_binary(host=self.host, **args)
        super(PingRunner, self).check()

    def use_fping(self, fping, ip_version, interval, length, host, marking, local_bind):
            # Since there is not timeout parameter to fping, set a watchdog
            # timer to kill it in case it runs over time
            self.watchdog_timer = self.delay + length + max(1,
                                                            int((self.delay + length) * 0.05))
            return "{binary} {ipver} -D -p {interval:.0f} -c {count:.0f} " \
                "-t {timeout} {marking} {local_bind} {host}".format(
                    binary=fping,
                    ipver='-6' if (ip_version == 6 and
                                   not fping.endswith("6")) else "",
                    interval=interval * 1000,  # fping expects interval in ms
                    # since there's no timeout parameter for fping,
                    # calculate a total number of pings to send
                    count=length // interval + 1,
                    # the timeout parameter is not the kind of timeout we
                    # want, rather it is the time after which fping will
                    # ignore late replies. We don't ever want to ignore late
                    # replies, so set this to a really high value (twice the
                    # full test length). This only affects fping v4.0+;
                    # earlier versions will ignore -t when running in -c mode.
                    timeout=length * 2000,
                    marking=self.parse_marking(marking, "-O {0}"),
                    local_bind=("-S {0}".format(local_bind)
                                if local_bind else ""),
                    host=host)

    def use_ping(self, ping, pingargs, interval, length, host, marking, local_bind):

            return "{binary} -n -D -i {interval:.2f} -w {length:d} {marking} " \
                "{local_bind} {pingargs} {host}".format(
                    binary=ping,
                    interval=max(0.2, interval),
                    length=length,
                    marking=self.parse_marking(marking, "-Q {0}"),
                    local_bind="-I {0}".format(local_bind) if local_bind else "",
                    host=host,
                    pingargs=" ".join(pingargs))

    def find_binary(self, ip_version, interval, length, host,
                    marking=None, local_bind=None, **kwargs):
        """Find a suitable ping executable, looking first for a compatible
        `fping`, then falling back to the `ping` binary. Binaries are checked
        for the required capabilities."""

        key_fping = f"fping,{ip_version},{self.remote_host or ''}"
        key_ping = f"ping,{ip_version},{self.remote_host or ''}"

        if key_fping in self.cache:
            return self.use_fping(self.cache[key_fping],
                                  ip_version, interval, length,
                                  host, marking, local_bind)

        if key_ping in self.cache:
            ping, pingargs = self.cache[key_ping]
            return self.use_ping(ping, pingargs, interval, length,
                                 host, marking, local_bind)

        if ip_version == 6:
            suffix = "6"
        else:
            suffix = ""

        # Ping and fping can't handle hostnames for the -I parameter, so do a
        # lookup first.
        if local_bind:
            local_bind = util.lookup_host(local_bind, ip_version)[4][0]

        fping = util.which('fping' + suffix, remote_host=self.remote_host) or util.which('fping', remote_host=self.remote_host)
        ping = util.which('ping' + suffix, remote_host=self.remote_host)
        pingargs = []

        if fping is not None:
            out, err = self.run_simple([fping, '-h'])
            # check for presence of timestamp option
            if ip_version == 6 and not fping.endswith("6") and \
               "--ipv6" not in str(out):
                logger.warning("Found fping, but it does not appear to "
                               "support IPv6. Not using.")
            elif "print timestamp before each output line" not in str(out):
                logger.warning("Found fping, but it does not appear to support "
                               "timestamps. Not using.")
            elif "must run as root?" in str(err):
                logger.warning("Found fping, but it appears to be missing "
                               "permissions (no SUID?). Not using.")
            else:
                out, err = self.run_simple([fping, '-D', '-c', '1',
                                            '-r', '0', '-t', '200',
                                            'localhost', host, 'one.one.one.one'])
                res = self.parse_string(out)
                try:
                    tdiff = abs(res[1][0]['t'] - time.time())
                except (TypeError, IndexError):
                    tdiff = None

                if tdiff is None:
                    logger.warning("Found fping, but couldn't parse its output. "
                                   "Not using.")
                elif tdiff > 100:
                    logger.warning("Found fping, but it outputs broken timestamps (off by %fs). "
                                   "Not using.", tdiff)
                else:
                    self.cache[key_fping] = fping
                    return self.use_fping(fping, ip_version, interval, length, host, marking, local_bind)

        if ping is None and ip_version == 6:
            # See if we have a combined ping binary (new versions of iputils)
            ping6 = util.which("ping", remote_host=self.remote_host)
            out, err = self.run_simple([ping6, '-h'])
            if '-6' in err:
                ping = ping6
                pingargs = ['-6']

        if ping is not None:
            # Try parsing the output of 'ping' and complain if no data is
            # returned from the parser. This should pick up e.g. the ping on OSX
            # not having a -D option and allow us to supply a better error
            # message.
            out, err = self.run_simple([ping, '-D', '-n', '-c', '1',
                                        'localhost'] + pingargs)
            if not self.parse_string(out)[0]:
                raise RunnerCheckError(
                    "Cannot parse output of the system ping binary ({ping}). "
                    "Please install fping v3.5+.".format(ping=ping))

            self.cache[key_ping] = (ping, pingargs)
            return self.use_ping(ping, pingargs, interval, length,
                                 host, marking, local_bind)

        raise RunnerCheckError("No suitable ping tool found.")


class HttpGetterRunner(RegexpRunner):

    regexes = [re.compile(
        r'^\[(?P<t>[0-9]+\.[0-9]+)\].*in (?P<val>[0-9]+(?:\.[0-9]+)?) seconds.$')]
    metadata_regexes = [re.compile(r'^.*min/avg/max(?:/mdev)? = '
                                   r'(?P<MIN_VALUE>[0-9]+(?:\.[0-9]+)?)/'
                                   r'(?P<MEAN_VALUE>[0-9]+(?:\.[0-9]+)?)/'
                                   r'(?P<MAX_VALUE>[0-9]+(?:\.[0-9]+)?).*$')]
    transformed_metadata = ('MEAN_VALUE', 'MIN_VALUE', 'MAX_VALUE')
    transformers = {'val': transformers.s_to_ms}

    def __init__(self, interval, length, workers=None, ip_version=None,
                 dns_servers=None, url_file=None, timeout=None, **kwargs):
        super(HttpGetterRunner, self).__init__(**kwargs)

        self.interval = interval
        self.length = length
        self.workers = workers
        self.ip_version = ip_version
        self.dns_servers = dns_servers
        self.url_file = url_file
        self.timeout = timeout

    def check(self):

        http_getter = util.which('http-getter', fail=RunnerCheckError, remote_host=self.remote_host)

        if self.url_file:
            url_file = self.url_file
        elif self.settings.HTTP_GETTER_URLLIST:
            url_file = self.settings.HTTP_GETTER_URLLIST[0]
        else:
            url_file = "http://{}/filelist.txt".format(normalise_host(self.settings.HOST))
        dns_servers = self.dns_servers or self.settings.HTTP_GETTER_DNS
        timeout = (self.timeout or self.settings.HTTP_GETTER_TIMEOUT
                   or int(self.length * 1000))
        workers = self.workers or self.settings.HTTP_GETTER_WORKERS
        ip_version = self.ip_version or self.settings.IP_VERSION

        self.command = "{binary} -i {interval} -l {length} -t {timeout} " \
                       "{dns} {workers} {ipv} {url_file}".format(
                           binary=http_getter,
                           interval=int(self.interval * 1000),
                           length=int(self.length),
                           timeout=timeout,
                           dns="-d {}".format(dns_servers) if dns_servers else "",
                           workers="-n {}".format(workers) if workers else "",
                           ipv="-{}".format(ip_version) if ip_version else "",
                           url_file=url_file)

        # Individual http requests can take a long time to time out, causing
        # http-getter to get stuck, so set a generous watchdog timer at 1.5
        # times the duration to catch any stuck binaries
        self.watchdog_timer = self.delay + (self.length * 3) // 2

        super(HttpGetterRunner, self).check()


class DashJsRunner(RegexpRunner):

    silent_exit = True
    _regex_prefix = r"^\[[0-9]+:[0-9]+:(?P<t>[0-9]+/[0-9]+\.[0-9]+):" \
        r"INFO:CONSOLE\([0-9]+\)\] "
    regexes = [
        re.compile(_regex_prefix + r'"D,[0-9]+,(?:BC|IR),(?P<bitrate>[0-9]+),'),
        re.compile(_regex_prefix + r'"D,[0-9]+,AT,(?P<val>[0-9\.]+),'),
        re.compile(_regex_prefix + r'"D,[0-9]+,ST,(?P<stall_dur>[0-9\.]+),'),
        re.compile(_regex_prefix + r'"D,[0-9]+,BL,(?P<buflen>[0-9]+),')]
    metadata_regexes = [
        re.compile(_regex_prefix + r'"D,[0-9]+,ID,(?P<INITIAL_DELAY>[0-9\.]+),')]

    def parse_chromium_timestamps(tstamp):
        sec, mil = tstamp.split(".")
        dt = datetime.strptime(sec, "%m%d/%H%M%S")
        dt = dt.replace(year=datetime.now().year)
        timestamp = time.mktime(dt.timetuple()) + float("0." + mil)
        return timestamp

    transformers = {'val': transformers.kbits_to_mbits,
                    'bitrate': transformers.bits_to_mbits,
                    't': parse_chromium_timestamps}

    def __init__(self, length, url, host='localhost', **kwargs):
        super(DashJsRunner, self).__init__(**kwargs)

        self.length = length
        self.url = url
        self.host = normalise_host(host)

    def parse(self, output, error=""):
        result, raw_values, metadata = super().parse(output, error)
        last_bitrate = None
        new_rv = []

        # Since the bitrate output happens when the bitrate changes, we insert a
        # value just before the change so the output becomes abrupt staircase
        # changes instead of gradual transitions when plotting
        for rw in raw_values:
            if 'bitrate' in rw:
                if last_bitrate is not None:
                    new_rv.append({'t': rw['t'], 'bitrate': last_bitrate})
                last_bitrate = rw['bitrate']
            new_rv.append(rw)

        # Also insert a value at the end with the last known bitrate
        if new_rv:
            new_rv.append({'t': new_rv[-1]['t'],
                           'bitrate': last_bitrate})

        return result, new_rv, metadata

    def check(self):
        self.command = self.find_binary(self.length, self.url, self.host)
        super(DashJsRunner, self).check()

    def find_binary(self, length, url, host='localhost'):
        script = os.path.join(DATA_DIR, 'scripts', 'dash_client.sh')
        if not os.path.exists(script):
            raise RunnerCheckError("Cannot find dash_client.sh.")

        bash = util.which('bash')
        if not bash:
            raise RunnerCheckError("Dash client requires a Bash shell.")

        return "{bash} {script} -l {length} -u '{url}' -H {host}".format(
                bash=bash,
                script=script,
                length=length,
                url=url,
                host=host)


class IperfCsvRunner(ProcessRunner):
    """Runner for iperf csv output (-y C), possibly with unix timestamp patch."""

    transformed_metadata = ('MEAN_VALUE',)

    def __init__(self, host, interval, length, ip_version, local_bind=None,
                 no_delay=False, udp=False, bw=None, pktsize=None, marking=None,
                 **kwargs):
        self.host = normalise_host(host)
        self.interval = interval
        self.length = length
        self.ip_version = ip_version
        self.local_bind = local_bind
        self.no_delay = no_delay
        self.udp = udp
        self.bw = bw
        self.pktsize = pktsize
        self.marking = marking
        super(IperfCsvRunner, self).__init__(**kwargs)

    def parse(self, output, error):
        result = []
        raw_values = []
        metadata = {}
        dest = None
        last_res = last_rw = None
        for line in output:
            parts = line.split(",")
            if len(parts) < 9:
                continue

            # Skip the header line in recent versions of iperf2
            if parts[0] == "time":
                continue

            # Newer versions of iperf2 have a timezone in front of the timestamp
            subpart = parts[0].split(":")
            if len(subpart) > 1:
                parts[0] = subpart[1]

            # Add the result of the last line to the array; this skips the last
            # entry, which is an average for the whole test, and is handled
            # below
            if last_res is not None:
                result.append(last_res)
                raw_values.append(last_rw)

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
                val = transformers.bits_to_mbits(float(bandwidth))
                last_res = [timestamp, val]
                last_rw = {'t': timestamp, 'val': val}
            except ValueError:
                pass

        # Handle last entry
        # src and dest should be reversed if this was a reply from the
        # server. Track this for UDP where it may be missing.
        if parts[1] == dest or not self.udp:
            metadata['MEAN_VALUE'] = last_res[1]
        else:
            metadata['MEAN_VALUE'] = None

        return result, raw_values, metadata

    def check(self):
        local_bind = self.local_bind
        if not self.local_bind and self.settings.LOCAL_BIND:
            local_bind = self.settings.LOCAL_BIND[0]

        self.command = self.find_binary(self.host, self.interval, self.length,
                                        self.ip_version,
                                        local_bind=local_bind,
                                        no_delay=self.no_delay,
                                        udp=self.udp,
                                        bw=self.bw,
                                        pktsize=self.pktsize,
                                        marking=self.marking)
        super(IperfCsvRunner, self).check()

    def find_binary(self, host, interval, length, ip_version, local_bind=None,
                    no_delay=False, udp=False, bw=None, pktsize=None,
                    marking=None):
        iperf = util.which('iperf', remote_host=self.remote_host)

        if iperf is not None:
            out, err = self.run_simple([iperf, '-h'])

            # The iperf flag --enhancedreports was deprecated in 2.0.14a and replaced
            # by --enhanced
            enhanced = None
            if "--enhanced" in out or err:
                enhanced = "--enhanced"
            elif "--enhancedreports" in err:
                enhanced = "--enhancedreports"

            if enhanced:
                if udp:
                    udp_args = "--udp --bandwidth {}".format(bw if bw else "100M")
                    if pktsize:
                        udp_args = "{} --len {}".format(udp_args, pktsize)
                else:
                    udp_args = ""
                return "{binary} {enhanced} --reportstyle C --format m " \
                    "--client {host} --time {length} --interval {interval} " \
                    "{local_bind} {no_delay} {udp} {marking} {ip6}".format(
                        host=host,
                        binary=iperf,
                        enhanced=enhanced,
                        length=length,
                        interval=interval,
                        # --help output is wrong
                        ip6="--ipv6_domain" if ip_version == 6 else "",
                        local_bind="--bind {0}".format(
                            local_bind) if local_bind else "",
                        no_delay="--nodelay" if no_delay else "",
                        marking=self.parse_marking(marking, "--tos {}"),
                        udp=udp_args)
            out, err = self.run_simple([iperf, '-v'])

            logger.warning(
                "Found iperf binary (%s), but it does not have "
                "either an --enhanced nor --enhancedreports option. Not using.", err.strip())

        raise RunnerCheckError("No suitable Iperf binary found.")


class IrttRunner(ProcessRunner):

    _irtt = {}

    def __init__(self, host, length, interval=None, ip_version=None,
                 local_bind=None, marking=None, multi_results=False,
                 sample_freq=0, data_size=None, **kwargs):
        self.host = normalise_host(host, bracket_v6=True)
        self.interval = interval
        self.length = length
        self.ip_version = ip_version
        self.local_bind = local_bind
        self.marking = marking
        self.multi_results = multi_results
        self.sample_freq = sample_freq
        self.data_size = data_size
        super(IrttRunner, self).__init__(**kwargs)

    # irtt outputs all durations in nanoseconds
    def _to_ms(self, value):
        return value / 10**6

    def _to_s(self, value):
        return value / 10**9

    def parse(self, output, error):
        result = {'rtt': [], 'delay': [], 'jitter': [], 'loss': []}
        raw_values = []
        metadata = {}
        try:
            data = json.load(output)
        except ValueError as e:
            logger.warning("Unable to parse irtt JSON output: %s", e)
            return

        metadata['RTT_MEAN'] = self._to_ms(data['stats']['rtt']['mean'])
        metadata['RTT_MEDIAN'] = self._to_ms(data['stats']['rtt']['median'])
        metadata['RTT_MAX'] = self._to_ms(data['stats']['rtt']['max'])
        metadata['RTT_MIN'] = self._to_ms(data['stats']['rtt']['min'])

        metadata['OWD_UP_MEAN'] = self._to_ms(
            data['stats']['send_delay']['mean'])
        metadata['OWD_DOWN_MEAN'] = self._to_ms(
            data['stats']['receive_delay']['mean'])
        metadata['IPDV_MEAN'] = self._to_ms(
            data['stats']['ipdv_round_trip']['mean'])
        metadata['IPDV_UP_MEAN'] = self._to_ms(
            data['stats']['ipdv_send']['mean'])
        metadata['IPDV_DOWN_MEAN'] = self._to_ms(
            data['stats']['ipdv_receive']['mean'])

        metadata['MEAN_VALUE'] = metadata['RTT_MEAN']
        metadata['PACKETS_SENT'] = data['stats']['packets_sent']
        metadata['PACKETS_RECEIVED'] = data['stats']['packets_received']
        metadata['PACKET_LOSS_RATE'] = (data['stats']['packet_loss_percent']
                                             / 100.0)
        metadata['SEND_RATE'] = data['stats']['send_rate']['bps'] / 10**6
        metadata['RECEIVE_RATE'] = (data['stats']['receive_rate']['bps']
                                         / 10**6)

        next_sample = 0
        lost = 0
        for pkt in data['round_trips']:
            try:
                dp = {'seq': pkt['seqno']}
                if pkt['lost'] == 'false':
                    dp['t'] = self._to_s(
                        pkt['timestamps']['client']['receive']['wall'])

                    dp['val'] = self._to_ms(pkt['delay']['rtt'])
                    dp['owd_up'] = self._to_ms(pkt['delay']['send'])
                    dp['owd_down'] = self._to_ms(pkt['delay']['receive'])

                    try:
                        dp['ipdv_up'] = self._to_ms(pkt['ipdv']['send'])
                        dp['ipdv_down'] = self._to_ms(pkt['ipdv']['receive'])
                        dp['ipdv'] = self._to_ms(pkt['ipdv']['rtt'])
                    except KeyError:
                        pass

                    if dp['t'] >= next_sample:
                        result['rtt'].append([dp['t'], dp['val']])
                        # delay and jitter are for compatibility with the D-ITG
                        # VoIP mode
                        result['delay'].append([dp['t'], dp['owd_up']])
                        result['jitter'].append([dp['t'],
                                                 abs(dp.get('ipdv_up', 0))])
                        result['loss'].append([dp['t'], lost])
                        lost = 0
                        next_sample = dp['t'] + self.sample_freq
                else:
                    lost_dir = pkt['lost'].replace('true_', '')
                    dp['lost'] = True
                    dp['lost_dir'] = lost_dir or None
                    dp['t'] = self._to_s(
                        pkt['timestamps']['client']['send']['wall'])
                    lost += 1

                raw_values.append(dp)
            except KeyError as e:
                logger.warning("Missing expected key in irtt output: %s",
                               e, extra={'output': str(pkt)})
                continue

        if not self.multi_results:
            result = result['rtt']
        return result, raw_values, metadata

    def check(self):

        if self.local_bind:
            local_bind = "--local={}".format(self.local_bind)
        elif self.settings.LOCAL_BIND:
            local_bind = "--local={}".format(self.settings.LOCAL_BIND[0])
        else:
            local_bind = ""

        ip_version = self.ip_version or self.settings.IP_VERSION
        if ip_version is not None:
            ip_version = "-{}".format(ip_version)
        else:
            ip_version = ""

        if not self._irtt:
            irtt = util.which('irtt', fail=RunnerCheckError, remote_host=self.remote_host)

            out, err = self.run_simple([irtt, 'help', 'client'])
            if re.search(r'--[a-z]', out) is None:
                raise RunnerCheckError("%s is too old to support gnu style args. "
                                       "Please upgrade to irtt v0.9+." % irtt)

            args = [irtt, 'client', '-n', '-Q',
                    '--timeouts=200ms,300ms,400ms']

            if local_bind:
                args.append(local_bind)

            if ip_version:
                args.append(ip_version)

            args.append(self.host)

            out, err = self.run_simple(args,
                                       errmsg="Irtt connection check failed: {err}")

            self._irtt['binary'] = irtt
        else:
            irtt = self._irtt['binary']

        if self.data_size is not None:
            data_size = "-l {}".format(self.data_size)
        else:
            data_size = ""

        if self.settings.IRTT_INTERVAL:
            interval = "{}ms".format(self.settings.IRTT_INTERVAL)
        else:
            interval = "{}s".format(self.interval or self.settings.STEP_SIZE)

        self.command = "{binary} client -o - --fill=rand -Q " \
                       "-d {length}s -i {interval} {ip_version} {marking} " \
                       "{local_bind} {data_size} {host}".format(
                           binary=irtt,
                           length=self.length,
                           interval=interval,
                           host=self.host,
                           ip_version=ip_version,
                           local_bind=local_bind,
                           data_size=data_size,
                           marking=self.parse_marking(self.marking, "--dscp={}"))

        self.units = 'ms'
        super(IrttRunner, self).check()


class UdpRttRunner(DelegatingRunner):

    def check(self):
        try:
            self.add_child(IrttRunner, **self.runner_args)
            self.debug("Using irtt")
        except RunnerCheckError as e:
            self.debug("Cannot use irtt runner (%s). Using netperf UDP_RR", e)
            self.add_child(NetperfDemoRunner,
                           **dict(self.runner_args, test='UDP_RR'))

        super(UdpRttRunner, self).check()


class VoipRunner(DelegatingRunner):

    def check(self):
        try:
            self.add_child(IrttRunner,
                           **dict(self.runner_args,
                                  multi_results=True,
                                  sample_freq=self.runner_args['interval'],
                                  # interval and data size to emulate G711 VoIP
                                  # ref.: https://wiki.wireshark.org/SampleCaptures?action=AttachFile&do=get&target=SIP_CALL_RTP_G711
                                  interval=0.02,
                                  data_size=172))
            self.debug("Using irtt")
        except RunnerCheckError as e:
            self.debug("Cannot use irtt runner (%s). Using D-ITG", e)
            self.add_child(DitgRunner,
                           **dict(self.runner_args, test_args='VoIP'))

        super(VoipRunner, self).check()


class SsRunner(ProcessRunner):
    """Runner for iterated `ss -t -i -p`. Depends on same partitial output
    separationa and time stamping as TcRunner."""

    # Keep track of runners to avoid duplicates (relies on this being a class
    # variable, and so the same dictionary instance across all instances of the
    # class).
    _duplicate_map = {}

    ip_v4_addr_sub_re = r"([0-9]{1,3}\.){3}[0-9]{1,3}(:\d+)"
    # ref.: to commented, untinkered version: ISBN 978-0-596-52068-7
    ip_v6_addr_sub_re = r"\[?(?:(?:[A-F0-9]{1,4}:){7}[A-F0-9]{1,4}|" \
                        r"(?=(?:[A-F0-9]{0,4}:){0,7}[A-F0-9]{0,4})" \
                        r"(([0-9A-F]{1,4}:){1,7}|:)((:[0-9A-F]{1,4})" \
                        r"{1,7}|:))\]?(:\d+)"

    time_re = re.compile(r"^Time: (?P<timestamp>\d+\.\d+)", re.MULTILINE)
    pid_re = re.compile(r"pid=(?P<pid>\d+)", re.MULTILINE)
    ports_ipv4_re = re.compile(r"" + "(?P<src_p>" + ip_v4_addr_sub_re + ")" +
                               r"\s+" + "(?P<dst_p>" + ip_v4_addr_sub_re + ")")
    ports_ipv6_re = re.compile(r"" + "(?P<src_p>" + ip_v6_addr_sub_re + ")" +
                               r"\s+" + "(?P<dst_p>" + ip_v6_addr_sub_re + ")",
                               re.IGNORECASE)
    ss_header_re = re.compile(r"" + r"State\s+Recv-Q\s+Send-Q\s+Local")

    data_res = [re.compile(r"cwnd:(?P<cwnd>\d+)", re.MULTILINE),
                re.compile(r"rtt:(?P<rtt>\d+\.\d+)/(?P<rtt_var>\d+\.\d+)",
                           re.MULTILINE),
                re.compile(r"pacing_rate (?P<pacing_rate>\d+(\.\d+)?[MK]?bps)",
                           re.MULTILINE),
                re.compile(r"delivery_rate (?P<delivery_rate>\d+(\.\d+)?[MK]?bps)",
                           re.MULTILINE),
                re.compile(r"bbr:\(bw:(?P<bbr_bw>\d+(\.\d+)?[MK]?bps),"
                           r"mrtt:(?P<bbr_mrtt>\d+\.\d+),"
                           r"pacing_gain:(?P<bbr_pacing_gain>\d+(\.\d+)?),"
                           r"cwnd_gain:(?P<bbr_cwnd_gain>\d+(\.\d+)?)\)",
                           re.MULTILINE)]

    src_p = []
    dst_p = []
    # ref.: upstream ss
    ss_states = ["UNKNOWN", "ESTAB", "SYN-SENT", "SYN-RECV", "FIN-WAIT-1",
                 "FIN-WAIT-2", "TIME-WAIT", "UNCONN", "CLOSE-WAIT", "LAST-ACK",
                 "LISTEN", "CLOSING"]
    ss_states_re = re.compile(r"|".join(ss_states))

    silent = True

    def __init__(self, exclude_ports, ip_version, host, interval,
                 length, target, **kwargs):
        self.exclude_ports = exclude_ports
        self.ip_version = ip_version
        self.host = normalise_host(host)
        self.interval = interval
        self.length = length
        self.target = target
        self.is_dup = False
        self._dup_key = None
        self._parsed_parts = None
        self._dup_runner = None
        super(SsRunner, self).__init__(**kwargs)

    def fork(self):
        if self._dup_runner is None:
            self.debug("Active runner for dup key %s: forking", self._dup_key)
            return super().fork()
        else:
            self.debug("Duplicate for dup key %s. Not forking", self._dup_key)
            return 0

    def run(self):
        if self._dup_runner is None:
            super(SsRunner, self).run()
            del self._duplicate_map[self._dup_key]
            return

        self._dup_runner.join()

    def filter_np_parent(self, part):
        parsed_parts = []
        sub_parts = self.ss_states_re.split(part)
        sub_parts = [sp for sp in sub_parts if sp.strip()
                     and not self.ss_header_re.search(sp)]

        for sp in sub_parts:
            # Filter out stats from netserver when it's run along with ss
            if "netserver" in sp:
                continue

            pid = self.pid_re.search(sp)
            if None is pid:
                continue
            pid_str = pid.group('pid')

            f_ports = self.ports_ipv4_re.search(sp)
            if None is f_ports:
                f_ports = self.ports_ipv6_re.search(sp)

            if None is f_ports:
                raise ParseError()

            dst_p = int(f_ports.group('dst_p').split(":")[-1])

            parsed_parts.append({'dst_p': dst_p, 'sp': sp, 'pid': pid_str})

        return parsed_parts

    def parse_val(self, val):
        if val.endswith("Mbps"):
            return float(val[:-4])
        if val.endswith("Kbps"):
            return float(val[:-4]) / 1000
        if val.endswith("bps"):
            return float(val[:-3]) / 10**6
        return float(val)

    def parse_subpart(self, sub_part):
        vals = {}
        for r in self.data_res:
            m = r.search(sub_part)
            if m is not None:
                d = m.groupdict()
                for k, v in d.items():
                    try:
                        vals['tcp_%s' % k] = self.parse_val(v)
                    except ValueError:
                        pass
        return vals

    def parse_part(self, part):
        sub_parts = self.filter_np_parent(part)

        timestamp = self.time_re.search(part)
        if timestamp is None:
            raise ParseError()
        timestamp = float(timestamp.group('timestamp'))

        vals = []
        for sp in sub_parts:
            v = self.parse_subpart(sp['sp'])
            if not v:
                continue
            v.update({'t': timestamp,
                      'dst_p': sp['dst_p'],
                      'pid': sp['pid']})
            vals.append(v)

        return vals

    def do_parse(self, pool):
        if not self.is_dup:
            return super().do_parse(pool)
        return []

    def parse(self, output, error):
        parsed_parts = []
        for part in self.split_stream(output):
            try:
                parsed_parts.extend(self.parse_part(part))
            except ParseError:
                pass

        # we return an empty result and store the parsed data in metadata, so we
        # can retrieve it later
        return [], [], {'parsed_parts': parsed_parts}

    @property
    def parsed_parts(self):
        if self.is_dup:
            return self._dup_runner.parsed_parts
        if self._parsed_parts is None:
            self._parsed_parts = self.metadata.pop('parsed_parts', [])
        return self._parsed_parts

    def post_parse(self):
        par_pid = str(self._parent.pid)
        results = {}
        raw_values = []

        for res_dict in self.parsed_parts:
            if res_dict['pid'] != par_pid or res_dict['dst_p'] in self.exclude_ports:
                continue
            t = res_dict['t']
            for k, v in res_dict.items():
                if k in ('t', 'pid', 'dst_p'):
                    continue
                if k not in results:
                    results[k] = [[t, v]]
                else:
                    results[k].append([t, v])
            rw = res_dict.copy()
            del rw['pid']
            del rw['dst_p']
            raw_values.append(rw)

        if not results:
            extra = {'runner': self} if not self.is_dup else None
            logger.warning("%s%s: Found no results for pid %s",
                           self.__class__.__name__,
                           "(dup)" if self.is_dup else "",
                           par_pid, extra=extra)
        self.result = results
        self.raw_values = raw_values

    def check(self):
        dup_key = (self.host, self.interval, self.length, self.target,
                   self.ip_version, tuple(self.exclude_ports))

        if dup_key in self._duplicate_map:
            self.debug("Found duplicate runner (%s), reusing output", dup_key)
            self._dup_runner = self._duplicate_map[dup_key]
            self.is_dup = True
            self.command = "%s (duplicate)" % self._dup_runner.command
        else:
            self.debug("Starting new runner (dup key %s)", dup_key)
            self._dup_runner = None
            self._duplicate_map[dup_key] = self
            self.command = self.find_binary(self.ip_version, self.host,
                                            self.interval, self.length,
                                            self.target)
            self.watchdog_timer = self.delay + self.length + 5

        self._dup_key = dup_key
        super(SsRunner, self).check()

    def find_binary(self, ip_version, host, interval, length, target):
        script = os.path.join(DATA_DIR, 'scripts', 'ss_iterate.sh')
        if not os.path.exists(script):
            raise RunnerCheckError("Cannot find ss_iterate.sh.")

        bash = util.which('bash')
        if not bash:
            raise RunnerCheckError("Socket stats requires a Bash shell.")

        resol_target = util.lookup_host(target, ip_version)[4][0]
        if ip_version == 6:
            resol_target = "[" + str(resol_target) + "]"

        filt = ""
        for p in self.exclude_ports:
            filt = "{} and dport != {}".format(filt, p)

        return "{bash} {script} -I {interval:.2f} " \
            "-l {length} -H {host} -t '{target}' -f '{filt}'".format(
                bash=bash,
                script=script,
                interval=interval,
                length=length,
                host=host,
                target=resol_target,
                filt=filt)


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

        # fq_pie
        re.compile(r"pkts_in (?P<pkts_in>\d+) "
                   r"overlimit (?P<overlimit_pie>\d+) "
                   r"overmemory (?P<overmemory>\d+) "
                   r"dropped (?P<dropped_pie>\d+) "
                   r"ecn_mark (?P<ecn_mark>\d+)"),
        re.compile(r"new_flow_count (?P<new_flow_count>\d+) "
                   r"new_flows_len (?P<new_flows_len>\d+) "
                   r"old_flows_len (?P<old_flows_len>\d+) "
                   r"memory_used (?P<memory_used>\d+)"),
    ]

    cake_tin_re = r"(Tin \d|Bulk|Best Effort|Video|Voice)"
    cake_alltins_re = re.compile(r"(\s*" + cake_tin_re + r")+")
    cake_1tin_re = re.compile(cake_tin_re)
    cake_keys = ["av_delay", "sp_delay", "pkts", "bytes",
                 "drops", "marks", "sp_flows", "bk_flows", "max_len"]
    cumulative_keys = ["dropped", "ecn_mark"]

    def __init__(self, interface, interval, length, host='localhost', **kwargs):
        self.interface = interface
        self.interval = interval
        self.length = length
        self.host = normalise_host(host)
        super(TcRunner, self).__init__(**kwargs)

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

    def parse(self, output, error):
        results = {}
        raw_values = []
        metadata = {}
        last_vals = {}
        for part in self.split_stream(output):
            timestamp = self.time_re.search(part)
            if timestamp is None:
                continue
            timestamp = float(timestamp.group('timestamp'))

            # Split out individual qdisc entries (in case there are more than
            # one). If so, discard the root qdisc and sum the rest.
            qdiscs = [i for i in self.split_re.split(part)
                      if not i.startswith("ingress")]
            if len(qdiscs) > 2:
                part = "qdisc ".join([i for i in qdiscs
                                      if 'root' not in i])

            matches = {}

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
                        r"^  %s(:?\s*([0-9\.kmbitus]+)){%d}\s*$" % (key,
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

            # Transform cumulative keys into events per interval
            for k in self.cumulative_keys:
                if k not in matches:
                    continue
                v = matches[k]
                matches[k] = v - last_vals[k] if k in last_vals else 0.0
                last_vals[k] = v

            for k, v in matches.items():
                if not isinstance(v, float):
                    continue
                if k not in results:
                    results[k] = [[timestamp, v]]
                else:
                    results[k].append([timestamp, v])
            matches['t'] = timestamp
            raw_values.append(matches)
        return results, raw_values, metadata

    def check(self):
        self.command = self.find_binary(self.interface, self.interval,
                                        self.length, self.host)
        super(TcRunner, self).check()

    def find_binary(self, interface, interval, length, host='localhost'):
        script = os.path.join(DATA_DIR, 'scripts', 'tc_iterate.sh')
        if not os.path.exists(script):
            raise RunnerCheckError("Cannot find tc_iterate.sh.")

        bash = util.which('bash')
        if not bash:
            raise RunnerCheckError("TC stats requires a Bash shell.")

        if interface is None:
            logger.warning(
                "Warning: No interface given for tc runner. "
                "Defaulting to 'eth0'.")
            interface = 'eth0'

        return "{bash} {script} -i {interface} -I {interval:.2f} " \
            "-c {count:.0f} -l {length} -H {host}".format(
                bash=bash,
                script=script,
                interface=interface,
                interval=interval,
                count=length // interval + 1,
                length=length,
                host=host)


class CpuStatsRunner(ProcessRunner):
    """Runner for getting CPU usage stats from /proc/stat. Expects iterations to be
    separated by '\n---\n and a timestamp to be present in the form 'Time:
    xxxxxx.xxx' (e.g. the output of `date '+Time: %s.%N'`).

    The first line is the total CPU load, and the following lines are the load of
    each core.
    """

    time_re = re.compile(r"^Time: (?P<timestamp>\d+\.\d+)", re.MULTILINE)
    value_re = re.compile(r"^cpu(?P<core_nr>\d+)?: (?P<load>\d+\.\d+)", re.MULTILINE)

    def __init__(self, interval, length, host='localhost', **kwargs):
        self.interval = interval
        self.length = length
        self.host = normalise_host(host)
        super(CpuStatsRunner, self).__init__(**kwargs)

    def parse(self, output, error):
        results = {}
        raw_values = []
        metadata = {}
        for part in self.split_stream(output):
            timestamp = self.time_re.search(part)
            if timestamp is None:
                continue
            timestamp = float(timestamp.group('timestamp'))
            value = self.value_re.search(part)

            if value is None:
                continue

            matches = {}

            for m in self.value_re.finditer(part):
                core_nr = m.group("core_nr")
                load = m.group("load")
                k = f'cpu{core_nr}' if core_nr is not None else 'load'
                v = float(load)
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
            raw_values.append(matches)
        return results, raw_values, metadata

    def check(self):
        self.command = self.find_binary(self.interval,
                                        self.length, self.host)
        super(CpuStatsRunner, self).check()

    def find_binary(self, interval, length, host='localhost'):
        script = os.path.join(DATA_DIR, 'scripts', 'stat_iterate.sh')
        if not os.path.exists(script):
            raise RunnerCheckError("Cannot find stat_iterate.sh.")

        bash = util.which('bash')
        if not bash:
            raise RunnerCheckError("CPU stats requires a Bash shell.")

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

    def __init__(self, interface, interval, length,
                 host='localhost', stations=None, **kwargs):

        self.interface = interface
        self.interval = interval
        self.length = length
        self.host = normalise_host(host)

        self.stations = stations or []
        if self.stations in (["all"], ["ALL"]):
            self.stations = []
        # disabled as it doesn't work properly yet
        self.all_stations = False

        super(WifiStatsRunner, self).__init__(**kwargs)

    def parse(self, output, error):
        results = {}
        raw_values = []
        metadata = {}
        last_airtime = {}
        for part in self.split_stream(output):
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
                    rx = float(airtime.group('rx'))
                    tx = float(airtime.group('tx'))
                    if s not in last_airtime:
                        last_airtime[s] = {'rx': rx, 'tx': tx}
                        sv['airtime_rx'] = sv['airtime_tx'] = 0.0
                    else:
                        sv['airtime_rx'] = rx - last_airtime[s]['rx']
                        sv['airtime_tx'] = tx - last_airtime[s]['tx']
                        last_airtime[s]['rx'] = rx
                        last_airtime[s]['tx'] = tx

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
            raw_values.append(matches)

        if self.all_stations:
            metadata['test_parameters'] = {'wifi_stats_stations': ",".join(self.stations)}
        return results, raw_values, metadata

    def post_parse(self):
        self.test_parameters = self.metadata.pop('test_parameters', {})
        super().post_parse()

    def check(self):
        self.command = self.find_binary(self.interface, self.interval,
                                        self.length, self.host)
        super(WifiStatsRunner, self).check()

    def find_binary(self, interface, interval, length, host='localhost'):
        script = os.path.join(DATA_DIR, 'scripts', 'wifistats_iterate.sh')
        if not os.path.exists(script):
            raise RunnerCheckError("Cannot find wifistats_iterate.sh.")

        bash = util.which('bash')
        if not bash:
            raise RunnerCheckError("WiFi stats requires a Bash shell.")

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

    def __init__(self, interval, length, host='localhost', **kwargs):
        self.interval = interval
        self.length = length
        self.host = normalise_host(host)
        super(NetstatRunner, self).__init__(**kwargs)

    def parse(self, output, error):
        results = {}
        raw_values = []
        metadata = {}
        for part in self.split_stream(output):
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
            raw_values.append(matches)
        return results, raw_values, metadata

    def check(self):
        self.command = self.find_binary(self.interval,
                                        self.length, self.host)
        super(NetstatRunner, self).check()

    def find_binary(self, interval, length, host='localhost'):
        script = os.path.join(DATA_DIR, 'scripts', 'netstat_iterate.sh')
        if not os.path.exists(script):
            raise RunnerCheckError("Cannot find netstat_iterate.sh.")

        bash = util.which('bash')
        if not bash:
            raise RunnerCheckError("Capturing netstat requires a Bash shell.")

        return "{bash} {script} -I {interval:.2f} -c {count:.0f} " \
            "-H {host}".format(
                bash=bash,
                script=script,
                interval=interval,
                count=length // interval + 1,
                host=host)


class CommandOutputRunner(ProcessRunner):
    """Runner for executing a user-defined command with an interval. The command
    should output a single numeric value on a separate line. It will be run by
    the cmd_iterate.sh script, which adds the same timestamp format and
    separator as the other scripts. Which means that the parser expects
    iterations to be separated by '\n---\n and a timestamp to be present in the
    form 'Time: xxxxxx.xxx' (e.g. the output of `date '+Time: %s.%N'`).

    """
    time_re = re.compile(r"^Time: (?P<timestamp>\d+\.\d+)", re.MULTILINE)
    value_re = re.compile(r"^\s*(?P<value>\d+(\.\d+)?)\s*\n",
                          re.MULTILINE)

    def __init__(self, interval, length, user_command, host='localhost', **kwargs):
        self.interval = interval
        self.length = length
        self.user_command = user_command
        self.host = normalise_host(host)
        super().__init__(**kwargs)

    def parse(self, output, error):
        results = []
        raw_values = []
        metadata = {}
        for part in self.split_stream(output):
            timestamp = self.time_re.search(part)
            if timestamp is None:
                continue
            timestamp = float(timestamp.group('timestamp'))

            value = self.value_re.search(part)
            if value is None:
                continue
            value = float(value.group("value"))

            raw_values.append({'t': timestamp,
                               'value': value})
            results.append([timestamp, value])

        return results, raw_values, metadata

    def check(self):
        self.command = self.find_binary(self.interval,
                                        self.length,
                                        self.user_command,
                                        self.host)
        super().check()

    def find_binary(self, interval, length, user_command, host='localhost'):
        script = os.path.join(DATA_DIR, 'scripts', 'cmd_iterate.sh')
        if not os.path.exists(script):
            raise RunnerCheckError("Cannot find cmd_iterate.sh.")

        bash = util.which('bash')
        if not bash:
            raise RunnerCheckError("Capturing command output requires a Bash shell.")

        return f"{bash} {script} -I {interval:.2f} -l {length:.2f} " \
            f"-H {host} -C '{user_command}'"


class MosquittoSubRunner(ProcessRunner):
    """Runner for connecting to an MQTT broker using the mosquitto_sub binary
    from the Eclipse mosquitto software suite. It relies on the '%J' output
    format to get a timestamp and payload in JSON format, which means that the
    payload of the subscribed topic also has to be in JSON format.
    """

    supports_remote = False # can't do the config file trick remotely
    success_return = [0, 27] # 27 is timeout waiting for message

    def __init__(self, length, mqtt_topic, mqtt_host, mqtt_port=8883,
                 mqtt_user=None, mqtt_pass=None, payload_key=None, **kwargs):
        self.length = length
        self.mqtt_topic = mqtt_topic
        self.mqtt_host = normalise_host(mqtt_host)
        self.mqtt_port = mqtt_port
        self.mqtt_user = mqtt_user
        self.mqtt_pass = mqtt_pass
        self.payload_key = payload_key
        self._env = {} # separate copy per instance
        self.config_dir = None

        super().__init__(**kwargs)

    def parse(self, output, error):
        results = []
        raw_values = []
        metadata = {}
        for line in output:

            try:
                js = json.loads(line)

                timestamp = datetime.fromisoformat(js['tst']).timestamp()
                pl = js['payload']
                if self.payload_key:
                    value = pl[self.payload_key]
                else:
                    value = pl

                raw_values.append({'t': timestamp,
                                   'value': value})
                results.append([timestamp, value])

            except json.decoder.JSONDecodeError:
                continue

        return results, raw_values, metadata

    def cleanup(self):
        if self.config_dir is not None:
            self.debug("Cleaning up temporary directory %s", self.config_dir.name)
            self.config_dir.cleanup()
            self.config_dir = None

    def check(self):
        self.command = self.find_binary(self.length,
                                        self.mqtt_topic,
                                        self.mqtt_host,
                                        self.mqtt_port,
                                        self.mqtt_user)

        if self.mqtt_pass is not None and self.config_dir is None:
            # We don't want to pass the password on the command line, so create
            # a confiruration file with the password option

            try:
                tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
                fname = os.path.join(tmpdir.name, "mosquitto_sub")

                with open(fname, "w") as fp:
                    fp.write(f"--pw {self.mqtt_pass}\n")

                self.debug("Wrote mosquitto_sub config file to %s", fname)

                self.config_dir = tmpdir
                self._env['XDG_CONFIG_HOME'] = tmpdir.name
            except IOError as e:
                raise RuntimeError("Couldn't write mosquitto config file: %s", e)

        super().check()

    def find_binary(self, length, mqtt_topic, mqtt_host, mqtt_port, mqtt_user):
        sub = util.which('mosquitto_sub')
        if not sub:
            raise RunnerCheckError("Can't find mosquitto_sub binary.")

        if mqtt_user is not None:
            mqtt_user = f"-u '{mqtt_user}'"
        else:
            mqtt_user = ""

        return f"{sub} -F '%J' -R -W {length} -h {mqtt_host} -p {mqtt_port} "\
            f"-t '{mqtt_topic}' {mqtt_user}"


class StressNgRunner(RegexpRunner):
    """Runner for executing stress-ng as a CPU stressor and capture the number
    of runners being executed over time.

    """

    regexes = [re.compile(r"stress-ng: (?P<t>([0-9]{2}:){2}[0-9]{2}\.[0-9]{2}).*"
                          r"\sstatus: (?P<val>\d+) run\s*")]
    metadata_regexes = [re.compile(r"stress-ng:.*C0\s+(?P<CSTATE_C0>\d+\.\d+)%$"),
                        re.compile(r"stress-ng:.*C1\s+(?P<CSTATE_C1>\d+\.\d+)%$"),
                        re.compile(r"stress-ng:.*C1\s+(?P<CSTATE_C1>\d+\.\d+)%$"),
                        re.compile(r"stress-ng:.*C1E\s+(?P<CSTATE_C1E>\d+\.\d+)%$"),
                        re.compile(r"stress-ng:.*C2\s+(?P<CSTATE_C2>\d+\.\d+)%$"),
                        re.compile(r"stress-ng:.*C3\s+(?P<CSTATE_C3>\d+\.\d+)%$"),
                        re.compile(r"stress-ng:.*C4\s+(?P<CSTATE_C4>\d+\.\d+)%$"),
                        re.compile(r"stress-ng:.*C5\s+(?P<CSTATE_C5>\d+\.\d+)%$"),
                        re.compile(r"stress-ng:.*C6\s+(?P<CSTATE_C6>\d+\.\d+)%$"),
                        re.compile(r"stress-ng:.*POLL\s+(?P<CSTATE_POLL>\d+\.\d+)%$")]

    def parse_stressng_timestamp(tstamp):
        sec, mil = tstamp.split(".")
        dt = datetime.strptime(sec, "%H:%M:%S")
        n = datetime.now()
        dt = dt.replace(year=n.year, month=n.month, day=n.day)
        timestamp = dt.timestamp() + float("0." + mil)
        return timestamp

    transformers = {'t': parse_stressng_timestamp}

    def __init__(self, interval, length, n_stressors=1, cpu_load=100, **kwargs):
        self.interval = max(1, round(interval))
        self.length = length
        self.n_stressors = int(n_stressors)
        self.cpu_load = int(cpu_load)
        super().__init__(**kwargs)

    def check(self):
        self.command = self.find_binary(self.interval,
                                        self.length,
                                        self.n_stressors,
                                        self.cpu_load)
        super().check()

    def find_binary(self, interval, length, n_stressors, cpu_load):
        stress_ng = util.which('stress-ng', fail=RunnerCheckError,
                               remote_host=self.remote_host)

        if n_stressors < 1:
            raise RunnerCheckError("Number of CPU stressors must be at least one")

        return f"{stress_ng} -t {length} --status {interval} --timestamp --c-states " \
            f"--cpu {n_stressors} --cpu-load {cpu_load} --cpu-method int64 " \
            f"--taskset 0-{n_stressors-1}"


class NullRunner(RunnerBase):
    pass


class ComputingRunner(RunnerBase):
    command = "Computed"
    supported_meta = ['MEAN_VALUE']
    copied_meta = ['UNITS']

    def __init__(self, apply_to=None, post=False, **kwargs):
        super(ComputingRunner, self).__init__(**kwargs)
        if apply_to is None:
            self.keys = []
        else:
            self.keys = apply_to
        self.metadata['COMPUTED_LATE'] = post

    def compute_result(self, res):
        if not self.keys:
            return res

        new_res = []
        keys = Glob.expand_list(self.keys, res.series_names, [self.runner_name])

        for r in res.zipped(keys):
            values = [v for v in r[1:] if v is not None]
            if not values:
                new_res.append(None)
            else:
                new_res.append(self.compute(values))

        meta = res.meta('SERIES_META') if 'SERIES_META' in res.meta() else {}
        meta[self.runner_name] = self.metadata
        for mk in self.supported_meta:
            vals = []
            for k in keys:
                if k in meta and mk in meta[k] and meta[k][mk] is not None:
                    vals.append(meta[k][mk])
            if vals:
                try:
                    meta[self.runner_name][mk] = self.compute(vals)
                except TypeError:
                    meta[self.runner_name][mk] = None

        for mk in self.copied_meta:
            vals = []
            for k in keys:
                if k in meta and mk in meta[k]:
                    vals.append(meta[k][mk])
            if vals:
                # If all the source values of the copied metadata are the same,
                # just use that value, otherwise include all of them.
                meta[self.runner_name][mk] = vals if len(set(vals)) > 1 else vals[0]

        res.add_result(self.runner_name, new_res)
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
        super(SmoothAverageRunner, self).__init__(**kwargs)
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

    def compute_result(self, res):
        if not self.keys:
            return res

        key = self.keys[0]

        data = [i for i in res[key] if i is not None]
        if not data:
            res.add_result(self.runner_name, [None] * len(res[key]))
        else:
            min_val = min(data)
            res.add_result(
                self.runner_name, [i - min_val if i is not None else None
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
