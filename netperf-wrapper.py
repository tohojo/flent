## -*- coding: utf-8 -*-
##
## netperf-wrapper.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:     October 8th, 2012
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

# Wrapper to run multiple concurrent netperf instances, in several iterations,
# and aggregate the result.

import optparse, sys, os

import aggregators, formatters, util
from settings import settings, load



config = util.DefaultConfigParser({'delay': 0})
config.add_section('global')
config.set('global', 'name', 'Netperf')
config.set('global', 'iterations', '1')
config.set('global', 'output', 'org_table')
config.set('global', 'cmd_opts', '-P 0 -v 0')
config.set('global', 'cmd_binary', '/usr/bin/netperf')


if __name__ == "__main__":
    try:
        settings,results = load()

        aggregator_name = settings.AGGREGATOR
        classname = util.classname(aggregator_name, "Aggregator")
        if hasattr(aggregators, classname):
            agg = getattr(aggregators, classname)()
        else:
            raise RuntimeError("Aggregator not found: '%s'" % aggregator_name)

        for s in settings.DATA_SETS.items():
            agg.add_instance(*s)

        formatter_name = util.classname(settings.FORMAT, 'Formatter')
        if hasattr(formatters, formatter_name):
            formatter = getattr(formatters, formatter_name)(settings.OUTPUT)
        else:
            raise RuntimeError("Formatter not found.")

        if not results:
            results = agg.postprocess(agg.aggregate(results))
            results.dump_dir(os.path.dirname(settings.OUTPUT) or ".")
        formatter.format(results)

    except RuntimeError, e:
        sys.stderr.write(u"Error occurred: %s\n"% unicode(e))
        sys.exit(1)
    except KeyboardInterrupt:
        sys.stderr.write(u"Interrupted\n")
        sys.exit(1)
