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

import optparse, ConfigParser, sys

import aggregators, formatters, util

parser = optparse.OptionParser(description='Wrapper to run concurrent netperf instances',
                               usage="usage: %prog [options] config")

parser.add_option("-o", "--output", action="store", type="string", dest="output",
                  help="file to write output to (default standard out)")
parser.add_option("-f", "--format", action="store", type="string", dest="format",
                  help="override config file output format")

parser.set_defaults(output="-")


config = ConfigParser.ConfigParser({'delay': 0})
config.add_section('global')
config.set('global', 'name', 'Netperf')
config.set('global', 'iterations', '1')
config.set('global', 'output', 'org_table')
config.set('global', 'cmd_opts', '-P 0 -v 0')
config.set('global', 'cmd_binary', '/usr/bin/netperf')


if __name__ == "__main__":
    try:

        (options,args) = parser.parse_args()
        if len(args) < 1:
            parser.error("Missing config file.")
        try:
            with open(args[0]) as fp:
                config.readfp(fp)
        except IOError:
            parser.error("Config file '%s' not found" % args[0])
        except ConfigParser.Error:
            parser.error("Unable to parse config file '%s'" % args[0])

        if options.format is not None:
            config.set('global', 'output', options.format)

        aggregator_name = config.get('global', 'aggregator')
        classname = util.classname(aggregator_name, "Aggregator")
        if hasattr(aggregators, classname):
            agg = getattr(aggregators, classname)(dict(config.items('global')))
        else:
            parser.error("Aggregator not found: '%s'" % aggregator_name)

        for s in config.sections():
            if s.startswith('test_'):
                agg.add_instance(dict(config.items(s)))

        results = agg.aggregate()
        formatter_name = util.classname(config.get('global', 'output'), 'Formatter')
        if hasattr(formatters, formatter_name):
            formatter = getattr(formatters, formatter_name)(options.output)
            formatter.format(config.get('global', 'name'), results)

    except RuntimeError, e:
        sys.stderr.write(u"Error occurred: %s\n"% unicode(e))
        sys.exit(1)
