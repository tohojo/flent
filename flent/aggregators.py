# -*- coding: utf-8 -*-
#
# aggregators.py
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

import math
import pprint
import signal

from collections import OrderedDict
from datetime import datetime
from threading import Event

from flent import runners
from flent.util import classname
from flent.loggers import get_logger

logger = get_logger(__name__)


def new(settings):
    cname = classname(getattr(settings, 'AGGREGATOR', 'timeseries'),
                      "Aggregator")
    if cname not in globals():
        raise RuntimeError("Aggregator not found: '%s'" % settings.AGGREGATOR)
    try:
        agg = globals()[cname](settings)
        for s in list(settings.DATA_SETS.items()):
            agg.add_instance(*s)
        return agg
    except Exception as e:
        raise RuntimeError("Error loading %s: %s." % (cname, e))


class GracefulShutdown(Exception):
    pass


def handle_usr1(signal, frame):
    raise GracefulShutdown()


class Aggregator(object):
    """Basic aggregator. Runs all jobs and returns their result."""

    def __init__(self, settings):
        self.instances = OrderedDict()
        self.threads = OrderedDict()
        self.settings = settings
        self.failed_runners = 0
        self.runner_counter = 0
        self.killed = False

        self.postprocessors = []

    def add_instance(self, name, config):
        instance = dict(config)

        if name in self.instances:
            raise RuntimeError("Duplicate runner name: '%s' "
                               "(probably unsupported duplicate "
                               "parameters or hosts)" % name)

        if 'delay' not in instance:
            instance['delay'] = 0

        idx = self.runner_counter
        self.runner_counter += 1
        instance['idx'] = idx

        if idx in self.settings.REMOTE_HOSTS:
            instance['remote_host'] = self.settings.REMOTE_HOSTS[idx]
        elif '*' in self.settings.REMOTE_HOSTS:
            instance['remote_host'] = self.settings.REMOTE_HOSTS['*']
        else:
            instance['remote_host'] = None

        instance['runner'] = runners.get(instance['runner'])
        instance['start_event'] = None
        instance['kill_event'] = None
        instance['finish_event'] = Event()

        self.instances[name] = instance

    def aggregate(self, results):
        raise NotImplementedError()

    def collect(self):
        """Create a ProcessRunner thread for each instance and start them. Wait
        for the threads to exit, then collect the results."""

        signal.signal(signal.SIGUSR1, handle_usr1)

        result = {}
        metadata = {'series': {}, 'test_parameters': {}}
        raw_values = {}
        try:
            for n, i in list(self.instances.items()):
                if 'run_after' in i:
                    i['start_event'] = self.instances[i['run_after']]['finish_event']  # noqa: E501
                if 'kill_after' in i:
                    i['kill_event'] = self.instances[i['kill_after']]['finish_event']  # noqa: E501
                t = i['runner'](name=n, settings=self.settings, **i)
                try:
                    t.check()
                except runners.RunnerCheckError as e:
                    raise RuntimeError("Runner %s failed check: %s" % (n, e))

                self.threads[n] = t

            # Start in a separate loop once we're sure we successfully created
            # all runners
            for t in self.threads.values():
                t.start()

            shutting_down = False
            for n, t in list(self.threads.items()):
                while t.is_alive():
                    try:
                        t.join(1)
                    except GracefulShutdown:
                        if not shutting_down:
                            logger.info(
                                "SIGUSR1 received; initiating graceful shutdown. "
                                "This may take a while...")
                            self.kill_runners(graceful=True)
                            shutting_down = True
                        else:
                            logger.info(
                                "Already initiated graceful shutdown. "
                                "Patience, please...")

                metadata['series'][n] = t.metadata
                if t.test_parameters:
                    metadata['test_parameters'].update(t.test_parameters)
                raw_values[n] = t.raw_values

                if hasattr(t, 'compute_result'):
                    # The runner is a post-processor(Avg etc), and should be run
                    # as such (by the postprocess() method)
                    self.postprocessors.append(t.compute_result)
                elif t.result is None:
                    continue
                elif hasattr(t.result, 'keys'):
                    if not t.result:
                        self.failed_runners += 1
                    for k in t.result.keys():
                        key = "%s::%s" % (n, k)
                        result[key] = t.result[k]
                else:
                    if not t.result:
                        self.failed_runners += 1
                    result[n] = t.result

                for c in t.child_results:
                    for k, v in c.items():
                        key = "%s::%s" % (n, k)
                        if key in result:
                            raise RuntimeError(
                                "Duplicate key '%s' from child runner" % key)
                        result[key] = v

        except KeyboardInterrupt:
            logger.debug("Received SIGINT")
            self.kill_runners()
            raise

        logger.debug("Runner aggregation finished",
                     extra={'output': pprint.pformat(result)})

        signal.signal(signal.SIGUSR1, signal.SIG_DFL)
        return result, metadata, raw_values

    def kill_runners(self, graceful=False):
        self.killed = True
        for t in list(self.threads.values()):
            t.kill(graceful)

    def postprocess(self, result):
        logger.debug("Postprocessing data using %d postprocessors", len(self.postprocessors))
        for p in self.postprocessors:
            result = p(result)
        return result


