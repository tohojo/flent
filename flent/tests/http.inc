## -*- mode: python; coding: utf-8 -*-

DATA_SETS['HTTP latency'] = {'interval': STEP_SIZE, 'length': TOTAL_LENGTH, 'units': 'ms',
                             'runner': 'http_getter'}


PLOTS['http_delay']       = {'description': 'HTTP latency over time',
                             'type': 'timeseries',
                             'series': [{'data': 'HTTP latency',
                                      'label': 'HTTP get (ms)'}]}

PLOTS['http_delay_cdf']   = {'description': 'Latency CDF plot',
                             'type': 'cdf',
                             'cutoff': HTTP_CUTOFF,
                             'parent': 'http_delay'}

PLOTS['http_box_combine'] = {'description': 'Box combination of HTTP latency',
                             'type': 'box_combine',
                             'axis_labels': ['Mean download time (s)'],
                             'cutoff': HTTP_CUTOFF,
                             'series': [{'data': 'HTTP latency',
                                         'label': 'HTTP get (ms)',
                                         'combine_mode': 'raw_mean'}]}
