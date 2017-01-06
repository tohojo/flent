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

from logging import StreamHandler, FileHandler

class MaxFilter(object):

    def __init__(self, maxlvl):
        self.maxlvl = maxlvl

    def filter(self, record):
        if record.levelno > self.maxlvl:
            return 0
        return 1


def get_logger(name):
    return logging.getLogger(name)


def setup_console():
    logger = logging.getLogger()

    err = StreamHandler(sys.stderr)
    err.setLevel(logging.WARNING)
    fmt = logging.Formatter(fmt="%(levelname)s: %(message)s")
    err.setFormatter(fmt)
    logger.addHandler(err)

    out = StreamHandler(sys.stdout)
    out.setLevel(logging.INFO)
    fmt = logging.Formatter(fmt="%(message)s")
    out.setFormatter(fmt)
    filt = MaxFilter(logging.INFO)
    out.addFilter(filt)
    logger.addHandler(out)

    logger.setLevel(logging.INFO)


def setup_null():
    logger = logging.getLogger()
    handler = logging.NullHandler()
    logger.addHandler(handler)


def setup_file(filename):
    logger = logging.getLogger()

    handler = FileHandler(filename, encoding='utf-8')
    handler.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        fmt="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    handler.setFormatter(fmt)
    logger.addHandler(handler)

    logger.setLevel(logging.DEBUG)
