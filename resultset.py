## -*- coding: utf-8 -*-
##
## resultset.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:     24 november 2012
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

import json, os, gzip
from datetime import datetime
from dateutil.parser import parse as parse_date

from ordereddict import OrderedDict

# Controls pretty-printing of json dumps
JSON_INDENT=None

__all__ = ['ResultSet']

class ResultSet(object):
    def __init__(self, **kwargs):
        self.metadata = kwargs
        if not 'TIME' in self.metadata:
            self.metadata['TIME'] = datetime.now()
        if not 'NAME' in self.metadata:
            raise RuntimeError("Missing name for resultset")
        self._x_values = []
        self._results = OrderedDict()

    def meta(self, k=None):
        if k:
            return self.metadata[k]
        return self.metadata

    def get_x_values(self):
        return self._x_values
    def set_x_values(self, x_values):
        assert not self._x_values
        self._x_values = x_values
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
        self._x_values.append(x)
        for k in self._results.keys():
            if k in data:
                self._results[k].append(data[k])
                del data[k]
            else:
                self._results[k].append(None)

        if data:
            raise RuntimeError("Unexpected data point(s): %s" % data.keys())

    def series(self, name, smooth=None):
        if smooth:
            return self.smoothed(name, smooth)
        return self._results[name]

    def smoothed(self, name, amount):
        res = self._results[name]
        smooth_res = []
        for i in range(len(res)):
            s = max(0,i-amount/2)
            e = min(len(res),i+amount/2)
            window = res[s:e]
            smooth_res.append(math.fsum(window)/len(window))
        return smooth_res


    @property
    def series_names(self):
        return self._results.keys()

    def zipped(self, keys=None):
        if keys is None:
            keys = self.series_names
        for i in range(len(self._x_values)):
            yield [self._x_values[i]]+[self._results[k][i] for k in keys]

    def __iter__(self):
        return self.zipped()

    def __len__(self):
        return len(self._x_values)

    def serialise(self):
        metadata = dict(self.metadata)
        metadata['TIME'] = metadata['TIME'].isoformat()
        return {
            'metadata': metadata,
            'x_values': self._x_values,
            'results': self._results,
            }

    @property
    def empty(self):
        return not self._x_values

    def dump(self, fp):
        return json.dump(self.serialise(), fp, indent=JSON_INDENT)

    def dumps(self):
        return json.dumps(self.serialise(), indent=JSON_INDENT)

    def dump_dir(self, dirname):
        filename = "%s-%s.data.json.gz" % (self.metadata['NAME'], self.metadata['TIME'].isoformat())
        with gzip.open(os.path.join(dirname, filename), "w") as fp:
            self.dump(fp)

    @classmethod
    def unserialise(cls, obj):
        metadata = dict(obj['metadata'])
        if 'TIME' in metadata:
            metadata['TIME'] = parse_date(metadata['TIME'])
        rset = cls(**metadata)
        rset.x_values = obj['x_values']
        for k,v in obj['results'].items():
            rset.add_result(k,v)
        return rset

    @classmethod
    def load(cls, fp):
        return cls.unserialise(json.load(fp))

    @classmethod
    def loads(cls, s):
        return cls.unserialise(json.loads(s))