class IterationAggregator(Aggregator):
    """Iteration aggregator. Runs the jobs multiple times and aggregates the
    results. Assumes each job outputs one value."""

    def __init__(self, *args, **kwargs):
        Aggregator.__init__(self, *args, **kwargs)
        self.iterations = self.settings.ITERATIONS

    def aggregate(self, results):
        for i in range(self.iterations):
            data, metadata, raw_values = self.collect()
            results.meta('SERIES_META', metadata['series'])
            results.meta('FAILED_RUNNERS', self.failed_runners)
            results.raw_values = raw_values
            if i == 0:
                results.create_series(data.keys())
            results.append_datapoint(i, data)
        return results


class TimeseriesAggregator(Aggregator):
    """Time series aggregator. Runs the jobs (which are all assumed to output a
    series of timed entries) and combines the times onto a single timeline,
    aligning values to the same time steps (interpolating values as necessary).
    Assumes each job outputs a list of pairs (time, value) where the times and
    values are floating point values."""

    def __init__(self, *args, **kwargs):
        Aggregator.__init__(self, *args, **kwargs)
        self.step = self.settings.STEP_SIZE
        self.max_distance = self.step * 5.0

    def aggregate(self, results):
        measurements, metadata, raw_values = self.collect()
        if self.killed:
            logger.debug("Aggregator was killed, skipping aggregation")
            return results
        if not measurements:
            raise RuntimeError("No data to aggregate. Run with -L and check log "
                               "file to investigate.")

        results.create_series(list(measurements.keys()))
        results.raw_values = raw_values

        results.meta('SERIES_META', metadata['series'])
        results.meta('TEST_PARAMETERS').update(metadata['test_parameters'])
        results.meta('FAILED_RUNNERS', self.failed_runners)

        # We start steps at the minimum time value, and do as many steps as are
        # necessary to get past the maximum time value with the selected step
        # size
        first_times = [i[0][0] for i in
                       list(measurements.values()) if i and i[0]]
        last_times = [i[-1][0] for i in
                      list(measurements.values()) if i and i[-1]]
        if not (first_times and last_times):
            raise RuntimeError("No data to aggregate. Run with -L and check log "
                               "file to investigate.")
        t_0 = min(first_times)
        t_max = max(last_times)
        t_total = t_max - t_0
        steps = int(math.ceil(t_total / self.step))

        if t_total > self.settings.TOTAL_LENGTH * 10:
            logger.warning("Data shows test duration %fs more than 10 times the expected %ds "
                           "- clock issue or buggy timestamps from test tool?",
                           t_total, self.settings.TOTAL_LENGTH)
        if steps > 10**6:
            raise RuntimeError("Refusing to iterate more than 1 million steps during aggregation (got %d)" % steps)

        results.meta('T0', datetime.utcfromtimestamp(t_0))

        for s in range(steps):
            time_label = self.step * s
            t = t_0 + self.step * s

            # for each step we need to find the interpolated measurement value
            # at time t by interpolating between the nearest measurements before
            # and after t
            result = {}
            # n is the name of this measurement (from the config), r is the list
            # of measurement pairs (time,value)
            for n, r in list(measurements.items()):
                max_dist = self.max_distance
                last = False
                if not r:
                    continue
                t_prev = v_prev = None
                t_next = v_next = None

                for i in range(len(r)):
                    if r[i][0] > t:
                        if i > 0:
                            t_prev, v_prev = r[i - 1]
                        else:
                            # minimum interpolation distance on first entry to
                            # avoid multiple interpolations to the same value
                            max_dist = self.step * 0.5
                        t_next, v_next = r[i]
                        break
                if t_next is None:
                    t_next, v_next = r[-1]
                    last = True
                if abs(t - t_next) <= max_dist:
                    if t_prev is None:
                        # The first/last data point for this measurement is
                        # after the current t. Don't interpolate, just use the
                        # value.
                        if last and results.last_datapoint(n) in (v_next, None):
                            # Avoid repeating last interpolation
                            result[n] = None
                        else:
                            result[n] = v_next
                    else:
                        # We found the previous and next values; interpolate
                        # between them. We assume that the rate of change dv/dt
                        # is constant in the interval, and so can be calculated
                        # as (v_next-v_prev)/(t_next-t_prev). Then the value v_t
                        # at t can be calculated as v_t=v_prev +
                        # dv/dt*(t-t_prev)

                        dv_dt = (v_next - v_prev) / (t_next - t_prev)
                        result[n] = v_prev + dv_dt * (t - t_prev)
                else:
                    # Interpolation distance is too long; don't use the value.
                    result[n] = None

            results.append_datapoint(time_label, result)

        return results
