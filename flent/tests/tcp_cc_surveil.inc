## -*- mode: python; coding: utf-8 -*-

# Mixin include file to add surveilling pid flows to a test

PIDS=get_test_parameter('socket_stats_pids')

if PIDS:
    for pid in PIDS.split(","):
        DATA_SETS['sock_stats::%s' % pid] = {'command': find_ss_iterate(IP_VERSION, HOST, STEP_SIZE, TOTAL_LENGTH),
                                              'units': 'misc',
                                              'runner': 'ss',}
        DATA_SETS['sock_stats::%s::tcp_cwnd' % pid] = {'units': 'packets', 'runner': 'null', 'id': pid}
        DATA_SETS['sock_stats::%s::tcp_rtt' % pid] = {'units': 'ms', 'runner': 'null', 'id': pid}

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
