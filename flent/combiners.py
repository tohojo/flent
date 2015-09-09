## -*- coding: utf-8 -*-
##
## combiners.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:     13 March 2015
## Copyright (c) 2015, Toke Høiland-Jørgensen
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

from __future__ import absolute_import, division, print_function, unicode_literals

import re

from .util import classname, long_substr
from .resultset import ResultSet

from itertools import cycle
from bisect import bisect_left, bisect_right
from collections import OrderedDict

try:
    from itertools import izip_longest as zip_longest
except ImportError:
    from itertools import zip_longest

try:
    import numpy
    HAS_NUMPY=True
except ImportError:
    HAS_NUMPY=False

def get_combiner(combiner_type):
    cname = classname(combiner_type, "Combiner")
    if not cname in globals():
        raise RuntimeError("Combiner not found: '%s'" % plot_type)
    return globals()[cname]

def new(combiner_type, *args):
    try:
        return get_combiner(combiner_type)(*args)
    except Exception as e:
        raise RuntimeError("Error loading combiner: %s." % e)


class Combiner(object):
    # Match a word of all digits, optionally with a non-alphanumeric character
    # preceding or succeeding it. For instance a series of files numbered as
    # -01, -02, etc.
    serial_regex = re.compile(r'\W?\b\d+\b\W?')

    def __init__(self, print_n=False):
        self.filter_regexps = []
        self.filter_serial = True
        self.filter_prefix = True
        self.print_n = print_n

    def __call__(self, results, config):
        return self.combine(results, config)

    def combine(self, results, config):

        """Combines several result sets into one box plot by grouping them on
        unique data file name parts and then combining each group into a single
        data set."""

        self.config = config

        # Group the result sets into the groups that will appear as new data
        # sets. This is done on the file name, by first removing the file
        # extension and the longest common prefix from all the loaded file
        # names, then removing the first word boundary-delimited sequence of
        # digits.
        #
        # The idea is that the data files will be named by a common prefix, with
        # the distinguishing attribute (for instance configured qdisc) at the
        # end, followed by a number signifying test iteration. So for instance
        # given the filenames:
        #
        # rrul-fq_codel-01.flent.gz
        # rrul-fq_codel-02.flent.gz
        # rrul-fq_codel-03.flent.gz
        # rrul-pfifo_fast-01.flent.gz
        # rrul-pfifo_fast-02.flent.gz
        # rrul-pfifo_fast-03.flent.gz
        #
        # two new data sets will be created ('fq_codel' and 'pfifo_fast'), each
        # with three data points created from each of the data files. The
        # function used to map the data points of each result set into a single
        # data point is specified in the test config, and can be one of:
        #
        # mean, median, min, max : resp value computed from all valid data points
        # span: max()-min() from all data points
        # mean_span: mean of all data points' difference from the min value
        # mean_zero: mean value with missing data points interpreted as 0 rather
        #            than being filtered out
        groups = OrderedDict()
        new_results, regexps, names = [], [], []
        filenames = [r.meta('DATA_FILENAME').replace(r.SUFFIX, '') for r in results]
        for r in self.filter_regexps:
            regexps.append(re.compile(r))
        if self.filter_serial:
            regexps.append(self.serial_regex)
        if self.filter_prefix:
            prefix = long_substr(filenames, prefix_only=True)
            names = [n.replace(prefix, "", 1) for n in filenames]
        else:
            names = filenames

        for i,n in enumerate(names):
            for r in regexps:
                n = r.sub("", n, count=1)
            if n in groups:
                groups[n].append(results[i])
            else:
                groups[n] = [results[i]]

        self.orig_series = config['series']
        self.orig_name = results[0].meta('NAME')

        # Do the main combine - group() is defined by subclasses.
        new_results = self.group(groups, config)

        # We've already been applying the cutoff value on combine, make sure the
        # plotting functions don't do that also.
        config['cutoff'] = None

        return new_results

    def get_reducer(self, s_config):
        reducer_name = s_config.get('combine_mode', 'mean')
        cutoff = self.config.get('cutoff', None)
        return  get_reducer(reducer_name, cutoff)


