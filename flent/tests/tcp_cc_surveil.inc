## -*- mode: python; coding: utf-8 -*-

# Mixin include file to add surveilling pid flows to a test

PIDS=get_test_parameter('socket_stats_pids')
HOST="localhost"
DEFAULTS={'PLOT': 'tcp_cwnd'}

if PIDS:
    for pid in PIDS.split(","):
        DATA_SETS['sock_stats::%s' % pid] = {'command': find_ss_iterate(IP_VERSION, HOST, STEP_SIZE, TOTAL_LENGTH),
                                              'units': 'misc',
                                              'runner': 'ss',}

PLOTS['tcp_cwnd'] = {'description': 'TCP window statistics',
                     'type': 'timeseries',
                     'axis_labels': ['Packets'],
                     'series': [
                         {
                          'data': glob("sock_stats::**"),
                          'label': 'TCP window size',
                          'raw_key' : glob("**::tcp_cwnd")
                      },
                     ]}

PLOTS['tcp_rtt'] = {'description': 'TCP RTT statistics',
                 'type': 'timeseries',
                 'axis_labels': ['Latency (ms)'],
                 'series': [
                     {
                       'data': glob("sock_stats::**"),
                       'label': 'RTT',
                       'raw_key': glob("**::tcp_rtt")
                       },
                 ]}

PLOTS['tcp_rtt_var'] = {'description': 'TCP RTT statistics',
                 'type': 'timeseries',
                 'axis_labels': ['Latency (ms)'],
                 'series': [
                     {
                       'data': glob("sock_stats::**"),
                       'label': 'RTT_VAR',
                       'raw_key': glob("**::tcp_rtt_var")
                       },
                 ]}
