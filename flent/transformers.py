# -*- coding: utf-8 -*-
#
# tranformers.py
#
# Author:   Toke Høiland-Jørgensen (toke@toke.dk)
# Date:     24 October 2012
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

try:
    import numpy as np
except ImportError:
    np = None


def transform_results(results, func):
    """Transform a list of (timestamp,value) pairs by applying a function to the
    value."""
    try:
        for i in range(len(results)):
            results[i][1] = func(results[i][1])
    except TypeError:
        # Transformers can also be applied to metadata items, in which case
        # calling len() on results will result in a TypeError. So just try to
        # call the function on the value itself.
        return func(results)
    return results


def rr_to_ms(results):
    """Transforms a transactions/second netperf RR measurement into ping times
    in milliseconds."""

    if hasattr(results, "shape"):
        return 1000 / results

    def safe_divide(x):
        if x == 0:
            return None
        return 1000.0 / x
    return transform_results(results, safe_divide)


def s_to_ms(results):
    if hasattr(results, "shape"):
        return results * 1000.0
    return transform_results(results, lambda x: x * 1000.0)


def bits_to_mbits(results):
    if hasattr(results, "shape"):
        return results / 1000000.0
    return transform_results(results, lambda x: x / 1000000.0)


def kbits_to_mbits(results):
    if hasattr(results, "shape"):
        return results / 1000.0
    return transform_results(results, lambda x: x / 1000.0)


def cumulative_to_events(results):
    """Transform cumulative counter values into the increasing events."""
    if hasattr(results, "shape") and np is not None:
        # Need output array same length as input array
        arr = np.zeros(len(results), dtype=float)
        arr[1:] = np.diff(results)
        return arr

    try:
        current = results[0][1]
        res = []
        for t, v in results:
            res.append((t, v - current))
            current = v
        return res
    except (TypeError, IndexError):
        return results


def identity(results):
    return results
