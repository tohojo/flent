# -*- coding: utf-8 -*-
#
# combiners.py
#
# Author:   Toke Høiland-Jørgensen (toke@toke.dk)
# Date:     13 March 2015
# Copyright (c) 2015-2016, Toke Høiland-Jørgensen
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
import re

from datetime import datetime
from bisect import bisect_left, bisect_right
from collections import OrderedDict

try:
    from itertools import izip_longest as zip_longest
except ImportError:
    from itertools import zip_longest

from flent.util import classname, long_substr, Glob, format_date, mos_score
from flent.resultset import ResultSet
from flent.loggers import get_logger

try:
    import numpy
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

logger = get_logger(__name__)


def get_combiner(combiner_type):
    cname = classname(combiner_type, "Combiner")
    if cname not in globals():
        raise RuntimeError("Combiner not found: '%s'" % combiner_type)
    return globals()[cname]


def new(combiner_type, *args, **kwargs):
    try:
        return get_combiner(combiner_type)(*args, **kwargs)
    except Exception as e:
        raise RuntimeError("Error loading combiner: %s." % e)


class Combiner(object):
    # Match a word of all digits, optionally with a non-alphanumeric character
    # preceding or succeeding it. For instance a series of files numbered as
    # -01, -02, etc.
    serial_regex = re.compile(r'\W?\b\d+\b\W?')

    def __init__(self, print_n=False, filter_regexps=None, filter_series=None,
                 save_dir=None):
        self.filter_serial = True
        self.filter_prefix = True
        self.print_n = print_n
        self.save_dir = save_dir
        if filter_regexps is not None:
            self.filter_regexps = filter_regexps
        else:
            self.filter_regexps = []
        self.filter_series = filter_series

    def __call__(self, results, config):
        if self.check_intermediate(results, config):
            return results

        res = self.combine(results, config)
        self.save_intermediate(res, config, results[0].meta())

        return res

    def check_intermediate(self, results, config):
        valid = True
        for r in results:
            if "FROM_COMBINER" in r.meta():
                if r.meta("FROM_COMBINER") != self.__class__.__name__:
                    raise RuntimeError("Intermediate results from different "
                                       "combiner: %s/%s"
                                       % (r.meta("FROM_COMBINER"),
                                          self.__class__.__name__))
                if r.meta("COMBINER_PLOT") != config['plot_name']:
                    raise RuntimeError("Intermediate results from different "
                                       "plot: %s/%s" % (r.meta("COMBINER_PLOT"),
                                                        config['plot_name']))
            else:
                valid = False
        if valid:
            config['series'] = results[0].meta("COMBINER_SERIES")
            config['cutoff'] = None
        return valid

    def save_intermediate(self, new_results, config, orig_meta):
        orig_meta = orig_meta.copy()
        del orig_meta['TITLE']
        if self.save_dir:
            t = datetime.utcnow()
            series = config['series']
            # Can't serialise 'source' Glob objects
            for s in series:
                if 'source' in s:
                    del s['source']
            for i, r in enumerate(new_results):
                r.meta().update(orig_meta)
                r.meta("FROM_COMBINER", self.__class__.__name__)
                r.meta("COMBINER_SERIES", series)
                r.meta("COMBINER_PLOT", config['plot_name'])
                r._filename = "%s-%s-%s-%02d%s" % (
                    config['plot_name'],
                    self.__class__.__name__,
                    format_date(t).replace(":", ""),
                    i,
                    r.SUFFIX)
                r.dump_dir(self.save_dir)

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
        filenames = [r.meta('DATA_FILENAME').replace(r.SUFFIX, '')
                     for r in results]
        for r in self.filter_regexps:
            regexps.append(re.compile(r))
        if self.filter_serial:
            regexps.append(self.serial_regex)
        if self.filter_prefix:
            prefix = long_substr(filenames, prefix_only=True)
            names = [n.replace(prefix, "", 1) for n in filenames]
        else:
            names = filenames

        for i, n in enumerate(names):
            for r in regexps:
                n = r.sub("", n, count=1)
            if n in groups:
                groups[n].append(results[i])
            else:
                groups[n] = [results[i]]

        self.orig_series = [s for s in config['series']
                            if not s['data'] in self.filter_series]
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
        return get_reducer(reducer_name, cutoff, self.filter_series)


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
                    data[s['data']] = reducer(r, s)

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
                res.x_values = [x for x in x_values
                                if x >= cutoff[0] and
                                x <= max(x_values) - cutoff[1]]
            else:
                res.x_values = x_values
            for s in config['series']:
                length = max([r.meta("TOTAL_LENGTH") for r in groups[k]])
                data = zip_longest(x_values, *[r[s['data']] for r in groups[k]])
                new_data = []
                reducer = self.get_reducer(s)
                reducer.cutoff = None
                for d in data:
                    if cutoff is None or (d[0] >= cutoff[0] and
                                          d[0] <= length - cutoff[1]):
                        new_data.append(reducer(res, s, data=d[1:]))
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
                    start = min(r.x_values) + cutoff[0]
                    end = min(r.x_values) + r.meta("TOTAL_LENGTH") - cutoff[1]
                keys, minvals = [], {}
                for s in self.orig_series:
                    k = s['data']
                    keys.append(k)
                    if s.get('combine_mode', None) == 'span' and k in r:
                        minvals[k] = min(
                            [d for d in r.series(k) if d is not None])
                    else:
                        minvals[k] = None
                for p in r.zipped(keys):
                    if cutoff is None or (p[0] > start and p[0] < end):
                        dp = {}
                        for k, v in zip(keys, p[1:]):
                            if minvals[k] is None:
                                dp[k] = v
                            elif v is not None:
                                dp[k] = v - minvals[k]
                            else:
                                pass  # skip None-values when a minval exists
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
                for k, v in zip(groups.keys(), d):
                    reducer = self.get_reducer(s)
                    data[k] = reducer(v, s) if v is not None else None
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
            s, g = k.rsplit("-", 1)
            if s not in series_names:
                series_names.append(s)
            if g not in group_names:
                group_names.append(g)
        new_series = [{'data': s, 'label': s} for s in series_names]
        new_results = []
        for s in group_names:
            res = ResultSet(TITLE=s, NAME=self.orig_name)
            res.create_series(series_names)
            x = 0
            for d in zip_longest(*[g[1] for g in groups.items()
                                   if g[0].endswith("-%s" % s)]):
                data = {}
                for k, v in zip([k.rsplit("-", 1)[0] for k in groups.keys()
                                 if k.endswith("-%s" % s)], d):
                    reducer = self.get_reducer(old_s)
                    data[k] = reducer(v, old_s) if v is not None else None

                res.append_datapoint(x, data)
                x += 1
            new_results.append(res)
        config['series'] = new_series

        return new_results


