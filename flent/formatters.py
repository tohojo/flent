# -*- coding: utf-8 -*-
#
# formatters.py
#
# Author:   Toke Høiland-Jørgensen (toke@toke.dk)
# Date:     16 October 2012
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

import csv
import io
import os
import sys

from functools import reduce

from flent import plotters, combiners
from flent.util import classname, format_bytes
from flent.loggers import get_logger

try:
    import ujson as json
except ImportError:
    import json

logger = get_logger(__name__)


def new(settings):
    formatter_name = classname(settings.FORMAT, 'Formatter')
    if formatter_name not in globals():
        raise RuntimeError("Formatter not found: '%s'." % settings.FORMAT)
    logger.debug("Creating new %s", formatter_name)
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
            # 2. If the file exists, do not open (and hence overwrite it) until
            #    after the tests have run.
            if os.path.exists(output):
                # os.access doesn't work on non-existant files on FreeBSD; so
                # only do the access check on existing files (to avoid
                # overwriting them before the tests have completed).
                if not os.access(output, os.W_OK):
                    raise RuntimeError(
                        "No write permission for output file '%s'" % output)
                else:
                    self.output = output
            else:
                # If the file doesn't exist, just try to open it immediately;
                # that'll error out if access is denied.
                try:
                    self.output = io.open(output, self.open_mode)
                except IOError as e:
                    raise RuntimeError("Unable to open output file: '%s'" % e)

    def __del__(self):
        if hasattr(self.output, 'close'):
            self.output.close()

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
        if results[0].dump_filename is not None:
            logger.info(
                "No output formatter selected.\nTest data is in %s "
                "(use with -i to format).", results[0].dump_filename)

    def write(self, string):
        try:
            self.output.write(string)
        except BrokenPipeError:
            pass

    def verify(self):
        return True, None


class NullFormatter(Formatter):

    def check_output(self, output):
        pass

    def format(self, results):
        pass

    def __del__(self):
        pass


class TableFormatter(Formatter):

    def get_header(self, results):
        name = results[0].meta("NAME")
        keys = list(
            set(reduce(lambda x, y: x + y, [r.series_names for r in results])))
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
        keys = list(
            set(reduce(lambda x, y: x + y, [r.series_names for r in results])))
        for row in list(zip(*[list(r.zipped(keys)) for r in results])):
            out_row = [row[0][0]]
            for r in row:
                if r[0] != out_row[0]:
                    raise RuntimeError(
                        "x-value mismatch: %s/%s. Incompatible data sets?"
                        % (out_row[0], r[0]))
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
        self.write("|-" + "-+-".join(["-" * len(i) for i in header_row]) + "-|\n")

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


class CombiningFormatter(Formatter):

    def make_combines(self, results, modes):
        # The calls here are a bit awkward because the combiners were
        # originally tailored to plotting; but the benefit is that we can
        # re-use the same code that is used to make combination plots for
        # this summary output, ensuring consistency and feature parity.
        comb = combiners.new('groups',
                             data_cutoff=self.settings.DATA_CUTOFF)
        series = []
        for s in results.series_names:
            series.append({'data': s})

        self.combined_res = {}
        for m in modes:
            self.combined_res[m] = comb([results], {'series': series},
                                        combine_mode=m)[0]

    def get_res(self, series, mode):
        if mode == 'N':
            # The combiners store the pre-reduction N values in a special
            # series_meta specifically this usage
            return self.combined_res['mean'].series_meta(series, 'orig_n')[0]

        if mode not in self.combined_res:
            return 0

        return self.combined_res[mode][series][0]


class StatsFormatter(CombiningFormatter):

    def __init__(self, settings):
        Formatter.__init__(self, settings)
        try:
            import numpy
            self.np = numpy
        except ImportError:
            raise RuntimeError(
                "Stats formatter requires numpy, which seems to be missing. "
                "Please install it and try again.")

    def format(self, results):
        self.open_output()
        self.write("Warning: Totals are computed as cumulative sum * step size,\n"
                   "so spurious values wreck havoc with the results.\n")
        for r in results:
            self.write("Results %s" % r.meta('TIME'))
            if r.meta('TITLE'):
                self.write(" - %s" % r.meta('TITLE'))
            self.write(":\n")

            self.make_combines(r, ['mean', 'median', 'min', 'max',
                                   'std', 'var', 'cumsum'])

            for s in sorted(r.series_names):
                self.write(" %s:\n" % s)
                if not self.get_res(s, 'mean'):
                    self.write("  No data.\n")
                    continue

                if s in self.settings.DATA_SETS:
                    units = self.settings.DATA_SETS[s]['units']
                else:
                    units = ''
                self.write("  Data points: %d\n" % self.get_res(s, 'N'))
                if units != "ms":
                    self.write("  Total:       %f %s\n" % (
                        self.get_res(s, 'cumsum'),
                        units.replace("/s", "")))
                self.write("  Mean:        %f %s\n" % (self.get_res(s, 'mean'), units))
                self.write("  Median:      %f %s\n" % (self.get_res(s, 'median'), units))
                self.write("  Min:         %f %s\n" % (self.get_res(s, 'min'), units))
                self.write("  Max:         %f %s\n" % (self.get_res(s, 'max'), units))
                self.write("  Std dev:     %f\n" % (self.get_res(s, 'std')))
                self.write("  Variance:    %f\n" % (self.get_res(s, 'var')))

