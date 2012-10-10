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

import subprocess, shlex, optparse, ConfigParser, threading, time, pprint, math

parser = optparse.OptionParser(description='Wrapper to run concurrent netperf instances',
                               usage="usage: %prog [options] config")

#parser.add_option('config', type=unicode, help='config file defining the netperf instances')


config = ConfigParser.ConfigParser({'delay': 0})
config.add_section('global')
config.set('global', 'name', 'Netperf')
config.set('global', 'iterations', '1')
config.set('global', 'output', 'org_table')
config.set('global', 'cmd_opts', '-P 0 -v 0')
config.set('global', 'cmd_binary', '/usr/bin/netperf')

class ProcessRunner(threading.Thread):
    """Default process runner for any process."""

    def __init__(self, binary, options, delay, *args, **kwargs):
        threading.Thread.__init__(self,*args, **kwargs)
        self.binary = binary
        self.options = options
        self.delay = delay
        self.result = None

    def run(self):
        """Runs the configured job. If a delay is set, wait for that many
        seconds, then open the subprocess, wait for it to finish, and collect
        the last word of the output (whitespace-separated)."""

        if self.delay:
            time.sleep(self.delay)
        args = [self.binary] + shlex.split(self.options)
        prog = subprocess.Popen(args,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         universal_newlines=True)
        out,err=prog.communicate()
        self.result = self.parse(out)

    def parse(self, output):
        """Default parser returns the last (whitespace-separated) word of
        output."""

        return output.split()[-1].strip()


class NetperfDemoRunner(ProcessRunner):
    """Runner for netperf demo mode."""

    def parse(self, output):
        """Parses the interim result lines and returns a list of (time,value)
        pairs."""

        result = []
        lines = output.split("\n")
        for line in lines:
            if line.startswith("Interim"):
                parts = line.split()
                result.append([float(parts[9]), float(parts[2])])

        return result

runners = {
    'default': ProcessRunner,
    'netperf_demo': NetperfDemoRunner}

class Aggregator(object):
    """Basic aggregator. Runs all jobs and returns their result."""

    def __init__(self, config):
        self.iterations = int(config['iterations'])
        self.binary = config['cmd_binary']
        self.global_options = config['cmd_opts']
        self.default_runner = config.get('runner', 'default')
        self.instances = {}

    def add_instance(self, config):
        self.instances[config['name']] = {
            'options': self.global_options + " " + config.get('cmd_opts', ''),
            'delay': float(config.get('delay', 0)),
            'runner': runners[config.get('runner', self.default_runner)],
            'binary': config.get('binary', self.binary)}

    def aggregate(self):
        """Create a ProcessRunner thread for each instance and start them. Wait
        for the threads to exit, then collect the results."""

        result = {}
        threads = {}
        for n,i in self.instances.items():
            threads[n] = i['runner'](i['binary'], i['options'], i['delay'])
            threads[n].start()
        for n,t in threads.items():
            t.join()
            result[n] = t.result

        return result

class IterationAggregator(Aggregator):
    """Iteration aggregator. Runs the jobs multiple times and aggregates the
    results. Assumes each job outputs one value."""

    def aggregate(self):
        results = []
        for i in range(self.iterations):
            results.append(("Run %d"%(i+1), Aggregator.aggregate(self)))
        return results

class TimeseriesAggregator(Aggregator):
    """Time series aggregator. Runs the jobs (which are all assumed to output a
    series of timed entries) and combines the times onto a single timeline,
    aligning values to the same time steps (interpolating values as necessary).
    Assumes each job outputs a list of pairs (time, value) where the times and
    values are floating point values."""

    def __init__(self, config):
        self.step = float(config['step'])
        self.max_distance = float(config['max_distance'])
        Aggregator.__init__(self, config)

    def aggregate(self):
        measurements = Aggregator.aggregate(self)
        results = []

        # We start steps at the minimum time value, and do as many steps as are
        # necessary to get past the maximum time value with the selected step
        # size
        t_0 = min([i[0][0] for i in measurements.values()])
        t_max = max([i[-1][0] for i in measurements.values()])
        steps = int(math.ceil((t_max-t_0)/self.step))

        time_labels = []

        for s in range(steps):
            time_labels.append(self.step*s)
            t = t_0 + self.step*s

            # for each step we need to find the interpolated measurement value
            # at time t by interpolating between the nearest measurements before
            # and after t
            result = {}
            # n is the name of this measurement (from the config), r is the list
            # of measurement pairs (time,value)
            for n,r in measurements.items():
                t_prev = v_prev = None
                t_next = v_next = None
                for i in range(len(r)):
                    if r[i][0] > t:
                        if i > 0:
                            t_prev,v_prev = r[i-1]
                        t_next,v_next = r[i]
                        break
                if t_prev is None:
                    # The first data point for this measurement is after the
                    # current t. Don't interpolate, just use the value if it is
                    # within the max distance.
                    if t_next is None or abs(t-t_next) > self.max_distance:
                        result[n] = None
                    else:
                        result[n] = v_next
                else:
                    # We found the previous and next values; interpolate between
                    # them. We assume that the rate of change dv/dt is constant
                    # in the interval, and so can be calculated as
                    # (v_next-v_prev)/(t_next-t_prev). Then the value v_t at t
                    # can be calculated as v_t=v_prev + dv/dt*(t-t_prev)

                    dv_dt = (v_next-v_prev)/(t_next-t_prev)
                    result[n] = v_prev + dv_dt*(t-t_prev)
            results.append(result)

        return zip(time_labels, results)

aggregators = {
    'iteration': IterationAggregator,
    'timeseries': TimeseriesAggregator}

def format_pprint(name, results):
    """Use the pprint pretty-printing module to just print out the contents of
    the results list."""

    print name
    pprint.pprint(results)

def format_org_table(name, results):
    """Format the output for an Org mode table. The formatter is pretty crude
    and does not align the table properly, but it should be sufficient to create
    something that Org mode can correctly realign."""

    if not results:
        print name, "-- empty"
    first_row = results[0][1]
    header_row = [name] + sorted(first_row.keys())
    print "| " + " | ".join(header_row) + " |"
    print "|-" + "-+-".join(["-"*len(i) for i in header_row]) + "-|"
    for i,row in results:
        print "| %s |" % i,
        for c in header_row[1:]:
            if isinstance(row[c], float):
                print "%.2f |" % row[c],
            else:
                print row[c], "|",
        print

formatters = {'org_table': format_org_table,
              'pprint': format_pprint}

if __name__ == "__main__":

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

    aggregator_name = config.get('global', 'aggregator')
    if aggregator_name in aggregators:
        agg = aggregators[aggregator_name](dict(config.items('global')))
    else:
        parser.error("Aggregator not found: '%s'" % aggregator_name)

    for s in config.sections():
        if s.startswith('test_'):
            agg.add_instance(dict(config.items(s)))

    results = agg.aggregate()
    formatter = config.get('global', 'output')
    if formatter in formatters:
        formatters[formatter](config.get('global', 'name'),
                              results)
