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

from .util import classname

from itertool import cycle

try:
    import numpy
except ImportError:
    raise RuntimeError("Combining datasets requires numpy.")

def get_combiner(combiner_type):
    cname = classname(combiner_type, "Combiner")
    if not cname in globals():
        raise RuntimeError("Combiner not found: '%s'" % plot_type)
    return globals()[cname]

def new(combiner_type):
    try:
        return get_combiner(combiner_type)()
    except Exception as e:
        raise RuntimeError("Error loading combiner: %s." % e)


class Combiner(object):
    # Match a word of all digits, optionally with a non-alphanumeric character
    # preceding or succeeding it. For instance a series of files numbered as
    # -01, -02, etc.
    serial_regex = re.compile(r'\W?\b\d+\b\W?')

    def __init__(self, settings):
        self.settings = settings

    def combine(self, results):

        """Combines several result sets into one box plot by grouping them on
        unique data file name parts and then combining each group into a single
        data set."""

        if config is None:
            config = self.config

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
        # rrul-fq_codel-01.json.gz
        # rrul-fq_codel-02.json.gz
        # rrul-fq_codel-03.json.gz
        # rrul-pfifo_fast-01.json.gz
        # rrul-pfifo_fast-02.json.gz
        # rrul-pfifo_fast-03.json.gz
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
        for r in self.settings.COMBINE_FILTER_REGEXP:
            regexps.append(re.compile(r))
        if self.settings.COMBINE_FILTER_SERIAL:
            regexps.append(self.serial_regex)
        for f in filename:
            for r in regexps:
                f = r.sub("", f, count=1)
            names.append(f)
        if self.settings.COMBINE_FILTER_PREFIX:
            prefix = long_substr(names, prefix_only=True)
            names = [n.replace(prefix, "") for n in names]

        for i,n in enumerate(names):
            if n in groups:
                groups[n].append(results[i])
            else:
                groups[n] = [results[i]]

        return self.group(groups)

class GroupsCombiner(Combiner):
    # group_by == 'groups' means preserve the data series and group the data
    # by the data groups identified above -- i.e. they become the items in
    # the legend.
    def group(self, groups):

        for k in groups.keys():
            title = "%s (n=%d)" % (k, len(groups[k])) if self.settings.COMBINE_PRINT_N else k
            res = ResultSet(TITLE=title, NAME=results[0].meta('NAME'))
            res.create_series([s['data'] for s in config['series']])
            x = 0
            for r in groups[k]:
                data = {}
                for s in config['series']:
                    data[s['data']] = self._combine_data(r, s['data'], s.get('combine_mode', 'mean'), config.get('cutoff', None))

                res.append_datapoint(x, data)
                x += 1
            new_results.append(res)
        return new_results

def GroupsPointsCombiner(Combiner):
    # groups_points means group by groups, but do per-point combinations, to
    # e.g. create a data series that is the mean of several others

    def group(self, groups):
        for k in groups.keys():
            title = "%s (n=%d)" % (k, len(groups[k])) if self.settings.COMBINE_PRINT_N else k
            res = ResultSet(TITLE=title, NAME=results[0].meta('NAME'))
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
                for d in data:
                    if cutoff is None or (d[0] >= cutoff[0] and d[0] <= max(x_values)-cutoff[1]):
                        new_data.append(self._combine_data(res, s['data'], s.get('combine_mode', 'mean'), None, d=d[1:]))
                res.add_result(s['data'], new_data)
            new_results.append(res)
        return new_results

def GroupsConcatCombiner(Combiner):
        # groups_concat means group by groups, but do per-point combinations, to
        # e.g. create a data series that is the mean of several others

    def group(groups):
        for k in groups.keys():
            title = "%s (n=%d)" % (k, len(groups[k])) if self.settings.COMBINE_PRINT_N else k
            res = ResultSet(TITLE=title, NAME=results[0].meta('NAME'))
            res.create_series([s['data'] for s in config['series']])
            x = 0
            for r in groups[k]:
                keys = [s['data'] for s in config['series']]
                for p in r.zipped(keys):
                    res.append_datapoint(x, dict(zip(keys, p[1:])))
                    x += 1
            new_results.append(res)
        return new_results

