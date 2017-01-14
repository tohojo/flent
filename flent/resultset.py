# -*- coding: utf-8 -*-
#
# resultset.py
#
# Author:   Toke Høiland-Jørgensen (toke@toke.dk)
# Date:     24 November 2012
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

import math
import os
import re

from datetime import datetime
from calendar import timegm
from itertools import repeat
from copy import deepcopy
from collections import OrderedDict

from flent.loggers import get_logger
from flent.util import gzip_open, bz2_open, parse_date, format_date

try:
    import ujson as json
except ImportError:
    import json

logger = get_logger(__name__)

# Controls pretty-printing of json dumps
JSON_INDENT = 2

__all__ = ['new', 'load']

RECORDED_SETTINGS = (
    "NAME",
    "HOST",
    "HOSTS",
    "TIME",
    "LOCAL_HOST",
    "TITLE",
    "NOTE",
    "LENGTH",
    "TOTAL_LENGTH",
    "STEP_SIZE",
    "TEST_PARAMETERS",
    "FLENT_VERSION",
    "IP_VERSION",
    "BATCH_NAME",
    "BATCH_TIME",
    "BATCH_TITLE",
    "BATCH_UUID",
    "DATA_FILENAME",
    "HTTP_GETTER_URLLIST",
    "HTTP_GETTER_DNS",
    "HTTP_GETTER_WORKERS",
)

FILEFORMAT_VERSION = 3
SUFFIX = '.flent.gz'
MAX_FILENAME_LEN = 250  # most filesystems have 255 as their limit

# Time settings will be serialised as ISO timestamps and stored in memory as
# datetime instances
TIME_SETTINGS = ("TIME", "BATCH_TIME", "T0")

_EMPTY = object()


def new(settings):
    d = {}
    for a in RECORDED_SETTINGS:
        d[a] = deepcopy(getattr(settings, a, None))
    return ResultSet(**d)


def load(filename, absolute=False):
    return ResultSet.load_file(filename, absolute)


