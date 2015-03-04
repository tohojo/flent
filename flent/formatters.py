## -*- coding: utf-8 -*-
##
## formatters.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:     16 October 2012
## Copyright (c) 2012-2015, Toke Høiland-Jørgensen
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

import json, sys, csv, math, inspect, os, re, io

from .util import cum_prob, frange, classname, long_substr
from .resultset import ResultSet
from .build_info import DATA_DIR, VERSION
from functools import reduce
from itertools import product,cycle,islice
try:
    from itertools import izip_longest as zip_longest
except ImportError:
    from itertools import zip_longest
try:
    from collections import OrderedDict
except ImportError:
    from flent.ordereddict import OrderedDict

def new(settings):
    formatter_name = classname(settings.FORMAT, 'Formatter')
    if not formatter_name in globals():
        raise RuntimeError("Formatter not found: '%s'." % settings.FORMAT)
    try:
        return globals()[formatter_name](settings)
    except RuntimeError:
        raise
    except Exception as e:
        raise RuntimeError("Error loading %s: %r." % (formatter_name, e))


class Formatter(object):

    open_mode = "wt"

    def __init__(self, settings):
        self.settings = settings
        self.check_output(self.settings.OUTPUT)

    def check_output(self, output):
        if hasattr(output, 'read') or output == "-":
            self.output = output
        else:
            # This logic is there to ensure that:
            # 1. If there is no write access, fail before running the tests.
            # 2. If the file exists, do not open (and hence overwrite it) until after the
            #    tests have run.
            if os.path.exists(output):
                # os.access doesn't work on non-existant files on FreeBSD; so only do the
                # access check on existing files (to avoid overwriting them before the tests
                # have completed).
                if not os.access(output, os.W_OK):
                    raise RuntimeError("No write permission for output file '%s'" % output)
                else:
                    self.output = output
            else:
                # If the file doesn't exist, just try to open it immediately; that'll error out
                # if access is denied.
                try:
                    self.output = io.open(output, self.open_mode)
                except IOError as e:
                    raise RuntimeError("Unable to open output file: '%s'" % e)

    def open_output(self):
        output = self.output
        if hasattr(output, 'read'):
            return
        if output == "-":
            self.output = sys.stdout
        else:
            try:
                self.output = io.open(output, self.open_mode)
            except IOError as e:
                raise RuntimeError("Unable to output data: %s" % e)

    def format(self, results):
        if results[0].dump_file is not None:
            sys.stderr.write("No output formatter selected.\nTest data is in %s (use with -i to format).\n" % results[0].dump_file)

    def write(self, string):
        try:
            self.output.write(string)
        except BrokenPipeError:
            pass

class NullFormatter(Formatter):
    def check_output(self, output):
        pass
    def format(self, results):
        pass

DefaultFormatter = Formatter

class TableFormatter(Formatter):

    def get_header(self, results):
        name = results[0].meta("NAME")
        keys = list(set(reduce(lambda x,y:x+y, [r.series_names for r in results])))
        header_row = [name]

        if len(results) > 1:
            for r in results:
                header_row += [k + ' - ' + r.label() for k in keys]
        else:
            header_row += keys
        return header_row

    def combine_results(self, results):
        """Generator to combine several result sets into one list of rows, by
        concatenating them."""
        keys = list(set(reduce(lambda x,y:x+y, [r.series_names for r in results])))
        for row in list(zip(*[list(r.zipped(keys)) for r in results])):
            out_row = [row[0][0]]
            for r in row:
                if r[0] != out_row[0]:
                    raise RuntimeError("x-value mismatch: %s/%s. Incompatible data sets?" % (out_row[0], r[0]))
                out_row += r[1:]
            yield out_row


class OrgTableFormatter(TableFormatter):
    """Format the output for an Org mode table. The formatter is pretty crude
    and does not align the table properly, but it should be sufficient to create
    something that Org mode can correctly realign."""

    def format(self, results):
        self.open_output()
        name = results[0].meta("NAME")

        if not results[0]:
            self.write(str(name) + " -- empty\n")
            return
        header_row = self.get_header(results)
        self.write("| " + " | ".join(header_row) + " |\n")
        self.write("|-" + "-+-".join(["-"*len(i) for i in header_row]) + "-|\n")

        def format_item(item):
            if isinstance(item, float):
                return "%.2f" % item
            return str(item)

        for row in self.combine_results(results):
            self.write("| ")
            self.write(" | ".join(map(format_item, row)))
            self.write(" |\n")



