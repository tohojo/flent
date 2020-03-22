## -*- mode: python; coding: utf-8 -*-

urllist = HTTP_GETTER_URLLIST
if not urllist:
    urllist = [None]
elif not isinstance(urllist, list):
    urllist = [urllist]

if len(urllist) == 1:
    keys = ['HTTP latency']
else:
    keys = ['HTTP latency::{}'.format(i+1) for i in range(len(urllist))]

for k, url_file in zip(keys, urllist):
    DATA_SETS[k] = {'interval': STEP_SIZE, 'length': TOTAL_LENGTH, 'units': 'ms',
                    'runner': 'http_getter', 'url_file': url_file}


PLOTS['http_delay']       = {'description': 'HTTP latency over time',
                             'type': 'timeseries',
                             'series': [{'data': glob('HTTP latency**'),
                                      'label': 'HTTP get (ms)'}]}

PLOTS['http_delay_cdf']   = {'description': 'Latency CDF plot',
                             'type': 'cdf',
                             'cutoff': HTTP_CUTOFF,
                             'parent': 'http_delay'}

PLOTS['http_box_combine'] = {'description': 'Box combination of HTTP latency',
                             'type': 'box_combine',
                             'axis_labels': ['Mean download time (s)'],
                             'cutoff': HTTP_CUTOFF,
                             'series': [{'data': glob('HTTP latency**'),
                                         'label': 'HTTP get (ms)',
                                         'combine_mode': 'raw_mean'}]}
