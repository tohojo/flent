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

import ConfigParser, math
from bisect import bisect_left
from datetime import datetime

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
def cum_prob(data, val):
    return bisect_left(data, val)/float(len(data))

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
  return (limit1 + n*increment for n in xrange(count))

class DefaultConfigParser(ConfigParser.ConfigParser):
    class _NoDefault(object):
        pass

    def get(self, section, option, default=_NoDefault):
        try:
            return ConfigParser.ConfigParser.get(self, section, option)
        except ConfigParser.NoOptionError:
            if default==self._NoDefault:
                raise
            else:
                return default

    def getint(self, section, option, default=_NoDefault):
        try:
            return ConfigParser.ConfigParser.getint(self, section, option)
        except ConfigParser.NoOptionError:
            if default==self._NoDefault:
                raise
            else:
                return default

    def getfloat(self, section, option, default=_NoDefault):
        try:
            return ConfigParser.ConfigParser.getfloat(self, section, option)
        except ConfigParser.NoOptionError:
            if default==self._NoDefault:
                raise
            else:
                return default

    def getboolean(self, section, option, default=_NoDefault):
        try:
            return ConfigParser.ConfigParser.getboolean(self, section, option)
        except ConfigParser.NoOptionError:
            if default==self._NoDefault:
                raise
            else:
                return default