def SeriesCombiner(Combiner):
    # group_by == 'series' means flip the group and series, so the groups
    # become the entries on the x axis, while the series become the new
    # groups (in the legend)
    def group(groups):

        for s in config['series']:
            res = ResultSet(TITLE=s['label'], NAME=results[0].meta('NAME'))
            res.create_series(groups.keys())
            x = 0
            for d in zip_longest(*groups.values()):
                data = {}
                for k,v in zip(groups.keys(), d):
                    data[k] = self._combine_data(v, s['data'], s.get('combine_mode', 'mean'), config.get('cutoff', None)) if v is not None else None
                res.append_datapoint(x, data)
                x += 1
            new_results.append(res)
        new_series = []
        for k in groups.keys():
            new_series.append({'data': k, 'label': k})
        config['series'] = new_series

        return new_results

def BothCombiner(Combiner):

    # group_by == 'both' means that the group names should be split by a
    # delimiter (currently '-') and the first part specifies the group, the
    # second the series. Currently only works if there's just one series
    # name configured in the plot config.
    def group(groups):
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
            res = ResultSet(TITLE=s,NAME=results[0].meta('NAME'))
            res.create_series(series_names)
            x = 0
            for d in zip_longest(*[g[1] for g in groups.items() if g[0].endswith("-%s" % s)]):
                data = {}
                for k,v in zip([k.rsplit("-",1)[0] for k in groups.keys() if k.endswith("-%s" % s)], d):
                    data[k] = self._combine_data(v, old_s['data'], old_s.get('combine_mode', 'mean'), config.get('cutoff', None)) if v is not None else None
                res.append_datapoint(x, data)
                x += 1
            new_results.append(res)
        config['series'] = new_series

        return new_results

def Reducer(object):
    filter_none = True
    def __init__(self, settings):
        self.settings = settings

    def reduce(self, data):
        if self.settings.COMBINE_CUTOFF:
            start,end = cycle(self.settings.COMBINE_CUTOFF)[:2]
            end = -int(end/self.settings.STEP_SIZE)
            if end == 0:
                end = None
            data = data[int(start/self.settings.STEP_SIZE):end]
        if self.filter_none:
            data = [p for p in data if p is not None]
        if not data:
            return None
        return self._reduce(data)


class MeanReducer(Reducer):
    def _reduce(self, data):
        return numpy.mean(data)

class MedianReducer(Reducer):
    def _reduce(self, data):
        return numpy.median(data)

class MinReducer(Reducer):
    def _reduce(self, data):
        return numpy.mean(data)

class MaxReducer(Reducer):
    def _reduce(self, data):
        return numpy.mean(data)

class SpanReducer(Reducer):
    def _reduce(self, data):
        return max(data)-min(data)

class MeanSpanReducer(Reducer):
    def _reduce(self, data):
        min_val = min(data)
        d = [i-min_val for i in data]
        return self.np.mean(d)

class MeanZeroReducer(Reducer):
    filter_none = False
    def _reduce(self, data):
        d = [p if p is not None else 0 for p in data]
        return self.np.mean(d) if d else None

    def _combine_data(self, resultset, key, combine_mode, cutoff=None, d=None):
        if d is None:
            d = resultset[key]
        if cutoff is not None:
            # cut off values from the beginning and end before doing the
            # plot; for e.g. pings that run long than the streams, we don't
            # want the unloaded ping values
            start,end = cutoff
            end = -int(end/self.settings.STEP_SIZE)
            if end == 0:
                end = None
            d = d[int(start/self.settings.STEP_SIZE):end]
        if combine_mode in ('mean', 'median', 'min', 'max'):
            d = [p for p in d if p is not None]
            return getattr(self.np, combine_mode)(d) if d else None
        elif combine_mode == 'span':
            d = [p for p in d if p is not None]
            return self.np.max(d)-self.np.min(d) if d else None
        elif combine_mode == 'mean_span':
            d = [p for p in d if p is not None]
            if not d:
                return None
            min_val = min(d)
            d = [i-min_val for i in d]
            return self.np.mean(d)
        elif combine_mode == 'mean_zero':
            d = [p if p is not None else 0 for p in d]
            return self.np.mean(d) if d else None
        elif combine_mode.startswith('meta:'):
            metakey = combine_mode.split(":", 1)[1]
            try:
                return resultset.meta('SERIES_META')[key][metakey]
            except KeyError:
                return None