class CsvFormatter(TableFormatter):
    """Format the output as csv."""

    def format(self, results):
        self.open_output()
        if not results[0]:
            return

        writer = csv.writer(self.output)
        header_row = self.get_header(results)
        try:
            writer.writerow(header_row)

            def format_item(item):
                if item is None:
                    return ""
                return str(item)

            for row in self.combine_results(results):
                writer.writerow(list(map(format_item, row)))

        except BrokenPipeError:
            return

class StatsFormatter(Formatter):

    def __init__(self, settings):
        Formatter.__init__(self, settings)
        try:
            import numpy
            self.np = numpy
        except ImportError:
            raise RuntimeError("Stats formatter requires numpy, which seems to be missing. Please install it and try again.")

    def format(self, results):
        self.open_output()
        self.write("Warning: Totals are computed as cumulative sum * step size,\n"
                          "so spurious values wreck havoc with the results.\n")
        for r in results:
            self.write("Results %s" % r.meta('TIME'))
            if r.meta('TITLE'):
                self.write(" - %s" % r.meta('TITLE'))
            self.write(":\n")

            for s in sorted(r.series_names):
                self.write(" %s:\n" % s)
                d = [i for i in r.series(s) if i]
                if not d:
                    self.write("  No data.\n")
                    continue
                cs = self.np.cumsum(d)
                units = self.settings.DATA_SETS[s]['units']
                self.write("  Data points: %d\n" % len(d))
                if units != "ms":
                    self.write("  Total:       %f %s\n" % (cs[-1]*r.meta('STEP_SIZE'),
                                                               units.replace("/s", "")))
                self.write("  Mean:        %f %s\n" % (self.np.mean(d), units))
                self.write("  Median:      %f %s\n" % (self.np.median(d), units))
                self.write("  Min:         %f %s\n" % (self.np.min(d), units))
                self.write("  Max:         %f %s\n" % (self.np.max(d), units))
                self.write("  Std dev:     %f\n" % (self.np.std(d)))
                self.write("  Variance:    %f\n" % (self.np.var(d)))


