# -*- mode: python; coding: utf-8 -*-

# Mixin to provide plots for TCP socket stats data series

PLOTS['tcp_cwnd'] = {'description': 'TCP window statistics',
                     'type': 'timeseries',
                     'axis_labels': ['Packets'],
                     'series': [
                         {'data': glob('**::tcp_cwnd'),
                          'label': 'TCP window size'},
                     ]}
PLOTS['tcp_rtt'] = {'description': 'TCP RTT statistics',
                    'type': 'timeseries',
                    'axis_labels': ['Latency (ms)'],
                    'series': [
                        {'data': glob('**::tcp_rtt'),
                         'label': 'RTT'},
                    ]}
PLOTS['tcp_rtt_cdf'] = {'description': 'TCP RTT statistics',
                        'type': 'cdf',
                        'axis_labels': ['Latency (ms)'],
                        'parent': 'tcp_rtt',
                        'cutoff': (DELAY,DELAY)}


# This is a bit of a hack: Since the plotter needs entries in DATA_SETS to be
# able to construct the plots, just generate entries for every netperf runner.
# The data sets that don't actually exist will then be filtered out by the
# plotter afterwards.
new_sets = {}
for k, v in DATA_SETS.items():
    if v['runner'] == 'netperf_demo':
        if 'duplicates' in v:
            for i in range(v['duplicates']):
                new_sets["%s::%d::tcp_cwnd" % (k, i+1)] = {'runner': 'null',
                                                           'units': 'packets',
                                                           'id': k}
                new_sets["%s::%d::tcp_rtt" % (k, i+1)] = {'runner': 'null',
                                                          'units': 'ms',
                                                          'id': k}
        else:
            new_sets["%s::tcp_cwnd" % k] = {'runner': 'null',
                                            'units': 'packets',
                                            'id': k}
            new_sets["%s::tcp_rtt" % k] = {'runner': 'null',
                                           'units': 'ms',
                                           'id': k}
if new_sets:
    DATA_SETS.update(new_sets)
