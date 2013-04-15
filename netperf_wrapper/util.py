## -*- coding: utf-8 -*-
##
## util.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:     16 oktober 2012
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

import math, os, gzip, io
from bisect import bisect_left
from datetime import datetime

try:
    import configparser
except ImportError:
    import ConfigParser as configparser

try:
    import configparser
except ImportError:
    import ConfigParser as configparser

def uscore_to_camel(s):
    """Turn a underscore style string (org_table) into a CamelCase style string
    (OrgTable) for class names."""
    return ''.join(x.capitalize() for x in s.split("_"))

def classname(s, suffix=''):
    return uscore_to_camel(s)+suffix

def parse_date(timestring):
    try:
        return datetime.strptime(timestring, "%Y-%m-%dT%H:%M:%S.%f")
    except ValueError:
        return datetime.strptime(timestring, "%Y-%m-%dT%H:%M:%S")

# Calculate discrete cdf function using bisect_left.
def cum_prob(data, val, size):
    return bisect_left(data, val)/size

# from http://code.activestate.com/recipes/66472/
def frange(limit1, limit2 = None, increment = 1.):
  """
  Range function that accepts floats (and integers).

  Usage:
  frange(-2, 2, 0.1)
  frange(10)
  frange(10, increment = 0.5)

  The returned value is an iterator.  Use list(frange) for a list.
  """

  if limit2 is None:
    limit2, limit1 = limit1, 0.
  else:
    limit1 = float(limit1)

  count = int(math.ceil((limit2 - limit1)/increment))
  return (limit1 + n*increment for n in range(count))

def is_executable(filename):
    return os.path.isfile(filename) and os.access(filename, os.X_OK)

def which(executable):
    pathname, filename = os.path.split(executable)
    if pathname:
        if is_executable(executable):
            return executable
    else:
        for path in [i.strip('""') for i in os.environ["PATH"].split(os.pathsep)]:
            filename = os.path.join(path, executable)
            if is_executable(filename):
                return filename

    return None

# In Python 2.6, the GzipFile object does not have a 'closed' property, which makes
# the io module blow up when trying to close it. This tidbit tries to detect that
# and substitute a subclass that does have the property, while not touching
# anything if the property is already present.
if hasattr(gzip.GzipFile, "closed"):
    _gzip_open = gzip.open
else:
    class GzipFile(gzip.GzipFile):
        @property
        def closed(self):
            return self.fileobj is None
    _gzip_open = GzipFile

def gzip_open(filename, mode="rb"):
    """Compatibility layer for gzip to work in Python 3.1 and 3.2."""
    wrap_text = False
    if "t" in mode:
        wrap_text = True
        mode = mode.replace("t", "")
    binary_file = _gzip_open(filename, mode)

    if wrap_text:
        # monkey-patching required to make gzip object compatible with TextIOWrapper
        # in Python 3.1.
        if not hasattr(binary_file, "readable"):
            def readable():
                return binary_file.mode == gzip.READ
            binary_file.readable = readable
        if not hasattr(binary_file, "writable"):
            def writable():
                return binary_file.mode == gzip.WRITE
            binary_file.writable = writable
        if not hasattr(binary_file, "seekable"):
            def seekable():
                return True
            binary_file.seekable = seekable

        # This wrapping is done by the builtin gzip module in python 3.3.
        return io.TextIOWrapper(binary_file)
    else:
        return binary_file


class DefaultConfigParser(configparser.ConfigParser):
    class _NoDefault(object):
        pass

    def get(self, section, option, default=_NoDefault):
        try:
            return configparser.ConfigParser.get(self, section, option)
        except configparser.NoOptionError:
            if default==self._NoDefault:
                raise
            else:
                return default

    def getint(self, section, option, default=_NoDefault):
        try:
            return configparser.ConfigParser.getint(self, section, option)
        except configparser.NoOptionError:
            if default==self._NoDefault:
                raise
            else:
                return default

    def getfloat(self, section, option, default=_NoDefault):
        try:
            return configparser.ConfigParser.getfloat(self, section, option)
        except configparser.NoOptionError:
            if default==self._NoDefault:
                raise
            else:
                return default

    def getboolean(self, section, option, default=_NoDefault):
        try:
            return configparser.ConfigParser.getboolean(self, section, option)
        except configparser.NoOptionError:
            if default==self._NoDefault:
                raise
            else:
                return default