class StatsCsvFormatter(CombiningFormatter):

    combines = {'mean': 'mean', 'median': 'median',
                'min': 'min', 'max': 'max',
                'std': 'std_dev', 'var': 'variance',
                'cumsum': 'cumul_total'}

    def __init__(self, settings):
        Formatter.__init__(self, settings)
        try:
            import numpy
            self.np = numpy
        except ImportError:
            raise RuntimeError(
                "Stats formatter requires numpy, which seems to be missing. "
                "Please install it and try again.")

    def format(self, results):
        self.open_output()
        writer = csv.writer(self.output)

        try:
            writer.writerow(["filename", "title", "series", "units", "datapoints"] +
                            list(self.combines.values()))

            for r in results:
                if r.meta('TITLE'):
                    rtitle = "{} - {}".format(r.meta('TIME'), r.meta('TITLE'))
                else:
                    rtitle = "{}".format(r.meta('TIME'))

                self.make_combines(r, self.combines.keys())

                for s in sorted(r.series_names):
                    if s in self.settings.DATA_SETS:
                        units = self.settings.DATA_SETS[s]['units']
                    else:
                        units = ''

                    row = [r.meta('DATA_FILENAME'), rtitle, s, units,
                           self.get_res(s, 'N')]

                    if not self.get_res(s, 'mean'):
                        writer.writerow(row)
                    else:
                        writer.writerow(row + [self.get_res(s, k)
                                               for k in self.combines.keys()])
        except BrokenPipeError:
            return

class SummaryFormatter(CombiningFormatter):

    COL_WIDTH = 12

    def __init__(self, settings):
        Formatter.__init__(self, settings)

    def format(self, results):
        self.open_output()
        for r in results:
            self.write("\nSummary of %s test run from %s" % (r.meta('NAME'),
                                                             r.meta("TIME")))
            if r.meta('TITLE'):
                self.write("\n  Title: '%s'" % r.meta('TITLE'))
            if self.settings.DATA_CUTOFF:
                self.write("\n  Cut data to interval: [%.2f, %.2f]" %
                           self.settings.DATA_CUTOFF)
            self.write("\n\n")

            if 'FROM_COMBINER' in r.meta():
                m = {}
            else:
                m = r.meta().get("SERIES_META", {})

            txtlen = max([len(n) for n in r.series_names])
            unit_len = max((len(s['units']) for s in
                            self.settings.DATA_SETS.values()))

            self.write("{spc:{txtlen}s} {avg:>{width}s}"
                       " {med:>{width}s} {datapoints:>{lwidth}s}\n".format(
                           spc="", avg="avg", med="median",
                           datapoints="# data pts", txtlen=txtlen + 3,
                           width=self.COL_WIDTH,
                           lwidth=self.COL_WIDTH + unit_len))

            self.make_combines(r, ['mean', 'median'])
            for s in sorted(r.series_names):
                self.write((" %-" + str(txtlen) + "s : ") % s)
                try:
                    d = [i[1] for i in r.raw_series(s) if i[1] is not None]
                except KeyError:
                    d = None

                if not d:
                    d = [i for i in r.series(s) if i is not None]

                md = m.get(s, {})

                units = (md.get('UNITS') or
                         self.settings.DATA_SETS.get(s, {}).get('units', ''))

                mean = self.get_res(s, 'mean')
                median = self.get_res(s, 'median')
                n = self.get_res(s, 'N')
                is_computed = 'COMPUTED_LATE' in m.get(s, {})

                if mean is None:
                    self.write("No data.\n")
                    continue

                if mean and units == 'bytes':
                    factor, units = format_bytes(max(mean, median))
                    mean /= factor
                    median /= factor

                if mean is not None:
                    self.write("{0:{width}.2f} ".format(mean,
                                                        width=self.COL_WIDTH))
                else:
                    self.write("{0:>{width}}".format("N/A", width=self.COL_WIDTH))

                if median is not None and not is_computed:
                    self.write("{0:{width}.2f} {1}".format(median, units,
                                                           width=self.COL_WIDTH))
                else:
                    self.write("{0:>{width}} {1}".format("N/A", units,
                                                         width=self.COL_WIDTH))

                self.write("{0:{width}d}\n".format(n,
                                                   width=(self.COL_WIDTH +
                                                          unit_len - len(units))))


DefaultFormatter = SummaryFormatter


class PlotFormatter(Formatter):

    def __init__(self, settings):
        Formatter.__init__(self, settings)
        plotters.init_matplotlib(settings.OUTPUT, settings.USE_MARKERS,
                                 settings.LOAD_MATPLOTLIBRC)
        self.plotters = plotters

        self.figure = None
        self.plotter = None

    def init_plots(self, results=None):
        if self.figure is not None:
            self.figure.clear()
            self.plotter.disable_cleanup = True
            self.plotter.disconnect_callbacks()

        if self.settings.SUBPLOT_COMBINE:
            self.plotter = self.plotters.new(self.settings,
                                             plotter=self.plotters.get_plotter(
                                                 "subplot_combine"),
                                             figure=self.figure,
                                             results=results)
        else:
            self.plotter = self.plotters.new(self.settings,
                                             figure=self.figure,
                                             results=results)

        self.figure = self.plotter.figure
        self.plotter.init()

    @property
    def disable_cleanup(self):
        return self.plotter.disable_cleanup

    @disable_cleanup.setter
    def disable_cleanup(self, val):
        self.plotter.disable_cleanup = val

    def format(self, results):
        if not results[0]:
            logger.debug("Zero-length result, not plotting")
            return

        self.init_plots(results)
        self.plotter.plot(results)
        self.plotter.save(results)

    def verify(self):
        return self.plotter.verify()


class MetadataFormatter(Formatter):

    def format(self, results):
        self.open_output()
        self.write(json.dumps([r.serialise_metadata()
                               for r in results], indent=4) + "\n")