class GroupsCombiner(Combiner):
    # group_by == 'groups' means preserve the data series and group the data
    # by the data groups identified above -- i.e. they become the items in
    # the legend.
    def group(self, groups, config):

        new_results = []

        for k in groups.keys():
            title = "%s (n=%d)" % (k, len(groups[k])) if self.print_n else k
            res = ResultSet(TITLE=title, NAME=self.orig_name)
            res.create_series([s['data'] for s in self.orig_series])
            x = 0
            for r in groups[k]:
                data = {}
                for s in self.orig_series:
                    reducer = self.get_reducer(s)
                    data[s['data']] = reducer(r, s['data'])

                res.append_datapoint(x, data)
                x += 1
            new_results.append(res)
        return new_results

class GroupsPointsCombiner(Combiner):
    # groups_points means group by groups, but do per-point combinations, to
    # e.g. create a data series that is the mean of several others

    def group(self, groups, config):
        new_results = []
        for k in groups.keys():
            title = "%s (n=%d)" % (k, len(groups[k])) if self.print_n else k
            res = ResultSet(TITLE=title, NAME=self.orig_name)
            x_values = []
            for r in groups[k]:
                if len(r.x_values) > len(x_values):
                    x_values = r.x_values
            cutoff = config.get('cutoff', None)
            if cutoff is not None:
                res.x_values = [x for x in x_values if x >= cutoff[0] and x <= max(x_values)-cutoff[1]]
            else:
                res.x_values = x_values
            for s in config['series']:
                data = zip_longest(x_values, *[r[s['data']] for r in groups[k]])
                new_data = []
                reducer = self.get_reducer(s)
                reducer.cutoff = None
                for d in data:
                    if cutoff is None or (d[0] >= cutoff[0] and d[0] <= max(x_values)-cutoff[1]):
                        new_data.append(reducer(res, s['data'], data=d[1:]))
                res.add_result(s['data'], new_data)
            new_results.append(res)
        return new_results

class GroupsConcatCombiner(Combiner):
        # groups_concat means group by groups, but concatenate the points of all
        # the groups, e.g. to create a combined CDF of all data points

    def group(self, groups, config):
        new_results = []
        for k in groups.keys():
            title = "%s (n=%d)" % (k, len(groups[k])) if self.print_n else k
            res = ResultSet(TITLE=title, NAME=self.orig_name)
            res.create_series([s['data'] for s in self.orig_series])
            cutoff = config.get('cutoff', None)
            x = 0
            for r in groups[k]:
                if cutoff:
                    start =  min(r.x_values) + cutoff[0]
                    end   =  max(r.x_values) - cutoff[1]
                keys , minvals = [], {}
                for s in self.orig_series:
                    k = s['data']
                    keys.append(k)
                    if s.get('combine_mode', None) == 'span' and k in r:
                        minvals[k] = min([d for d in r.series(k) if d is not None])
                    else:
                        minvals[k] = None
                for p in r.zipped(keys):
                    if cutoff is None or (p[0] > start and p[0] < end):
                        dp = {}
                        for k,v in zip(keys, p[1:]):
                            if minvals[k] is None:
                                dp[k] = v
                            elif v is not None:
                                dp[k] = v-minvals[k]
                            else:
                                pass # skip None-values when a minval exists
                        res.append_datapoint(x, dp)
                        x += 1
            new_results.append(res)
        return new_results

class SeriesCombiner(Combiner):
    # group_by == 'series' means flip the group and series, so the groups
    # become the entries on the x axis, while the series become the new
    # groups (in the legend)
    def group(self, groups, config):

        new_results = []

        for s in self.orig_series:
            res = ResultSet(TITLE=s['label'], NAME=self.orig_name)
            res.create_series(groups.keys())
            x = 0
            for d in zip_longest(*groups.values()):
                data = {}
                for k,v in zip(groups.keys(), d):
                    reducer = self.get_reducer(s)
                    data[k] = reducer(v, s['data']) if v is not None else Non
                res.append_datapoint(x, data)
                x += 1
            new_results.append(res)
        new_series = []
        for k in groups.keys():
            new_series.append({'data': k, 'label': k})
        config['series'] = new_series

        return new_results

