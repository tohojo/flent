# -*- coding: utf-8 -*-
#
# loggers.py
#
# Author:   Toke Høiland-Jørgensen (toke@toke.dk)
# Date:      6 January 2017
# Copyright (c) 2017, Toke Høiland-Jørgensen
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

import logging
import sys

from logging import StreamHandler, FileHandler, Formatter

err_handler = out_handler = None
START_MARKER = "-- OUTPUT START -->"
END_MARKER = "<-- OUTPUT END --"


class MaxFilter(object):

    def __init__(self, maxlvl):
        self.maxlvl = maxlvl

    def filter(self, record):
        if record.levelno > self.maxlvl:
            return 0
        return 1


class LogFormatter(Formatter):
    def __init__(self, fmt=None, datefmt=None, format_output=False):
        self.format_exceptions = True
        self.format_output = format_output
        super(LogFormatter, self).__init__(fmt, datefmt)

    def disable_exceptions(self):
        self.format_exceptions = False

    def formatException(self, ei):
        if self.format_exceptions:
            return super(LogFormatter, self).formatException(ei)
        return ""

    def format(self, record):
        s = super(LogFormatter, self).format(record)

        if not self.format_output:
            return s

        if hasattr(record, 'output'):
            if s[-1:] != "\n":
                s = s + "\n"
            s = s + START_MARKER + record.output + END_MARKER

        elif hasattr(record, 'runner'):
            if s[-1:] != "\n":
                s = s + "\n"

            s = s + "Runner class: %s\n" % record.runner.__class__.__name__
            s = s + "Command: %s\n" % record.runner.command
            s = s + "Return code: %s\n" % record.runner.returncode
            s = s + "Stdout: " + START_MARKER + record.runner.out + \
                END_MARKER + "\n"
            s = s + "Stderr: " + START_MARKER + record.runner.err + END_MARKER

        return s


def get_logger(name):
    return logging.getLogger(name)


def setup_console():
    global err_handler, out_handler

    if err_handler is not None:
        return

    logger = logging.getLogger()

    err_handler = StreamHandler(sys.stderr)
    err_handler.setLevel(logging.WARNING)
    fmt = LogFormatter(fmt="%(levelname)s: %(message)s")
    err_handler.setFormatter(fmt)
    logger.addHandler(err_handler)

    out_handler = StreamHandler(sys.stdout)
    out_handler.setLevel(logging.INFO)
    fmt = LogFormatter(fmt="%(message)s")
    out_handler.setFormatter(fmt)
    filt = MaxFilter(logging.INFO)
    out_handler.addFilter(filt)
    logger.addHandler(out_handler)

    logger.setLevel(logging.INFO)


def setup_null():
    logger = logging.getLogger()
    handler = logging.NullHandler()
    logger.addHandler(handler)


def setup_file(filename):
    logger = logging.getLogger()

    handler = FileHandler(filename, encoding='utf-8')
    handler.setLevel(logging.DEBUG)
    fmt = LogFormatter(
        fmt="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        format_output=True)
    handler.setFormatter(fmt)
    logger.addHandler(handler)

    logger.setLevel(logging.DEBUG)


def disable_exceptions():
    if err_handler is not None:
        err_handler.formatter.disable_exceptions()
