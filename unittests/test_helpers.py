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

import os
import sys
import warnings
import traceback

from flent import resultset

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


def prefork(method):
    def new_method(*args, **kwargs):
        pipe_r, pipe_w = os.pipe()
        pid = os.fork()
        if pid:
            os.close(pipe_w)
            os.waitpid(pid, 0)
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
                os._exit(0)
    return new_method


def get_test_data_files():
    dirname = os.path.join(os.path.dirname(__file__), "test_data")
    for fname in os.listdir(dirname):
        if not fname.endswith(resultset.SUFFIX):
            continue
        yield os.path.join(dirname, fname)
