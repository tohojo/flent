# -*- coding: utf-8 -*-
#
# test_aggregators.py
#
# Author:   ooonea <35407790+ooonea@users.noreply.github.com>
# Date:      9 June 2026
# Copyright (c) 2026, ooonea
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

import unittest

from flent import resultset, aggregators
from flent.settings import parser, Settings, DEFAULT_SETTINGS


class TestTimeseriesAggregator(unittest.TestCase):

    def _aggregate(self, measurements, step=0.2):
        settings = parser.parse_args(args=[],
                                     namespace=Settings(DEFAULT_SETTINGS))
        settings.STEP_SIZE = step
        settings.TOTAL_LENGTH = 10

        agg = aggregators.TimeseriesAggregator(settings)
        # Inject crafted measurements in place of running actual runners, so we
        # can exercise the interpolation logic in isolation.
        agg.collect = lambda: (measurements,
                               {"series": {}, "test_parameters": {}},
                               {})

        results = resultset.ResultSet(NAME="test-aggregators",
                                      DATA_FILENAME="test-aggregators",
                                      TEST_PARAMETERS={})
        return agg.aggregate(results)

    def test_interpolation_across_none_gap(self):
        # A None value in the middle of a series is a gap, as produced by sparse
        # netperf output at low rates combined with latency (see issue #265).
        # The None must not be used as a linear-interpolation anchor, which used
        # to raise "TypeError: unsupported operand type(s) for -: 'NoneType' and
        # 'float'". The gap should be preserved as None in the output series.
        measurements = {
            "TCP upload": [(0.0, 1.0), (0.2, 2.0), (0.4, None),
                           (0.6, 4.0), (0.8, 5.0)],
        }

        results = self._aggregate(measurements)

        data = results.series("TCP upload")
        self.assertTrue(data, "aggregator produced no data points")
        self.assertIn(None, data, "the data gap should be preserved as None")
        self.assertTrue(any(v is not None for v in data),
                        "valid data points should still be interpolated")


test_suite = unittest.TestLoader().loadTestsFromTestCase(TestTimeseriesAggregator)


if __name__ == "__main__":
    unittest.main()
