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

from flent.util import Glob, token_split
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

# Test parameters that will be parsed and from test parameters and passed to the
# add_stream callback. In addition to these, 'stream_delay' is handled specially
# in the code below
STREAM_CONFIG_PARAM_NAMES = ['label', 'ping_label', 'marking',
                             'control_host', 'local_bind', 'cc_algo']

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
            'set_test_parameter': self.set_test_parameter,
            'get_test_parameter': self.get_test_parameter,
            'try_test_parameters': self.try_test_parameters,
            'parse_int': self.parse_int,
            'zip_longest': zip_longest,
            'for_stream_config': self.for_stream_config,
        })

        self.informational = informational
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

    def get_test_parameter(self, name, default=_no_default, split=False, cast=None):
        try:
            ret = self.env['TEST_PARAMETERS'][name]
            if split:
                ret = token_split(ret)
                if cast:
                    ret = list(map(cast, ret))
            elif cast:
                ret = cast(ret)
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
        except (ValueError, AttributeError):
            raise RuntimeError("Invalid integer value: %s" % val)

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

    def for_stream_config(self, func, n=None):
        if n is None:
            n = len(self.env['HOSTS'])

        config_params = {}
        for k in STREAM_CONFIG_PARAM_NAMES:
            config_params[k] = self.get_test_parameter(k+"s",
                                                       default=[],
                                                       split=True)

        stream_delays = self.get_test_parameter("stream_delays",
                                                default=[],
                                                split=True)
        global_delay = self.env['DELAY']
        total_length = self.env['TOTAL_LENGTH']
        stream_length = total_length-2*global_delay

        for i in range(n):
            kwargs = {}
            try:
                kwargs['host'] = self.env['HOSTS'][i]
            except IndexError:
                pass

            for k, v in config_params.items():
                try:
                    kwargs[k] = v[i]
                except IndexError:
                    pass

            try:
                kwargs['length'] = stream_length - int(stream_delays[i])
                kwargs['delay'] = global_delay + int(stream_delays[i])
            except IndexError:
                pass

            func(i, **kwargs)
