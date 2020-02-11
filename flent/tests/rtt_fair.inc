## -*- mode: python; coding: utf-8 -*-

DATA_SETS = o([
    ('TCP upload avg',
     {'apply_to': [glob("TCP upload*", exclude=["TCP upload sum", "TCP upload fairness"])],
       'units': 'Mbits/s',
       'runner': 'average',}),
    ('TCP upload sum',
     {'apply_to': [glob("TCP upload*", exclude=["TCP upload avg", "TCP upload fairness"])],
       'units': 'Mbits/s',
       'runner': 'sum',}),
    ('TCP upload fairness',
     {'apply_to': [glob("TCP upload*", exclude=["TCP upload avg", "TCP upload sum"])],
       'units': 'Idx',
       'runner': 'fairness',}),

    ('TCP download avg',
     {'apply_to': [glob("TCP download*", exclude=["TCP download sum", "TCP download fairness"])],
       'units': 'Mbits/s',
       'runner': 'average',}),
    ('TCP download sum',
     {'apply_to': [glob("TCP download*", exclude=["TCP download avg", "TCP download fairness"])],
       'units': 'Mbits/s',
       'runner': 'sum',}),
    ('TCP download fairness',
     {'apply_to': [glob("TCP download*", exclude=["TCP download avg", "TCP download sum"])],
       'units': 'Idx',
       'runner': 'fairness',}),

    ('Ping (ms) avg',
     {'apply_to': [glob("Ping (ms)*")],
       'units': 'ms',
       'runner': 'average',}),
    ])

def add_stream(i, host=None, label='BE', ping_label='ICMP', marking='CS0',
               control_host=None, local_bind=None, cc_algo=None, send_size=None,
               length=LENGTH, delay=DELAY, **kwargs):
    if host is None:
        return

    if control_host is None:
        control_host = host

    DATA_SETS['TCP upload %s %s' % (label or "BE", host)] = \
     {'test': 'TCP_STREAM', 'length': length, 'host': host, 'marking': marking or
                              'CS0', 'control_host': control_host or host, 'local_bind': local_bind,
                              'delay': delay, 'id': host, 'units': 'Mbits/s', 'runner': 'netperf_demo',
                              'cong_control': cc_algo, 'send_size': send_size}
    DATA_SETS['TCP download %s %s' % (label or "BE", host)] = \
     {'test': 'TCP_MAERTS', 'length': length, 'host': host, 'marking': marking or
                              'CS0', 'control_host': control_host or host, 'local_bind': local_bind,
                              'delay': delay, 'id': host, 'units': 'Mbits/s', 'runner': 'netperf_demo',
                              'cong_control': cc_algo, 'send_size': send_size}
    DATA_SETS['Ping (ms) %s %s' % (ping_label or "ICMP", host)] = \
     {'ip_version': IP_VERSION, 'interval': STEP_SIZE, 'length': TOTAL_LENGTH,
      'host': host, 'local_bind': local_bind, 'id': host, 'units': 'ms',
      'runner': 'ping'}

for_stream_config(add_stream)

