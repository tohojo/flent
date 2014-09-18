## -*- coding: utf-8 -*-
##
## resultset.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:     24 November 2012
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

import json, os, math, re, sys
from datetime import datetime
from calendar import timegm
from itertools import repeat
from copy import deepcopy

try:
    from dateutil.parser import parse as parse_date
except ImportError:
    from .util import parse_date

try:
    from collections import OrderedDict
except ImportError:
    from .ordereddict import OrderedDict

from .util import gzip_open

# Controls pretty-printing of json dumps
JSON_INDENT=2

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
    "NETPERF_WRAPPER_VERSION",
    "IP_VERSION",
    "BATCH_NAME",
    "BATCH_TIME",
    "DATA_FILENAME",
    "HTTP_GETTER_URLLIST",
    "HTTP_GETTER_DNS",
    "HTTP_GETTER_WORKERS",
    )

# Time settings will be serialised as ISO timestamps and stored in memory as
# datetime instances
TIME_SETTINGS = ("TIME", "BATCH_TIME", "T0")

def new(settings):
    d = {}
    for a in RECORDED_SETTINGS:
        d[a] = deepcopy(getattr(settings,a,None))
    return ResultSet(**d)

def load(filename, absolute=False):
    return ResultSet.load_file(filename, absolute)

class ResultSet(object):
    SUFFIX = '.json.gz'
    def __init__(self, **kwargs):
        self._x_values = []
        self._results = OrderedDict()
        self._filename = None
        self._absolute = False
        self.metadata = kwargs
        if not 'TIME' in self.metadata or self.metadata['TIME'] is None:
            self.metadata['TIME'] = datetime.now()
        if not 'NAME' in self.metadata or self.metadata['NAME'] is None:
            raise RuntimeError("Missing name for resultset")
        if not 'DATA_FILENAME' in self.metadata or self.metadata['DATA_FILENAME'] is None:
            self.metadata['DATA_FILENAME'] = self.dump_file
        if not self.metadata['DATA_FILENAME'].endswith(self.SUFFIX):
            self.metadata['DATA_FILENAME'] += self.SUFFIX
        self._filename = self.metadata['DATA_FILENAME']

    def meta(self, k=None, v=None):
        if k:
            if v:
                self.metadata[k] = v
            return self.metadata[k]
        return self.metadata

    def label(self):
        return self.metadata["TITLE"] or self.metadata["TIME"].strftime("%Y-%m-%d %H:%M:%S")

    def get_x_values(self):
        return self._x_values
    def set_x_values(self, x_values):
        assert not self._x_values
        self._x_values = list(x_values)
    x_values = property(get_x_values, set_x_values)

    def add_result(self, name, data):
        assert len(data) == len(self._x_values)
        self._results[name] = data

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
            xnext = (self.x_values[-1] + res.x_values[0])/2.0
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
        if not name in self._results:
            sys.stderr.write("Warning: Missing data points for series '%s'\n" % name)
            return [None]*len(self.x_values)
        if smooth:
            return self.smoothed(name, smooth)
        return self._results[name]

    def __getitem__(self, name):
        return self.series(name)

    def __contains__(self, name):
        return name in self._results

    def smoothed(self, name, amount):
        res = self._results[name]
        smooth_res = []
        for i in range(len(res)):
            s = int(max(0,i-amount/2))
            e = int(min(len(res),i+amount/2))
            window = [j for j in res[s:e] if j is not None]
            if window and res[i] is not None:
                smooth_res.append(math.fsum(window)/len(window))
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

    def serialise_metadata(self):
        metadata = self.metadata.copy()
        for t in TIME_SETTINGS:
            if t in metadata and metadata[t] is not None:
                metadata[t] = metadata[t].isoformat()
        return metadata

    def serialise(self):
        metadata = self.serialise_metadata()
        return {
            'metadata': metadata,
            'x_values': self._x_values,
            'results': self._results,
            }

    @property
    def empty(self):
        return not self._x_values

    def dump(self, fp):
        data = self.dumps()
        if hasattr(data, "decode"):
            data = data.decode()

        return fp.write(data)

    def dumps(self):
        return json.dumps(self.serialise(), indent=JSON_INDENT, sort_keys=True)

    @property
    def dump_file(self):
        if hasattr(self, '_dump_file'):
            return self._dump_file
        return self._gen_filename()

    def _gen_filename(self):
        if self._filename is not None:
            return self._filename
        if 'TITLE' in self.metadata and self.metadata['TITLE']:
            return "%s-%s.%s%s" % (self.metadata['NAME'],
                                         self.metadata['TIME'].isoformat().replace(":", ""),
                                         re.sub("[^A-Za-z0-9]", "_", self.metadata['TITLE'])[:50],
                                         self.SUFFIX)
        else:
            return "%s-%s%s" % (self.metadata['NAME'], self.metadata['TIME'].isoformat().replace(":", ""), self.SUFFIX)

    def dump_dir(self, dirname):
        self._dump_file = os.path.join(dirname, self._gen_filename())
        try:
            fp = gzip_open(self._dump_file, "wt")
            try:
                self.dump(fp)
            finally:
                fp.close()
        except IOError as e:
            sys.stderr.write("Unable to write results data file: %s\n" % e)
            self._dump_file = None

    @classmethod
    def unserialise(cls, obj, absolute=False):
        metadata = dict(obj['metadata'])
        for t in TIME_SETTINGS:
            if t in metadata and metadata[t] is not None:
                metadata[t] = parse_date(metadata[t])
        rset = cls(**metadata)
        if absolute:
            t0 = metadata.get('T0', metadata.get('TIME'))
            x0 = timegm(t0.timetuple()) + t0.microsecond / 1000000.0
            rset.x_values = [x+x0 for x in obj['x_values']]
            rset._absolute = True
        else:
            rset.x_values = obj['x_values']
        for k,v in list(obj['results'].items()):
            rset.add_result(k,v)
        return rset

    @classmethod
    def load(cls, fp, absolute=False):
        obj = cls.unserialise(json.load(fp), absolute)
        if hasattr(fp, 'name'):
            obj._dump_file = fp.name
        return obj

    @classmethod
    def load_file(cls, filename, absolute=False):
        try:
            if filename.endswith(".gz"):
                o = gzip_open
            else:
                o = open
            fp = o(filename, 'rt')
            r = cls.load(fp, absolute)
            fp.close()
            return r
        except IOError:
            raise RuntimeError("Unable to read input file: '%s'" % filename)

    @classmethod
    def loads(cls, s):
        return cls.unserialise(json.loads(s))