class ResultSet(object):

    def __init__(self, SUFFIX=SUFFIX, **kwargs):
        self._x_values = []
        self._results = OrderedDict()
        self._filename = None
        self._loaded_from = None
        self._absolute = False
        self._raw_values = {}
        self.metadata = kwargs
        self.SUFFIX = SUFFIX
        self.t0 = None
        if 'TIME' not in self.metadata or self.metadata['TIME'] is None:
            self.metadata['TIME'] = datetime.utcnow()
        if 'NAME' not in self.metadata or self.metadata['NAME'] is None:
            raise RuntimeError("Missing name for resultset")
        if 'DATA_FILENAME' not in self.metadata \
           or self.metadata['DATA_FILENAME'] is None:
            self.metadata['DATA_FILENAME'] = self.dump_filename
        if not self.metadata['DATA_FILENAME'].endswith(self.SUFFIX):
            self.metadata['DATA_FILENAME'] += self.SUFFIX
        self._filename = self.metadata['DATA_FILENAME']
        self._label = None

        if 'TITLE' in self.metadata and self.metadata['TITLE']:
            self.title = "%s - %s" % (self.metadata['NAME'],
                                      self.metadata['TITLE'])
            self.long_title = "%s - %s" % (self.title, format_date(
                self.metadata['TIME'], fmt="%Y-%m-%d %H:%M:%S"))
        else:
            self.title = "%s - %s" % (self.metadata['NAME'],
                                      format_date(self.metadata['TIME'],
                                                  fmt="%Y-%m-%d %H:%M:%S"))
            self.long_title = self.title

    def meta(self, key=None, value=_EMPTY):
        if key:
            if value is not _EMPTY:
                self.metadata[key] = value
            if key in self.metadata:
                return self.metadata[key]
            # Try to walk the metadata structure by the :-separated keys in 'key'.
            # This makes it possible to extract arbitrary metadata strings from
            # the structure.
            try:
                parts = key.split(":")
                data = self.metadata[parts[0]]
                parts = parts[1:]
                while parts:
                    k = parts.pop(0)
                    try:
                        i = int(k)
                        data = data[i]
                    except ValueError:
                        data = data[k]
                return data
            except (KeyError, IndexError, TypeError):
                raise KeyError
        return self.metadata

    def label(self):
        return self._label or self.metadata["TITLE"] \
            or format_date(self.metadata["TIME"])

    def set_label(self, label):
        self._label = label

    def get_x_values(self):
        return self._x_values

    def set_x_values(self, x_values):
        assert not self._x_values
        self._x_values = list(x_values)
    x_values = property(get_x_values, set_x_values)

    def add_result(self, name, data):
        assert len(data) == len(self._x_values)
        self._results[name] = data

    def add_raw_values(self, name, data):
        self._raw_values[name] = data

    def set_raw_values(self, raw_values):
        self._raw_values = raw_values

    def get_raw_values(self):
        return self._raw_values

    raw_values = property(get_raw_values, set_raw_values)

    def create_series(self, series_names):
        for n in series_names:
            self._results[n] = []

    def append_datapoint(self, x, data):
        """Append a datapoint to each series. Missing data results in append
        None (keeping all result series synchronised in x values).

        Requires preceding call to create_series() with the data series name(s).
        """
        data = dict(data)
        self._x_values.append(x)
        for k in list(self._results.keys()):
            if k in data:
                self._results[k].append(data[k])
                del data[k]
            else:
                self._results[k].append(None)

        if data:
            raise RuntimeError("Unexpected data point(s): %s" % list(data.keys()))

    def concatenate(self, res):
        if self._absolute:
            x0 = 0.0
            # When concatenating using absolute values, insert an empty data
            # point midway between the data series, to prevent the lines for
            # each distinct data series from being joined together.
            xnext = (self.x_values[-1] + res.x_values[0]) / 2.0
            self.append_datapoint(xnext, zip(res.series_names, repeat(None)))
        else:
            x0 = self.x_values[-1] + self.meta("STEP_SIZE")
        for point in res:
            x = point[0] + x0
            data = dict(zip(res.series_names, point[1:]))
            self.append_datapoint(x, data)

    def last_datapoint(self, series):
        data = self.series(series)
        if not data:
            return None
        return data[-1]

    def series(self, name, smooth=None):
        if name not in self._results:
            logger.warning("Missing data points for series '%s'", name)
            return [None] * len(self.x_values)
        if smooth:
            return self.smoothed(self._results[name], smooth)
        return self._results[name]

    def _calculate_t0(self):
        self.t0 = timegm(self.metadata['T0'].timetuple(
        )) + self.metadata['T0'].microsecond / 1000000.0

    def raw_series(self, name, smooth=None, absolute=False):
        if name not in self.raw_values:
            logger.warning("Missing data points for series '%s'", name)
            return ([], [])
        if self.t0 is None:
            self._calculate_t0()
        x_values, y_values = [], []
        for i in self.raw_values[name]:
            x_values.append(i['t'] if absolute else i['t'] - self.t0)
            y_values.append(i['val'])
        if smooth:
            y_values = self.smoothed(y_values, smooth)
        return x_values, y_values

    def __getitem__(self, name):
        return self.series(name)

    def __contains__(self, name):
        return name in self._results

    def smoothed(self, res, amount):
        smooth_res = []
        for i in range(len(res)):
            s = int(max(0, i - amount / 2))
            e = int(min(len(res), i + amount / 2))
            window = [j for j in res[s:e] if j is not None]
            if window and res[i] is not None:
                smooth_res.append(math.fsum(window) / len(window))
            else:
                smooth_res.append(None)
        return smooth_res

    @property
    def series_names(self):
        return list(self._results.keys())

    def zipped(self, keys=None):
        if keys is None:
            keys = self.series_names
        for i in range(len(self._x_values)):
            y = [self._x_values[i]]
            for k in keys:
                if k in self._results:
                    y.append(self._results[k][i])
                else:
                    y.append(None)
            yield y

    def __iter__(self):
        return self.zipped()

    def __len__(self):
        return len(self._x_values)

    def __hash__(self):
        if self._loaded_from is None:
            return id(self)
        return self._loaded_from.__hash__()

    def __eq__(self, other):
        return isinstance(other, self.__class__) \
            and self.__hash__() == other.__hash__()

    def serialise_metadata(self):
        metadata = self.metadata.copy()
        for t in TIME_SETTINGS:
            if t in metadata and metadata[t] is not None:
                metadata[t] = format_date(metadata[t], utc=True)
        return metadata

    def serialise(self):
        metadata = self.serialise_metadata()
        return {
            'metadata': metadata,
            'version': FILEFORMAT_VERSION,
            'x_values': self._x_values,
            'results': self._results,
            'raw_values': self._raw_values,
        }

    @property
    def empty(self):
        return not self._x_values

    def dump(self, fp):
        data = self.dumps()
        if hasattr(data, "decode"):
            data = data.decode()

        return fp.write(data)

    def dump_file(self, filename):
        try:
            if filename.endswith(".gz"):
                o = gzip_open
            elif filename.endswith(".bz2"):
                o = bz2_open
            else:
                o = open
            with o(filename, "wt") as fp:
                self.dump(fp)
        except IOError as e:
            logger.error("Unable to write results data file: %s", e)

    def dumps(self):
        return json.dumps(self.serialise(), indent=JSON_INDENT, sort_keys=True)

    @property
    def dump_filename(self):
        if hasattr(self, '_dump_file'):
            return self._dump_file
        return self._gen_filename()

    def _gen_filename(self):
        if self._filename is not None:
            return self._filename
        if 'TITLE' in self.metadata and self.metadata['TITLE']:
            name = "%s-%s.%%s%s" % (self.metadata['NAME'],
                                    format_date(self.metadata['TIME']).replace(
                                        ":", ""),
                                    self.SUFFIX)
            title_len = MAX_FILENAME_LEN - len(name) + 2
            return name % re.sub("[^A-Za-z0-9]", "_",
                                 self.metadata['TITLE'])[:title_len]

        else:
            return "%s-%s%s" % (self.metadata['NAME'],
                                format_date(self.metadata['TIME']).replace(":",
                                                                           ""),
                                self.SUFFIX)

    def dump_dir(self, dirname):
        self._dump_file = os.path.join(dirname, self._gen_filename())
        try:
            if self._dump_file.endswith(".gz"):
                o = gzip_open
            elif self._dump_file.endswith(".bz2"):
                o = bz2_open
            else:
                o = open
            with o(self._dump_file, "wt") as fp:
                self.dump(fp)
        except IOError as e:
            logger.error("Unable to write results data file: %s", e)
            self._dump_file = None

    @classmethod
    def unserialise(cls, obj, absolute=False, SUFFIX=SUFFIX):
        try:
            version = int(obj['version'])
        except (KeyError, ValueError):
            version = 1

        if version > FILEFORMAT_VERSION:
            raise RuntimeError(
                "File format version %d is too new. "
                "Please upgrade your version of Flent" % version)
        if version < FILEFORMAT_VERSION:
            obj = cls.unserialise_compat(version, obj, absolute)
        metadata = dict(obj['metadata'])

        if 'TOTAL_LENGTH' not in metadata or metadata['TOTAL_LENGTH'] is None:
            metadata['TOTAL_LENGTH'] = max(obj['x_values'])

        for t in TIME_SETTINGS:
            if t in metadata and metadata[t] is not None:
                metadata[t] = parse_date(metadata[t])
        rset = cls(SUFFIX=SUFFIX, **metadata)
        if absolute:
            t0 = metadata.get('T0', metadata.get('TIME'))
            x0 = timegm(t0.timetuple()) + t0.microsecond / 1000000.0
            rset.x_values = [x + x0 for x in obj['x_values']]
            rset._absolute = True
        else:
            rset.x_values = obj['x_values']
        for k, v in list(obj['results'].items()):
            rset.add_result(k, v)
        rset.raw_values = obj['raw_values']
        return rset

    @classmethod
    def unserialise_compat(cls, version, obj, absolute=False):
        if version == 1:
            obj['raw_values'] = {}
            if 'SERIES_META' in obj['metadata']:
                obj['raw_values'] = dict([(k, v['RAW_VALUES']) for k, v in
                                          obj['metadata']['SERIES_META'].items()
                                          if 'RAW_VALUES' in v])
            if not obj['raw_values']:
                # No raw values were stored in the old data set. Fake them by
                # using the interpolated values as 'raw'. This ensures there's
                # always some data available as raw values, to facilitate
                # relying on their presence in future code.

                t0 = parse_date(obj['metadata'].get(
                    'T0', obj['metadata'].get('TIME')))
                x0 = timegm(t0.timetuple()) + t0.microsecond / 1000000.0
                for name in obj['results'].keys():
                    obj['raw_values'][name] = [{'t': x0 + x, 'val': r} for x, r in
                                               zip(obj['x_values'],
                                                   obj['results'][name])]
                obj['metadata']['FAKE_RAW_VALUES'] = True

            if 'NETPERF_WRAPPER_VERSION' in obj['metadata']:
                obj['metadata']['FLENT_VERSION'] = obj[
                    'metadata']['NETPERF_WRAPPER_VERSION']
                del obj['metadata']['NETPERF_WRAPPER_VERSION']

        return obj

    @classmethod
    def load(cls, fp, absolute=False):
        if hasattr(fp, 'name'):
            filename = fp.name
            name, ext = os.path.splitext(filename)
            if ext in ('.gz', '.bz2'):
                ext = os.path.splitext(name)[1] + ext
        else:
            filename, ext = None, SUFFIX
        try:
            obj = cls.unserialise(json.load(fp), absolute, SUFFIX=ext)
        except ValueError as e:
            raise RuntimeError(
                "Unable to load JSON from '%s': %s." % (filename, e))
        return obj

    @classmethod
    def load_file(cls, filename, absolute=False):
        try:
            if filename.endswith(".gz"):
                o = gzip_open
            elif filename.endswith(".bz2") or filename.endswith(".flnt"):
                o = bz2_open
            else:
                o = open
            fp = o(filename, 'rt')
            r = cls.load(fp, absolute)
            r._loaded_from = os.path.realpath(filename)
            fp.close()
            return r
        except IOError:
            raise RuntimeError("Unable to read input file: '%s'" % filename)

    @classmethod
    def loads(cls, s):
        try:
            return cls.unserialise(json.loads(s))
        except ValueError as e:
            raise RuntimeError("Unable to load JSON data: %s." % e)
