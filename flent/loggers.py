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

err_handler = out_handler = cache_handler = None
logfiles = set()
START_MARKER = "-- OUTPUT START -->"
END_MARKER = "<-- OUTPUT END --"

DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING

ENCODING = "UTF-8"
try:
    import locale
    ENCODING = locale.getpreferredencoding(False)
except:
    pass


class FilterAll(object):

    def filter(self, record):
        return 0


class MaxFilter(object):

    def __init__(self, maxlvl):
        self.maxlvl = maxlvl

    def filter(self, record):
        if record.levelno > self.maxlvl:
            return 0
        return 1


class NamePrefixFilter(object):

    def __init__(self, prefix):
        self.prefix = prefix

    def filter(self, record):
        if record.name.startswith(self.prefix):
            return 0
        return 1


class LevelDemoteFilter(object):

    def __init__(self, maxlevel):
        self.maxlevel = maxlevel

    def filter(self, record):
        if record.levelno > self.maxlevel:
            record.levelno = self.maxlevel
        return 1


class LogFormatter(Formatter):
    def __init__(self, fmt=None, datefmt=None, output_markers=None):
        self.format_exceptions = True

        if output_markers is not None:
            self.start_marker, self.end_marker = output_markers
        else:
            self.start_marker = self.end_marker = None
        super(LogFormatter, self).__init__(fmt, datefmt)

    def formatException(self, ei):
        if not self.format_exceptions:
            return ""

        # A string already formatted - passed through a pipe
        if hasattr(ei, "upper"):
            return ei

        return super(LogFormatter, self).formatException(ei)

    def format(self, record):
        s = super(LogFormatter, self).format(record)

        if self.start_marker is None:
            return s

        if hasattr(record, 'output'):
            if s[-1:] != "\n":
                s = s + "\n"
            output = record.output
            s = s + self.start_marker + output + self.end_marker

        elif hasattr(record, 'runner'):
            if s[-1:] != "\n":
                s = s + "\n"

            s = s + "Runner class: %s\n" % record.runner.__class__.__name__
            s = s + "Command: %s\n" % record.runner.command
            s = s + "Return code: %s\n" % record.runner.returncode
            s = s + "Stdout: " + self.start_marker + record.runner.out + \
                self.end_marker + "\n"
            s = s + "Stderr: " + self.start_marker + record.runner.err + \
                self.end_marker

        return s


class Handler(logging.Handler):

    def get_format_exceptions(self):
        return self.formatter.format_exceptions

    def set_format_exceptions(self, val):
        self.formatter.format_exceptions = val

    format_exceptions = property(get_format_exceptions,
                                 set_format_exceptions)


class QueueHandler(Handler):

    def __init__(self, queue, level=logging.NOTSET):
        super(QueueHandler, self).__init__(level=level)
        self.queue = queue

    def emit(self, record):
        if record.exc_info:
            # The log formatter will use the cached exc_text in place of the
            # exc_info Traceback object; since Traceback objects can't be
            # pickled, use this to pass over the formatted exception text
            # instead.
            fmt = Formatter()
            record.exc_info = fmt.formatException(record.exc_info)
        self.queue.put(record)

    def write(self, m):
        pass


class CachingHandler(Handler):
    def __init__(self, level=logging.NOTSET, max_entries=200):
        super(CachingHandler, self).__init__(level=level)
        self.max_entries = 200
        self.cache = []

    def emit(self, record):
        self.cache.append(record)

        while len(self.cache) > self.max_entries:
            self.cache.pop(0)

    def replay(self, handler):
        for r in self.cache:
            if r.levelno >= handler.level:
                handler.handle(r)

    def write(self, m):
        pass


def get_logger(name):
    return logging.getLogger(name)


def setup_console():
    global err_handler, out_handler, cache_handler

    if err_handler is not None:
        return

    logger = logging.getLogger()

    err_handler = StreamHandler(sys.stderr)
    err_handler.setLevel(logging.WARNING)
    fmt = LogFormatter(fmt="%(levelname)s: %(message)s",
                       output_markers=("", ""))
    fmt.format_exceptions = False
    err_handler.setFormatter(fmt)
    logger.addHandler(err_handler)

    out_handler = StreamHandler(sys.stdout)
    out_handler.setLevel(logging.INFO)
    out_handler.setFormatter(LogFormatter(fmt="%(message)s"))
    out_handler.addFilter(MaxFilter(logging.INFO))
    add_common_filters(out_handler)
    logger.addHandler(out_handler)

    cache_handler = CachingHandler()
    logger.addHandler(cache_handler)

    logger.setLevel(logging.DEBUG)

    logging.captureWarnings(True)
    logging.getLogger("py.warnings").addFilter(LevelDemoteFilter(DEBUG))
    logging.getLogger("matplotlib.font_manager").addFilter(FilterAll())


def set_console_level(level):
    logger = logging.getLogger()

    out_handler.setLevel(level)
    logger.setLevel(min(logger.level, level))


def setup_null():
    logger = logging.getLogger()
    handler = logging.NullHandler()
    logger.addHandler(handler)


def add_common_filters(handler):
    handler.addFilter(NamePrefixFilter("PyQt"))


def setup_logfile(filename, level=DEBUG, maxlevel=None, replay=True):
    if filename in logfiles:
        return
    logfiles.add(filename)

    logger = logging.getLogger()

    handler = FileHandler(filename, encoding='utf-8')
    add_common_filters(handler)
    handler.setLevel(level)
    fmt = LogFormatter(
        fmt="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        output_markers=(START_MARKER, END_MARKER))
    handler.setFormatter(fmt)

    if maxlevel:
        filt = MaxFilter(maxlevel)
        handler.addFilter(filt)

    logger.addHandler(handler)
    logger.setLevel(min(logger.level, level))

    if replay and cache_handler is not None:
        cache_handler.replay(handler)

    return handler


def remove_log_handler(handler):
    if not handler:
        return

    handler.flush()
    logger = logging.getLogger()
    logger.removeHandler(handler)


def add_log_handler(handler, replay=True):
    logger = logging.getLogger()
    fmt = LogFormatter(
        fmt="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S")
    handler.setFormatter(fmt)
    add_common_filters(handler)

    logger.addHandler(handler)
    logger.setLevel(min(logger.level, handler.level))

    if replay and cache_handler is not None:
        cache_handler.replay(handler)


def set_queue_handler(queue):
    logger = logging.getLogger()
    for h in logger.handlers[:]:
        logger.removeHandler(h)

    handler = QueueHandler(queue)
    logger.addHandler(handler)

    logging.captureWarnings(True)
    logging.getLogger("py.warnings").addFilter(LevelDemoteFilter(DEBUG))


def enable_exceptions():
    if err_handler is not None:
        err_handler.formatter.format_exceptions = True
