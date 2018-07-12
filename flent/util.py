# -*- coding: utf-8 -*-
#
# util.py
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

import argparse
import bz2
import fnmatch
import gzip
import io
import os
import re
import shlex
import socket
import time

from copy import copy
from calendar import timegm
from datetime import datetime
from math import log10, exp, sqrt

from flent.loggers import get_logger

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

logger = get_logger(__name__)


def uscore_to_camel(s):
    """Turn a underscore style string (org_table) into a CamelCase style string
    (OrgTable) for class names."""
    return ''.join(x.capitalize() for x in s.split("_"))


def classname(s, suffix=''):
    return uscore_to_camel(s) + suffix


def format_date(dt, fmt="%Y-%m-%dT%H:%M:%S.%f", utc=False):
    if utc:
        return dt.strftime(fmt + "Z")
    # The datetime object is already UTC, so use gmtime rather than mktime to
    # get the timestamp from which to compute the UTC offset.
    ts = timegm(dt.timetuple()) + dt.microsecond / 1000000.0
    offset = datetime.fromtimestamp(ts) - datetime.utcfromtimestamp(ts)
    return (dt + offset).strftime(fmt)


def format_bytes(nbytes):
    if nbytes > 2**30:
        return (2**30, 'Gbytes')
    elif nbytes > 2**20:
        return (2**20, 'Mbytes')
    elif nbytes > 2**10:
        return (1**10, 'Kbytes')
    else:
        return (nbytes, 'bytes')


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
        return dt - offset


def clean_path(path, allow_dirs=False):
    if allow_dirs:
        return re.sub("[^A-Za-z0-9_/-]", "_", path)
    else:
        return re.sub("[^A-Za-z0-9_-]", "_", path)


def long_substr(data, prefix_only=False):
    """Find the longest common substring between a list of strings.
    Optionally limit search to prefixes only.

    Brute force approach (i.e. not very efficient...).
    Based on https://stackoverflow.com/questions/2892931/longest-common-substring-from-more-than-two-strings-python"""  # noqa: E501
    substr = ''
    if len(data) > 1 and len(data[0]) > 0:
        if prefix_only:
            start_pos = [0]
        else:
            start_pos = range(len(data[0]))
        for i in start_pos:
            for j in range(len(data[0]) - i + 1):
                if j > len(substr) and all(data[0][i:i + j] in x for x in data):
                    substr = data[0][i:i + j]
    return substr


def diff_parts(strings, sep):
    """Return the unique parts of a set of strings by splitting on
    a separator and pruning parts that are identical for all strings"""

    parts = [s.split(sep) for s in strings]
    np = [p for p in zip(*parts) if len(set(p)) >= 1]

    return [sep.join(p) for p in zip(*np)]


def is_executable(filename):
    return os.path.isfile(filename) and os.access(filename, os.X_OK)


def which(executable, fail=None):
    pathname, filename = os.path.split(executable)
    if pathname:
        if is_executable(executable):
            logger.debug("which: %s is a full path and executable", executable)
            return executable
    else:
        for path in [i.strip('""') for i in os.environ["PATH"].split(os.pathsep)]:
            filename = os.path.join(path, executable)
            if is_executable(filename):
                logger.debug("which: Found %s executable at %s",
                             executable, filename)
                return filename
            else:
                logger.debug("which: %s is not an executable file", filename)

    if fail:
        raise fail("No %s binary found in PATH." % executable)
    return None


def path_components(path):
    folders = []
    while path and path != "/":
        path, folder = os.path.split(path)

        if folder:
            folders.insert(0, folder)
    if path == "/":
        folders.insert(0, path)
    return folders


def lookup_host(hostname, version=None):
    logger.debug("Looking up hostname '%s'.", hostname)
    if version == 4:
        version = socket.AF_INET
    elif version == 6:
        version = socket.AF_INET6
    else:
        version = socket.AF_UNSPEC
    try:
        hostnames = socket.getaddrinfo(hostname, None, version,
                                       socket.SOCK_STREAM)
    except Exception:
        hostnames = None

    if not hostnames:
        raise RuntimeError("Found no hostnames on lookup of %s" % hostname)

    return hostnames[0]