class BatchCombiner(GroupsCombiner):
    # group_by == 'batch' means group data sets by their batch UUID, getting
    # titles from the BATCH_TITLE if set

    def combine(self, results, config):

        self.config = config
        self.orig_series = config['series']
        self.orig_name = results[0].meta('NAME')

        groupmap = {}
        groups = OrderedDict()
        for r in results:
            u = "%s - %s " % (r.meta().get("BATCH_UUID", "None"), r.meta('NAME'))
            if u not in groupmap:
                t = "%s - %s" % (r.meta("BATCH_TITLE"), r.meta('NAME'))
                if not t or t in groupmap.values():
                    t = u
                groupmap[u] = t
            k = groupmap[u]
            if k not in groups:
                groups[k] = []
            groups[k].append(r)

        new_results = self.group(groups, config)
        config['cutoff'] = None

        return new_results


class BatchConcatCombiner(GroupsConcatCombiner, BatchCombiner):
    pass


class BatchSeriesCombiner(SeriesCombiner, BatchCombiner):
    pass


def get_reducer(reducer_type, *args):
    if ":" in reducer_type:
        reducer_type, reducer_arg = reducer_type.split(":", 1)
    else:
        reducer_arg = None
    cname = classname(reducer_type, "Reducer")
    if cname not in globals():
        raise RuntimeError("Reducer not found: '%s'" % reducer_type)
    return globals()[cname](reducer_arg, *args)