class BothCombiner(Combiner):

    # group_by == 'both' means that the group names should be split by a
    # delimiter (currently '-') and the first part specifies the group, the
    # second the series. Currently only works if there's just one series
    # name configured in the plot config.
    def group(self, groups, config):
        assert len(config['series']) == 1
        series_names = []
        group_names = []
        old_s = config['series'][0]
        for k in groups.keys():
            s,g = k.rsplit("-",1)
            if not s in series_names:
                series_names.append(s)
            if not g in group_names:
                group_names.append(g)
        new_series = [{'data': s, 'label': s} for s in series_names]
        new_results = []
        for s in group_names:
            res = ResultSet(TITLE=s,NAME=self.orig_name)
            res.create_series(series_names)
            x = 0
            for d in zip_longest(*[g[1] for g in groups.items() if g[0].endswith("-%s" % s)]):
                data = {}
                for k,v in zip([k.rsplit("-",1)[0] for k in groups.keys() if k.endswith("-%s" % s)], d):
                    reducer = self.get_reducer(old_s)
                    data[k] = reducer(v, old_s['data']) if v is not None else Non

                res.append_datapoint(x, data)
                x += 1
            new_results.append(res)
        config['series'] = new_series

        return new_results

def get_reducer(reducer_type, cutoff):
    if ":" in reducer_type:
        reducer_type,reducer_arg = reducer_type.split(":", 1)
    else:
        reducer_arg = None
    cname = classname(reducer_type, "Reducer")
    if not cname in globals():
        raise RuntimeError("Reducer not found: '%s'" % reducer_type)
    return globals()[cname](reducer_arg, cutoff)

class Reducer(object):
    filter_none = True
    numpy_req = False

    def __init__(self, arg, cutoff):
        self.arg = arg
        self.cutoff = cutoff

    def __call__(self, resultset, key, data=None):
        return self.reduce(resultset,key, data)

    def reduce(self, resultset, key, data=None):
        if self.numpy_req and not HAS_NUMPY:
            raise RuntimeError("%s requires numpy." % self.__class__)
        if data is None:
            data = resultset[key]
        if self.cutoff:
            start = min(resultset.x_values)+self.cutoff[0]
            end = max(resultset.x_values)-self.cutoff[1]
            start_idx = bisect_left(resultset.x_values,start)
            end_idx = bisect_right(resultset.x_values,end)
            data = data[start_idx:end_idx]
        if self.filter_none:
            data = [p for p in data if p is not None]
        if not data:
            return None
        return self._reduce(data)


class MeanReducer(Reducer):
    numpy_req = True
    def _reduce(self, data):
        return numpy.mean(data)

class MedianReducer(Reducer):
    numpy_req = True
    def _reduce(self, data):
        return numpy.median(data)

class MinReducer(Reducer):
    numpy_req = True
    def _reduce(self, data):
        return numpy.mean(data)

class MaxReducer(Reducer):
    numpy_req = True
    def _reduce(self, data):
        return numpy.mean(data)

class SpanReducer(Reducer):
    def _reduce(self, data):
        return max(data)-min(data)

class MeanSpanReducer(Reducer):
    numpy_req = True
    def _reduce(self, data):
        min_val = min(data)
        d = [i-min_val for i in data]
        return numpy.mean(d)

class MeanZeroReducer(Reducer):
    numpy_req = True
    filter_none = False
    def _reduce(self, data):
        d = [p if p is not None else 0 for p in data]
        return numpy.mean(d) if d else None

class RawSeqLossReducer(Reducer):
    filter_none = False

    def reduce(self, resultset, key, data=None):
        if '::' in key:
           key = key.split("::")[0]
        try:
            if self.cutoff is not None:
                start,end = self.cutoff
                start_t = min([r['t'] for r in resultset.raw_values[key]])+start
                end_t = max([r['t'] for r in resultset.raw_values[key]])-end
                seqs = [r['seq'] for r in resultset.raw_values[key] if r['t'] > start_t and r['t'] < end_t]
            else:
                seqs = [r['seq'] for r in resultset.raw_values[key]]
            return 1-len(seqs)/(max(seqs)-min(seqs)+1)
        except KeyError:
            return None

class MetaReducer(Reducer):
    filter_none = False

    def reduce(self, resultset, key, data=None):
        metakey = self.arg
        try:
            return resultset.meta('SERIES_META')[key][metakey]
        except KeyError:
            return None