class PlotFormatter(Formatter):

    def __init__(self, settings):
        Formatter.__init__(self, settings)
        try:
            from . import plotters
            plotters.init_matplotlib(settings)
            self.plotters = plotters
        except ImportError:
            raise RuntimeError("Unable to plot -- matplotlib is missing! Please install it if you want plots.")

        self.figure = None
        self.init_plots()


    def init_plots(self):
        if self.figure is None:
            self.plotter = self.plotters.new(self.settings)
            self.plotter.init()
            self.figure = self.plotter.figure
        else:
            self.figure.clear()
            self.plotter = self.plotters.new(self.settings, self.figure)
            self.plotter.init()

    def _init_timeseries_combine_plot(self, config=None, axis=None):
        self._init_timeseries_plot(config, axis)

    def _init_bar_combine_plot(self, config=None, axis=None):
        self._init_bar_plot(config, axis)

    def _init_box_combine_plot(self, config=None, axis=None):
        self._init_box_plot(config, axis)

    def _init_ellipsis_combine_plot(self, config=None, axis=None):
        self._init_ellipsis_plot(config, axis)

    def _init_cdf_combine_plot(self, config=None, axis=None):
        self._init_cdf_plot(config, axis)

    def do_timeseries_combine_plot(self, results, config=None, axis=None):
        return self.do_combine_many_plot(self.do_timeseries_plot, results, config, axis)

    def do_bar_combine_plot(self, results, config=None, axis=None):
        return self.do_combine_many_plot(self.do_bar_plot, results, config, axis)

    def do_box_combine_plot(self, results, config=None, axis=None):
        self.do_combine_many_plot(self.do_box_plot, results, config, axis)

    def do_ellipsis_combine_plot(self, results, config=None, axis=None):
        self.do_combine_many_plot(self.do_ellipsis_plot, results, config, axis)

    def do_cdf_combine_plot(self, results, config=None, axis=None):
        self.do_combine_many_plot(self.do_cdf_plot, results, config, axis)

    # Match a word of all digits, optionally with a non-alphanumeric character
    # preceding or succeeding it. For instance a series of files numbered as
    # -01, -02, etc.
    serial_regex = re.compile(r'\W?\b\d+\b\W?')
    def do_combine_many_plot(self, callback, results, config=None, axis=None):

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
        new_results = []
        filenames = [r.meta('DATA_FILENAME').replace(r.SUFFIX, '') for r in results]
        for r in self.settings.FILTER_REGEXP:
            filenames = [re.sub(r, "", f) for f in filenames]
        prefix = long_substr(filenames, prefix_only=True)
        names = map(lambda s: self.serial_regex.sub("", s.replace(prefix, ""), count=1), filenames)
        for i,n in enumerate(names):
            if n in groups:
                groups[n].append(results[i])
            else:
                groups[n] = [results[i]]


        group_by = config.get('group_by', 'groups')
        # group_by == 'groups' means preserve the data series and group the data
        # by the data groups identified above -- i.e. they become the items in
        # the legend.
        if group_by == 'groups':
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

        # groups_points means group by groups, but do per-point combinations, to
        # e.g. create a data series that is the mean of several others
        elif group_by == 'groups_points':
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

        # groups_concat means group by groups, but concatenate the points of all
        # the groups, e.g. to create a combined CDF of all data points
        elif group_by == 'groups_concat':
            for k in groups.keys():
                title = "%s (n=%d)" % (k, len(groups[k])) if self.settings.COMBINE_PRINT_N else k
                res = ResultSet(TITLE=title, NAME=results[0].meta('NAME'))
                res.create_series([s['data'] for s in config['series']])
                cutoff = config.get('cutoff', None)
                if cutoff is not None:
                    # cut off values from the beginning and end before doing the
                    # plot; for e.g. pings that run long than the streams, we don't
                    # want the unloaded ping values
                    start,end = cutoff
                    end = int(end/self.settings.STEP_SIZE)
                x = 0
                for r in groups[k]:
                    keys , minvals = [], {}
                    for s in config['series']:
                        k = s['data']
                        keys.append(k)
                        if s.get('combine_mode', None) == 'span' and k in r:
                            minvals[k] = min([d for d in r.series(k) if d is not None])
                        else:
                            minvals[k] = None
                    n = 0
                    for p in r.zipped(keys):
                        if n > start and n < len(r)-end:
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
                        n += 1
                new_results.append(res)

        # group_by == 'series' means flip the group and series, so the groups
        # become the entries on the x axis, while the series become the new
        # groups (in the legend)
        elif group_by == 'series':
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

        # group_by == 'both' means that the group names should be split by a
        # delimiter (currently '-') and the first part specifies the group, the
        # second the series. Currently only works if there's just one series
        # name configured in the plot config.
        elif group_by == 'both':
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

        config['cutoff'] = None

        return callback(new_results, config, axis)

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
        elif combine_mode == 'raw_seq_loss':
            if '::' in key:
                key = key.split("::")[0]
            try:
                if cutoff is not None:
                    start,end = cutoff
                    start_t = min([r['t'] for r in resultset.raw_values[key]])+start
                    end_t = max([r['t'] for r in resultset.raw_values[key]])-end
                    seqs = [r['seq'] for r in resultset.raw_values[key] if r['t'] > start_t and r['t'] < end_t]
                else:
                    seqs = [r['seq'] for r in resultset.raw_values[key]]
                return 1-len(seqs)/(max(seqs)-min(seqs)+1)
            except KeyError:
                return None
        elif combine_mode.startswith('meta:'):
            metakey = combine_mode.split(":", 1)[1]
            try:
                return resultset.meta('SERIES_META')[key][metakey]
            except KeyError:
                return None
        else:
            raise RuntimeError("Unknown combine mode: %s" % combine_mode)

    def format(self, results):
        if not results[0]:
            return

        self.plotter.subplot_combine_disabled = False
        self.plotter.plot(results)
        self.plotter.save(results)


class MetadataFormatter(Formatter):

    def format(self, results):
        self.open_output()
        self.write(json.dumps([r.serialise_metadata() for r in results], indent=4) + "\n")