PLOTS = o([
    ('download',
     {'description': 'Download bandwidth plot',
      'type': 'timeseries',
      'legend_title': 'TCP download',
      'series': [{'data': glob('TCP download *', exclude=["TCP download avg", "TCP download fairness", "TCP download sum"]),
                  'label': 'Download'},
                 {'data': 'TCP download avg',
                  'label': 'Avg',
                  'smoothing': 10,
                  'color': 'black',
                  'linewidth': 2}]}),

    ('download_scaled',
     {'description': 'Download bandwidth w/axes scaled to remove outliers',
      'parent': 'download',
      'scaling': (5,95)}),

    ('upload',
     {'description': 'Upload bandwidth plot',
      'type': 'timeseries',
      'legend_title': 'TCP upload',
      'series': [{'data': glob('TCP upload *', exclude=["TCP upload avg", "TCP upload fairness", "TCP upload sum"]),
                  'label': 'Upload'},
                 {'data': 'TCP upload avg',
                  'label': 'Avg',
                  'smoothing': 10,
                  'color': 'black',
                  'linewidth': 2}]}),

    ('upload_scaled',
     {'description': 'Upload bandwidth w/axes scaled to remove outliers',
      'parent': 'upload',
      'scaling': (5,95)}),

    ('bar_fairness',
     {'description': 'Jain\'s fairness combined bar plot',
      'type': 'bar_combine',
      'cutoff': (DELAY,-DELAY),
      'group_by': 'groups',
      'axis_labels': ['Fairness index'],
      'series': [{'data': 'TCP upload fairness',
                  'label': 'Upload fairness',
                  'combine_mode': 'mean'},
                 {'data': 'TCP download fairness',
                  'label': 'Download fairness',
                  'combine_mode': 'mean'}]}),

    ('ping',
     {'description': 'Ping plot',
      'type': 'timeseries',
      'legend_title': 'Ping (ms)',
      'axis_labels': ['Latency (ms)'],
      'series': [{'data': glob('Ping (ms) *', exclude=['Ping (ms) avg']),
                  'label': 'Ping (ms) ICMP'},
                 {'data': 'Ping (ms) avg',
                  'label': 'Avg',
                  'smoothing': 10,
                  'color': 'black',
                  'linewidth': 2}]}),

    ('ping_scaled',
     {'description': 'Ping w/axes scaled to remove outliers',
      'parent': 'ping',
      'scaling': (5,95)}),

    ('ping_cdf',
     {'description': 'Ping CDF plot',
      'type': 'cdf',
      'axis_labels': ['Latency (ms)'],
      'parent': 'ping',
      'cutoff': (DELAY,-DELAY)}),

    ('ping_cdf_combine',
     {'description': 'Ping CDF plot',
      'type': 'cdf_combine',
      'group_by': 'groups_concat',
      'axis_labels': ['Latency (ms)'],
      'parent': 'ping',
      'cutoff': (DELAY,-DELAY)}),

    ('totals',
     {'description': 'Total bandwidth and average ping plot',
      'type': 'timeseries',
      'dual_axes': True,
      'axis_labels': [None, 'Latency (ms)'],
      'series': [{'data': 'TCP download sum',
                  'label': 'Download',
                  'smoothing': 10},
                 {'data': 'TCP upload sum',
                  'label': 'Upload',
                  'smoothing': 10},
                 {'data': 'Ping (ms) avg',
                  'label': 'Ping (ms)',
                  'smoothing': 10,
                  'axis': 2}]}),
    ('totals_scaled',
     {'description': 'Total bandwidth and average ping plot (scaled)',
      'parent': 'totals',
      'scaling': (5,95)}),

    ('all_scaled',
     {'description': 'Download, upload, ping (scaled versions)',
      'type': 'meta',
      'subplots': ('download_scaled', 'upload_scaled', 'ping_scaled')}),

    ('all',
     {'description': 'Download, upload, ping (unscaled versions)',
      'type': 'meta',
      'subplots': ('download', 'upload', 'ping')}),

    ('box_download',
     {'description': 'Download bandwidth box plot',
      'parent': 'download',
      'type': 'box'}),

    ('box_upload',
     {'description': 'Upload bandwidth box plot',
      'parent': 'upload',
      'type': 'box'}),

    ('box_combine_up',
     {'description': 'Upload bandwidth combination box plot',
      'series': [{'data': glob('TCP upload *', exclude=["TCP upload avg", "TCP upload fairness", "TCP upload sum"]),
                  'label': 'BE',
                  'combine_mode': 'mean'},
                 {'data': 'TCP upload avg',
                  'label': 'Avg',
                  'combine_mode': 'mean'}],
      'type': 'box_combine'}),

    ('bar_combine_up',
     {'description': 'Upload bandwidth combination bar plot',
      'parent': 'box_combine_up',
      'type': 'bar_combine'}),

    ('box_combine_down',
     {'description': 'Download bandwidth combination box plot',
      'series': [{'data': glob('TCP download *', exclude=["TCP download avg", "TCP download fairness", "TCP download sum"]),
                  'label': 'BE',
                  'combine_mode': 'mean'},
                 {'data': 'TCP download avg',
                  'label': 'Avg',
                  'combine_mode': 'mean'}],
      'type': 'box_combine'}),

    ('bar_combine_down',
     {'description': 'Download bandwidth combination bar plot',
      'parent': 'box_combine_down',
      'type': 'bar_combine'}),

    ('box_ping',
     {'description': 'Ping box plot',
      'parent': 'ping',
      'type': 'box'}),

    ('box_totals',
     {'description': 'Box plot of totals',
      'parent': 'totals',
      'type': 'box',}),

    ('box_combine',
     {'description': 'Box plot of averages of several data files.',
      'type': 'box_combine',
      'dual_axes': True,
      'axis_labels': ['Mean TCP goodput (Mbit/s)', 'Mean induced latency (ms)'],
      'cutoff': (DELAY,-DELAY),
      'series': [{'data': 'TCP download sum',
                  'label': 'Download',
                  'combine_mode': 'mean'},
                 {'data': 'TCP upload sum',
                  'label': 'Upload',
                  'combine_mode': 'mean'},
                 {'data': 'Ping (ms) avg',
                  'label': 'Induced latency (ms)',
                  'combine_mode': 'mean_span',
                  'axis': 2}]}),

    ('bar_combine',
     {'description': 'Bar plot of averages of several data files.',
      'type': 'bar_combine',
      'parent': 'box_combine'}),

    ('box_combine_throughput',
     {'description': 'Box plot of averages of several data files - throughput.',
      'type': 'box_combine',
      'axis_labels': ['Mean TCP goodput (Mbit/s)'],
      'cutoff': (DELAY,-DELAY),
      'series': [{'data': 'TCP download sum',
                  'label': 'Download',
                  'combine_mode': 'mean'},
                 {'data': 'TCP upload sum',
                  'label': 'Upload',
                  'combine_mode': 'mean'}]}),

    ('bar_combine_throughput',
     {'description': 'Bar plot of averages of several data files - throughput.',
      'type': 'bar_combine',
      'parent': 'box_combine_throughput'}),

    ])

include("common.inc")
