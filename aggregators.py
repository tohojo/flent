## -*- coding: utf-8 -*-
##
## aggregators.py
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

import math

import runners, transformers

from util import classname

class Aggregator(object):
    """Basic aggregator. Runs all jobs and returns their result."""

    def __init__(self, config):
        self.iterations = int(config['iterations'])
        self.binary = config['cmd_binary']
        self.global_options = config['cmd_opts']
        self.default_runner = config.get('runner', 'default')
        self.instances = {}

    def add_instance(self, name, config):
        instance = {
            'options': self.global_options + " " + config.get('cmd_opts', ''),
            'delay': float(config.get('delay', 0)),
            'runner': getattr(runners, classname(config.get('runner', self.default_runner), 'Runner')),
            'binary': config.get('cmd_binary', self.binary)}

        # If an instance has the separate_opts set, do not combine the command
        # options with the global options.
        if config.get('separate_opts', False):
            instance['options'] = config.get('cmd_opts', '')

        if 'data_transform' in config and hasattr(transformers, config['data_transform']):
            instance['transformer'] = getattr(transformers, config['data_transform'])
        self.instances[name] = instance

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
            if t.result is None:
                continue
            elif 'transformer' in self.instances[n]:
                result[n] = self.instances[n]['transformer'](t.result)
            else:
                result[n] = t.result

        return result

class IterationAggregator(Aggregator):
    """Iteration aggregator. Runs the jobs multiple times and aggregates the
    results. Assumes each job outputs one value."""

    def aggregate(self):
        results = []
        for i in range(self.iterations):
            results.append(((i+1), Aggregator.aggregate(self)))
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
                if t_next is None:
                    t_next,v_next = r[-1]
                if t_prev is None:
                    # The first data point for this measurement is after the
                    # current t. Don't interpolate, just use the value if it is
                    # within the max distance.
                    if abs(t-t_next) > self.max_distance:
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
