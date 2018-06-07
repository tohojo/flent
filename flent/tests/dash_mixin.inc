## -*- mode: python; coding: utf-8 -*-

# Mixin include file to add a host to run a DASH client

DASH_CONTROL_HOST=get_test_parameter('dash_control_host', 'localhost')
DASH_URL=get_test_parameter('dash_url', default=None)

if DASH_URL:
   DATA_SETS['Dash'] = {'length': TOTAL_LENGTH, 'url': DASH_URL,
                        'host': DASH_CONTROL_HOST, 'units': 'Mbits/s',
                        'runner': 'dash_js'}

   PLOTS['dash'] = {
      'description': 'Dash media stream',
      'type': 'meta',
      'subplots': ['dash_throughput', 'dash_buffer']}

   PLOTS['dash_throughput'] = {
      'description': 'Dash throughput',
      'type': 'timeseries',
      'series': [{'data': 'Dash',
                  'raw_key': 'val',
                  'label': 'Throughput'},
                 {'data': 'Dash',
                  'raw_key': 'bitrate',
                  'label': 'Stream bitrate'}]}
   PLOTS['dash_buffer'] = {
      'description': 'Dash buffer length',
      'type': 'timeseries',
      'axis_labels': ['ms'],
      'series': [{'data': 'Dash',
                  'raw_key': 'buflen',
                  'label': 'Buffer length'}]}