# In Python 2.6, the GzipFile object does not have a 'closed' property, which
# makes the io module blow up when trying to close it. This tidbit tries to
# detect that and substitute a subclass that does have the property, while not
# touching anything if the property is already present.
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
        # monkey-patching required to make gzip object compatible with
        # TextIOWrapper in Python 3.1.
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
            if default == self._NoDefault:
                raise
            else:
                return default

    def getint(self, section, option, default=_NoDefault):
        try:
            return configparser.ConfigParser.getint(self, section, option)
        except configparser.NoOptionError:
            if default == self._NoDefault:
                raise
            else:
                return default

    def getfloat(self, section, option, default=_NoDefault):
        try:
            return configparser.ConfigParser.getfloat(self, section, option)
        except configparser.NoOptionError:
            if default == self._NoDefault:
                raise
            else:
                return default

    def getboolean(self, section, option, default=_NoDefault):
        try:
            return configparser.ConfigParser.getboolean(self, section, option)
        except configparser.NoOptionError:
            if default == self._NoDefault:
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

    def __repr__(self):
        return "<Glob: %s (excl: %s)>" % (self.pattern, ",".join(self.exclude))

    def filter(self, values, exclude, args=None):
        if args is not None:
            pattern = self.pattern.format(**args)
        else:
            pattern = self.pattern

        # Exclude * from matching :, make ** match everything
        re_pat = fnmatch.translate(pattern)
        re_pat = re_pat.replace(".*.*", ":::PLACEHOLDER:::")
        re_pat = re_pat.replace(".*", "[^:]*")
        re_pat = re_pat.replace(":::PLACEHOLDER:::", ".*")
        regex = re.compile(re_pat)

        exclude += self.exclude
        return (x for x in values if regex.match(x) and
                not any((fnmatch.fnmatch(x, e) for e in exclude)))

    def __iter__(self):
        return iter((self,))  # allow list(g) to return [g]

    @classmethod
    def filter_dict(cls, d, args=None):
        # Expand glob patterns in parameters. Go through all items in the
        # dictionary looking for subkeys that is a Glob instance or a list
        # that has a Glob instance in it.
        for k, v in list(d.items()):
            for g_k in list(v.keys()):
                try:
                    v[g_k] = cls.expand_list(
                        v[g_k], list(d.keys()), [k], args=args)
                except TypeError:
                    continue
        return d

    @classmethod
    def expand_list(cls, l, values, exclude=None, args=None):
        l = list(l)  # copy list, turns lone Glob objects into [obj]
        new_l = []
        if exclude is None:
            exclude = []
        # Expand glob patterns in list. Go through all items in the
        # list  looking for Glob instances and expanding them.
        for pattern in l:
            if isinstance(pattern, cls):
                new_l.extend(pattern.filter(values, exclude, args))
            else:
                new_l.append(pattern)
        return new_l


def mos_score(T, loss):
    """Calculate a MOS score based on a one-way delay and a packet loss rate.
    Based on ITU G.107 06/2015.

    Verified against the online reference implementation at
    https://www.itu.int/ITU-T/studygroups/com12/emodelv1/calcul.php

    This version assumes the default values are used for all parameters other
    than delay and loss.

    @T: Mean one-way delay
    @loss: Packet loss rate between 0 and 1.

    """

    # All variable names are from G.107.

    # Parameters
    Ta = T
    Tr = 2 * T
    Ppl = loss * 100  # in percent

    # Defaults
    mT = 100  # Table 1

    # From Table 3:
    WEPL = 110
    TELR = 65
    RLR = 2
    SLR = 8

    # Constants calculated from the Table 3 defaults:
    No = -61.17921438624169  # (7-3)
    Ro = 15 - (1.5 * (SLR + No))  # (7-2)
    Is = 1.4135680813438616  # (7-8)

    Rle = 10.5 * (WEPL + 7) * pow(Tr + 1, -0.25)  # (7-26)
    if Ta == 0:
        X = 0
    else:
        X = log10(Ta / mT) / log10(2)  # (7-28)

    if Ta <= 100:
        Idd = 0
    else:
        Idd = 25 * ((1 + X**6)**(1 / 6) - 3 *
                    (1 + (X / 3)**6)**(1 / 6) + 2)  # (7-27)

    Idle = (Ro - Rle) / 2 + sqrt((Ro - Rle)**2 / 4 + 169)  # (7-25)

    TERV = TELR - 40 * log10((1 + T / 10) / (1 + T / 150)) + \
        6 * exp(-0.3 * T**2)  # (7-22)
    Roe = -1.5 * (No - RLR)  # (7-20)
    Re = 80 + 2.5 * (TERV - 14)  # (7-21)

    if T < 1:
        Idte = 0
    else:
        Idte = ((Roe - Re) / 2 + sqrt((Roe - Re)**2 / 4 + 100) - 1) * \
            (1 - exp(-T))  # (7-19)

    Id = Idte + Idle + Idd  # (7-18)

    Ieeff = 95 * (Ppl / (Ppl + 1))  # (7-29) with BurstR = Bpl = 1

    R = Ro - Is - Id - Ieeff

    if R < 0:
        MOS = 1
    elif R > 100:
        MOS = 4.5
    else:
        MOS = 1 + 0.035 * R + R * (R - 60) * (100 - R) * 7 * 10**-6  # (B-4)

    return MOS