class Reducer(object):
    filter_none = True
    numpy_req = False

    def __init__(self, arg, cutoff, filter_series):
        self.arg = arg
        self.cutoff = cutoff
        self.filter_series = filter_series

    def __call__(self, resultset, series, data=None):
        return self.reduce(resultset, series, data)

    def reduce(self, resultset, series, data=None):
        if self.numpy_req and not HAS_NUMPY:
            raise RuntimeError("%s requires numpy." % self.__class__.__name__)

        if data is None:
            data = resultset[series['data']]

        if 'norm_by' in series:
            norm_series = series['norm_by'].format(**series)
            norm_data = resultset[norm_series]
        else:
            norm_data = []

        if self.cutoff:
            start = min(resultset.x_values) + self.cutoff[0]
            end = min(resultset.x_values) + \
                resultset.meta("TOTAL_LENGTH") - self.cutoff[1]
            start_idx = bisect_left(resultset.x_values, start)
            end_idx = bisect_right(resultset.x_values, end)
            data = data[start_idx:end_idx]
            if norm_data:
                norm_data = norm_data[start_idx:end_idx]

        if self.filter_none:
            data = [p for p in data if p is not None]
            norm_data = [p for p in norm_data if p is not None]

        if not data:
            return None

        val = self._reduce(data)

        if norm_data:
            normval = self._reduce(norm_data)
            return val / normval

        return val


class FairnessReducer(Reducer):

    def reduce(self, resultset, series, data=None):
        key = series['data']
        source = Glob.expand_list(series['source'], resultset.series_names,
                                  exclude=self.filter_series, args=series)
        values = []
        for key in source:
            v = super(FairnessReducer, self).reduce(
                resultset, None, resultset[key])
            if v is not None:
                values.append(v)
        valsum = math.fsum([x**2 for x in values])
        if not valsum:
            return None
        return math.fsum(values)**2 / (len(values) * valsum)


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
        return max(data) - min(data)


class MeanSpanReducer(Reducer):
    numpy_req = True

    def _reduce(self, data):
        min_val = min(data)
        d = [i - min_val for i in data]
        return numpy.mean(d)


class MeanZeroReducer(Reducer):
    numpy_req = True
    filter_none = False

    def _reduce(self, data):
        d = [p if p is not None else 0 for p in data]
        return numpy.mean(d) if d else None


class RawReducer(Reducer):

    def _get_series(self, resultset, name):
        data = resultset.raw_values[name]
        if data and self.cutoff is not None:
            start, end = self.cutoff
            min_t = min((d['t'] for d in data))
            start_t = min_t + start if start else min_t - 1
            if end is not None:
                end_t = min_t + resultset.meta("TOTAL_LENGTH") - end
                return [d for d in data if d['t'] > start_t and d['t'] < end_t]
            else:
                return [d for d in data if d['t'] > start_t]
        return data

    def reduce(self, resultset, series, data=None):
        key = series['data']
        if '::' in key:
            key = key.split("::")[0]
        try:
            rawdata = self._get_series(resultset, key)
        except KeyError:
            return None
        if not rawdata and self.cutoff:
            logger.warning(
                "No data points with current cutoff settings, "
                "relaxing end cutoff.")
            self.cutoff = (self.cutoff[0], None)
            rawdata = self._get_series(resultset, key)
        if self.filter_none:
            data = [d['val'] for d in rawdata if d['val'] is not None]
        else:
            data = [d['val'] for d in rawdata]
        if not data:
            return None
        return self._reduce(data)


class RawMeanReducer(MeanReducer, RawReducer):
    pass


class RawSeqLossReducer(RawReducer):
    filter_none = False

    def reduce(self, resultset, series, data=None):
        key = series['data']
        if '::' in key:
            key = key.split("::")[0]
        try:
            data = self._get_series(resultset, key)
            seqs = [d['seq'] for d in data]

            return 1 - len(seqs) / (max(seqs) - min(seqs) + 1)
        except (KeyError, ValueError):
            return None


class MosReducer(RawReducer):
    filter_none = False
    numpy_req = True

    def reduce(self, resultset, series, data=None):
        key = series['data']
        data = self._get_series(resultset, key)
        if not data:
            return None
        jitter_samples = []
        delay_samples = []
        loss = 0
        last_delay = -1
        last_seq = -1
        for d in data:
            if last_seq > -1 and d['seq'] - last_seq > 1:
                loss += 1
            last_seq = d['seq']
            if last_delay > -1:
                jitter_samples.append(abs(last_delay - d['val']))
            last_delay = d['val']
            delay_samples.append(d['val'])

        delay = numpy.mean(delay_samples) + 2 * numpy.mean(jitter_samples)
        lossrate = loss / len(data)
        mos = mos_score(delay, lossrate)
        return mos


class MetaReducer(Reducer):
    filter_none = False

    def reduce(self, resultset, series, data=None):
        key = series['data']
        metakey = self.arg
        try:
            return resultset.meta('SERIES_META')[key][metakey]
        except KeyError:
            return None


class FairnessMeanReducer(FairnessReducer, MeanReducer):
    pass
