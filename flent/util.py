## -*- coding: utf-8 -*-
##
## util.py
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

import math, os, gzip, bz2, io, socket, re, time
from bisect import bisect_left
from datetime import datetime
from calendar import timegm
from fnmatch import fnmatch

ENCODING = "UTF-8"
try:
    import locale
    ENCODING = locale.getpreferredencoding(False)
except:
    pass

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

def format_date(dt, fmt="%Y-%m-%dT%H:%M:%S.%f", utc=False):
    if utc:
        return dt.strftime(fmt+"Z")
    # The datetime object is already UTC, so use gmtime rather than mktime to
    # get the timestamp from which to compute the UTC offset.
    ts = timegm(dt.timetuple()) + dt.microsecond / 1000000.0
    offset = datetime.fromtimestamp(ts) - datetime.utcfromtimestamp(ts)
    return (dt+offset).strftime(fmt)

def parse_date(timestring):
    try:
        # Try to parse the straight UTC time string (has a Z at the end)
        return datetime.strptime(timestring, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        try:
            dt = datetime.strptime(timestring, "%Y-%m-%dT%H:%M:%S.%f")
        except ValueError:
            dt = datetime.strptime(timestring, "%Y-%m-%dT%H:%M:%S")
        # The timestamp is in local time, so get the (UTC) timestamp and
        # subtract the time zone offset at that time to get the UTC datetime
        # object.
        ts = time.mktime(dt.timetuple())
        offset = datetime.fromtimestamp(ts) - datetime.utcfromtimestamp(ts)
        return dt-offset

def clean_path(path, allow_dirs=False):
    if allow_dirs:
        return re.sub("[^A-Za-z0-9_/-]", "_", path)
    else:
        return re.sub("[^A-Za-z0-9_-]", "_", path)


def long_substr(data, prefix_only=False):
    """Find the longest common substring between a list of strings.
    Optionally limit search to prefixes only.

    Brute force approach (i.e. not very efficient...).
    Based on https://stackoverflow.com/questions/2892931/longest-common-substring-from-more-than-two-strings-python"""
    substr = ''
    if len(data) > 1 and len(data[0]) > 0:
        if prefix_only:
            start_pos = [0]
        else:
            start_pos = range(len(data[0]))
        for i in start_pos:
            for j in range(len(data[0])-i+1):
                if j > len(substr) and all(data[0][i:i+j] in x for x in data):
                    substr = data[0][i:i+j]
    return substr


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

def which(executable, fail=False):
    pathname, filename = os.path.split(executable)
    if pathname:
        if is_executable(executable):
            return executable
    else:
        for path in [i.strip('""') for i in os.environ["PATH"].split(os.pathsep)]:
            filename = os.path.join(path, executable)
            if is_executable(filename):
                return filename

    if fail:
        raise RuntimeError("No %s binary found in PATH." % executable)
    return None

def path_components(path):
    folders = []
    while path and path != "/":
        path, folder = os.path.split(path)

        if folder:
            folders.insert(0,folder)
    if path == "/":
        folders.insert(0,path)
    return folders

def lookup_host(hostname, version=None):
    if version == 4:
        version = socket.AF_INET
    elif version == 6:
        version = socket.AF_INET6
    else:
        version = socket.AF_UNSPEC
    hostnames = socket.getaddrinfo(hostname, None, version,
                                   socket.SOCK_STREAM)
    if not hostnames:
        raise RuntimeError("Found no hostnames on lookup of %s" % h)

    return hostnames[0]

# In Python 2.6, the GzipFile object does not have a 'closed' property, which makes
# the io module blow up when trying to close it. This tidbit tries to detect that
# and substitute a subclass that does have the property, while not touching
# anything if the property is already present.
if hasattr(gzip.GzipFile, "closed"):
    _gzip_open = gzip.open
else:
    class GzipFile(gzip.GzipFile):
        def get_closed(self):
            return self.fileobj is None
        # Setter needed for python3.1-compatibility
        def set_closed(self, closed):
            self._closed = closed
        closed = property(get_closed, set_closed)
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

if hasattr(bz2, 'open'):
    bz2_open = bz2.open
else:
    # compatibility with io.TextIOWrapper for Python 2
    class bz2file(bz2.BZ2File):
        def readable(self):
            return 'r' in self.mode
        def writable(self):
            return 'w' in self.mode
        def seekable(self):
            return True
        def flush(self):
            pass

    def bz2_open(filename, mode='rb', compresslevel=9):
        bz_mode = mode.replace("t", "")
        binary_file = bz2file(filename, bz_mode, compresslevel=compresslevel)
        if "t" in mode:
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


class Glob(object):
    """Object for storing glob patterns in matches"""

    def __init__(self, pattern, exclude=None):
        if exclude is None:
            self.exclude = []
        else:
            self.exclude = exclude
        self.pattern = pattern

    def filter(self, values, exclude):
        exclude += self.exclude
        return [x for x in values if fnmatch(x, self.pattern) and x not in exclude]

    def __iter__(self):
        return iter((self,)) # allow list(g) to return [g]

    @classmethod
    def filter_dict(cls, d):
        # Expand glob patterns in parameters. Go through all items in the
        # dictionary looking for subkeys that is a Glob instance or a list
        # that has a Glob instance in it.
        for k,v in list(d.items()):
            for g_k in list(v.keys()):
                try:
                    v[g_k] = cls.expand_list(v[g_k], list(d.keys()), [k])
                except TypeError:
                    continue
        return d

    @classmethod
    def expand_list(cls, l, values, exclude=None):
        l = list(l) # copy list, turns lone Glob objects into [obj]
        if exclude is None:
            exclude = []
        # Expand glob patterns in list. Go through all items in the
        # list  looking for Glob instances and expanding them.
        for i in range(len(l)):
            pattern = l[i]
            if isinstance(pattern, cls):
                l[i:i+1] = pattern.filter(values, exclude)
        return l
