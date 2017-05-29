# -*- mode: python; coding: utf-8 -*-

# Mixin to provide plots for TCP socket stats data series

PLOTS['tcp_cwnd'] = {'description': 'TCP window statistics',
                     'type': 'timeseries',
                     'axis_labels': ['Packets'],
                     'series': [
                         {'data': glob('TCP*'),
                          'raw_key': 'tcp_cwnd',
                          'label': 'TCP window size'},
                     ]}
PLOTS['tcp_rtt'] = {'description': 'TCP RTT statistics',
                    'type': 'timeseries',
                    'axis_labels': ['Latency (ms)'],
                    'series': [
                        {'data': glob('TCP*'),
                         'raw_key': 'tcp_rtt',
                         'label': 'RTT'},
                    ]}
PLOTS['tcp_rtt_cdf'] = {'description': 'TCP RTT statistics',
                        'type': 'cdf',
                        'axis_labels': ['Latency (ms)'],
                        'parent': 'tcp_rtt',
                        'cutoff': (DELAY,DELAY)}
