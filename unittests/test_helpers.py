# -*- coding: utf-8 -*-
#
# test_helpers.py
#
# Author:   Toke Høiland-Jørgensen (toke@toke.dk)
# Date:      9 July 2019
# Copyright (c) 2019, Toke Høiland-Jørgensen
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

import io
import os
import sys
import warnings
import traceback
import unittest

from flent import resultset, loggers

try:
    import cPickle as pickle
except ImportError:
    import pickle

try:
    from tblib import pickling_support
    from six import reraise
    pickling_support.install()
    HAS_TBLIB = True
except ImportError:
    HAS_TBLIB = False


def setup_warnings():
    warnings.filterwarnings('ignore',
                            message="Matplotlib is building the font cache")
    warnings.simplefilter('error', append=True)
    loggers.reset_to_null()


def prefork(method):
    def new_method(*args, **kwargs):
        sys.stderr.flush()
        sys.stdout.flush()

        pipe_r, pipe_w = os.pipe()
        pid = os.fork()
        if pid:
            os.close(pipe_w)
            _, status = os.waitpid(pid, 0)
            if os.WIFSIGNALED(status):
                raise RuntimeError(f"Child terminated by signal {os.WTERMSIG(status)}")
            elif os.WIFSTOPPED(status):
                raise RuntimeError(f"Child stopped by signal {os.WSTOPSIG(status)}")
            elif not os.WIFEXITED(status):
                raise RuntimeError("Child did not exit correctly")

            ret = os.WEXITSTATUS(status)
            if ret != 0:
                raise RuntimeError(f"Child exited with status {ret}")

            res = pickle.loads(os.read(pipe_r, 65535))
            if HAS_TBLIB and isinstance(res, tuple) and isinstance(res[1],
                                                                   Exception):
                reraise(*res)
            if isinstance(res, Exception):
                raise res
            return res
        else:
            os.close(pipe_r)
            try:
                setup_warnings()
                res = method(*args, **kwargs)
                os.write(pipe_w, pickle.dumps(res))
            except Exception as e:
                if not hasattr(e, 'orig_tb'):
                    e.orig_tb = traceback.format_exc()
                if HAS_TBLIB:
                    os.write(pipe_w, pickle.dumps(sys.exc_info()))
                else:
                    os.write(pipe_w, pickle.dumps(e))
            finally:
                os.close(pipe_w)
                os._exit(0)
    return new_method

class StreamProxy(io.StringIO):
    def writeln(self, line):
        super().write(line + "\n")


class ProxyTestResult(unittest.TextTestResult):
    def __init__(self):
        super().__init__(stream=StreamProxy(), descriptions=True, verbosity=2)
        self.stream_output = ""

    def _exc_info_to_string(self, err, test):
        exctype, value, tb = err

        if hasattr(value, 'orig_tb'):
            return str(value) + ":\n\n" + value.orig_tb

        return super()._exc_info_to_string(err, test)

    def __getstate__(self):
        state = {}

        for k, v in self.__dict__.items():
            if not k.startswith("_") and k != 'stream':
                state[k] = v

        state['stream_output'] = self.stream.getvalue()

        return state

    def copy_to_parent(self, parent):
        if parent is None:
            return
        parent.errors.extend(self.errors)
        parent.failures.extend(self.failures)
        parent.skipped.extend(self.skipped)
        parent.expectedFailures.extend(self.expectedFailures)
        parent.unexpectedSuccesses.extend(self.unexpectedSuccesses)
        parent.testsRun += self.testsRun
        parent.stream.write(self.stream_output)
        parent.stream.flush()


class ForkingTestCase(unittest.TestCase):

    @prefork
    def _run(self):
        res = ProxyTestResult()
        super().run(res)
        return res

    def run(self, result):
        res = self._run()
        res.copy_to_parent(result)


def get_test_data_files():
    dirname = os.path.join(os.path.dirname(__file__), "test_data")
    for fname in os.listdir(dirname):
        if not fname.endswith(resultset.SUFFIX):
            continue
        yield os.path.join(dirname, fname)