# Argparse stuff

class FuncAction(argparse.Action):

    def __init__(self, option_strings, dest, help=None):
        super(FuncAction, self).__init__(option_strings,
                                         dest,
                                         nargs=0,
                                         required=False,
                                         help=help)


class Update(argparse.Action):

    def __init__(self, *args, **kwargs):
        if 'default' not in kwargs:
            kwargs['default'] = {}
        super(Update, self).__init__(*args, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        if not hasattr(namespace, self.dest):
            setattr(namespace, self.dest, self.default)
        getattr(namespace, self.dest).update(values)


def float_pair(value):
    try:
        if "," not in value:
            return (None, float(value))
        a, b = [s.strip() for s in value.split(",", 1)]
        return (float(a) if a else None,
                float(b) if b else None)
    except ValueError:
        raise argparse.ArgumentTypeError("Invalid pair value: %s" % value)


def keyval(value):
    ret = {}
    for p in token_split(value, ";"):
        p = p.strip()
        if not p:
            continue
        try:
            k, v = token_split(p, '=')
            ret.update({k.strip(): v.strip()})
        except ValueError:
            raise argparse.ArgumentTypeError(
                "Invalid value '%s' (missing =)" % p)
    return ret


def keyval_int(value):
    try:
        return {int(k): v for k, v in keyval(value).items()}
    except ValueError:
        raise argparse.ArgumentTypeError("Keys must be integers.")


def comma_list(value):
    try:
        return [v.strip() for v in token_split(value)]
    except ValueError:
        raise argparse.ArgumentTypeError("Unable to split into list.")


def token_split(value, split_tokens=',;'):
    """Split VALUE on the tokens given in SPLIT_TOKENS, while
    avoiding splitting of quoted strings"""

    lex = shlex.shlex(value, posix=True)
    lex.whitespace_split = True
    lex.whitespace = split_tokens
    return list(lex)


class ArgParam(object):
    """A class that takes an argparser and sets object properties from
    the argparser-defined parameters."""

    params = None

    def __init__(self, **kwargs):
        if self.params:
            for a in self.params._actions:
                dest = a.dest.lower()
                if dest in kwargs:
                    setattr(self, dest, copy(kwargs[dest]))
                elif a.dest in kwargs:
                    setattr(self, dest, copy(kwargs[a.dest]))
                else:
                    setattr(self, dest, copy(a.default))


class ArgParser(argparse.ArgumentParser):

    def get_type(self, dest):
        for action in self._actions:
            if action.dest == dest:
                # Workaround because StoreConst actions don't store the action
                # type
                if isinstance(action, argparse._StoreConstAction):
                    return type(action.const)
                return action.type
        return None

    def get_choices(self, dest):
        for action in self._actions:
            if action.dest == dest and action.choices:
                return action.choices

        return None

    def is_list(self, dest):
        for action in self._actions:
            if action.dest == dest:
                return isinstance(action, argparse._AppendAction)
        return False

    def __contains__(self, dest):
        for action in self._actions:
            if action.dest == dest:
                return True
        return False
