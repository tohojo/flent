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

from flent import plotters
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


class StatsFormatter(Formatter):

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
                    self.write("  Total:       %f %s\n" % (
                        cs[-1] * r.meta('STEP_SIZE'),
                        units.replace("/s", "")))
                self.write("  Mean:        %f %s\n" % (self.np.mean(d), units))
                self.write("  Median:      %f %s\n" % (self.np.median(d), units))
                self.write("  Min:         %f %s\n" % (self.np.min(d), units))
                self.write("  Max:         %f %s\n" % (self.np.max(d), units))
                self.write("  Std dev:     %f\n" % (self.np.std(d)))
                self.write("  Variance:    %f\n" % (self.np.var(d)))


class SummaryFormatter(Formatter):

    COL_WIDTH = 12

    def __init__(self, settings):
        Formatter.__init__(self, settings)
        try:
            import numpy
            self.np = numpy
        except ImportError:
            self.np = None

    def format(self, results):
        self.open_output()
        for r in results:
            self.write("Summary of %s test run " % r.meta('NAME'))
            if r.meta('TITLE'):
                self.write("'%s' (at %s)" % (r.meta('TITLE'), r.meta("TIME")))
            else:
                self.write("at %s" % r.meta("TIME"))
            self.write(":\n\n")

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

            for s in sorted(r.series_names):
                self.write((" %-" + str(txtlen) + "s : ") % s)
                d = [i for i in r.series(s) if i is not None]

                median = mean = None

                if s in m and 'MEAN_VALUE' in m[s]:
                    mean = m[s]['MEAN_VALUE']
                elif not d:
                    self.write("No data.\n")
                    continue

                units = self.settings.DATA_SETS[s]['units'] if s in \
                    self.settings.DATA_SETS else ''

                if d and self.np is not None:
                    mean = self.np.mean(d) if not mean else mean
                    median = self.np.median(d)
                elif d:
                    mean = sum(d) / len(d) if not mean else mean
                    median = sorted(d)[len(d) // 2]

                if mean and units == 'bytes':
                    factor, units = format_bytes(max(mean, median))
                    mean /= factor
                    median /= factor

                if mean is not None:
                    self.write("{0:{width}.2f} ".format(mean,
                                                        width=self.COL_WIDTH))
                else:
                    self.write("{0:>{width}}".format("N/A", width=self.COL_WIDTH))

                if median is not None:
                    self.write("{0:{width}.2f} {1}".format(median, units,
                                                           width=self.COL_WIDTH))
                else:
                    self.write("{0:>{width}} {1}".format("N/A", units,
                                                         width=self.COL_WIDTH))

                self.write("{0:{width}d}\n".format(len(d),
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
        self.init_plots()

    def init_plots(self):
        if self.figure is None:
            self.plotter = self.plotters.new(self.settings)
            self.plotter.init()
            self.figure = self.plotter.figure
        else:
            self.figure.clear()
            self.plotter.disable_cleanup = True
            self.plotter.disconnect_callbacks()
            self.plotter = self.plotters.new(self.settings, figure=self.figure)
            self.plotter.init()

    @property
    def disable_cleanup(self):
        return self.plotter.disable_cleanup

    @disable_cleanup.setter
    def disable_cleanup(self, val):
        self.plotter.disable_cleanup = val

    def format(self, results):
        if not results[0]:
            return

        if self.settings.SUBPLOT_COMBINE:
            self.plotter.disable_cleanup = True
            self.plotter.disconnect_callbacks()
            self.figure.clear()
            self.plotter = self.plotters.new(self.settings,
                                             plotter=self.plotters.get_plotter(
                                                 "subplot_combine"),
                                             figure=self.figure)
            self.plotter.init()
        self.plotter.plot(results)
        self.plotter.save(results)


class MetadataFormatter(Formatter):

    def format(self, results):
        self.open_output()
        self.write(json.dumps([r.serialise_metadata()
                               for r in results], indent=4) + "\n")
