## -*- coding: utf-8 -*-
##
## tranformers.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:     24 October 2012
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

def transform_results(results, func):
    """Transform a list of (timestamp,value) pairs by applying a function to the
    value."""
    for i in range(len(results)):
        results[i][1] = func(results[i][1])
    return results

def rr_to_ms(results):
    """Transforms a transactions/second netperf RR measurement into ping times
    in milliseconds."""
    def safe_divide(x):
        if x == 0:
            return None
        return 1000.0/x
    return transform_results(results, safe_divide)

def s_to_ms(results):
    return transform_results(results, lambda x: x*1000.0)
