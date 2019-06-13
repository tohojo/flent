## -*- mode: python; coding: utf-8 -*-

DATA_SETS['VoIP']                 = {'length': VOIP_LENGTH,
                                     'host': VOIP_HOST,
                                     'local_bind': VOIP_LOCAL_BIND,
                                     'interval': STEP_SIZE,
                                     'units': 'Kbps',
                                     'control_host': VOIP_CONTROL_HOST,
                                     'marking': VOIP_MARKING,
                                     'runner': 'voip'}
DATA_SETS['VoIP::bitrate']        = {'units': 'Kbits/s', 'runner': 'null'}
DATA_SETS['VoIP::delay']          = {'units': 'ms', 'runner': 'null'}
DATA_SETS['VoIP::jitter']         = {'units': 'ms', 'runner': 'null'}
DATA_SETS['VoIP::loss']           = {'units': 'count', 'runner': 'null'}
DATA_SETS['VoIP::induced_delay']  = {'units': 'ms', 'runner': 'diff_min', 'apply_to': ['VoIP::delay']}


PLOTS['voip_delay']              = {'description': 'VoIP delay and jitter',
                                    'type': 'timeseries',
                                    'axis_labels': ['One-way delay (ms)'],
                                    'series': [{'data': 'VoIP::delay',
                                                'label': 'VoIP delay'},
                                               {'data': 'VoIP::jitter',
                                                'label': 'VoIP jitter',
                                                'color': 'green'}
                                    ]}
PLOTS['voip_delay_cdf']          = {'description': 'VoIP delay and jitter CDF',
                                    'type': 'cdf',
                                    'cutoff': VOIP_CUTOFF,
                                    'parent': 'voip_delay'}
PLOTS['voip_delay_box']          = {'description': 'VoIP delay and jitter box plot',
                                    'type': 'box',
                                    'cutoff': VOIP_CUTOFF,
                                    'parent': 'voip_delay'}
PLOTS['voip_induced_delay']      = {'description': 'VoIP induced delay CDF',
                                    'type': 'timeseries',
                                    'axis_labels': ['Induced one-way delay (ms)'],
                                    'series': [{'data': 'VoIP::induced_delay',
                                                'label': 'VoIP induced delay'}]}
PLOTS['voip_induced_delay_cdf']  = {'description': 'VoIP induced delay box plot',
                                    'type': 'cdf',
                                    'cutoff': VOIP_CUTOFF,
                                    'parent': 'voip_induced_delay'}
PLOTS['voip_induced_delay_box']  = {'description': 'VoIP induced delay box plot',
                                    'type': 'box',
                                    'cutoff': VOIP_CUTOFF,
                                    'parent': 'voip_induced_delay'}
PLOTS['voip_box_delay_loss']     = {'description': "Box delay/loss combination plot",
                                    'type': 'box_combine',
                                    'cutoff': VOIP_CUTOFF,
                                    'dual_axes': True,
                                    'axis_labels': ['Mean induced delay (ms)', 'Mean loss rate'],
                                    'series': [{'data': 'VoIP::delay',
                                                'label': 'Induced VoIP delay',
                                                'combine_mode': 'mean_span',
                                                'axis': 1},
                                               {'data': 'VoIP::loss',
                                                'label': 'VoIP loss rate',
                                                'combine_mode': 'raw_seq_loss',
                                                'axis': 2}]}
PLOTS['voip_mos_combine']         = {'description': "VoIP MOS combination plot",
                                    'type': 'box_combine',
                                    'cutoff': VOIP_CUTOFF,
                                    'axis_labels': ['MOS value'],
                                    'series': [{'data': 'VoIP',
                                                'label': 'MOS',
                                                'combine_mode': 'mos'},
                                               ]}
PLOTS['voip_bitrate']            = {'description': 'VoIP bitrate',
                                    'type': 'timeseries',
                                    'series': [{'data': 'VoIP::bitrate',
                                                'label': 'Bitrate'}
                                    ]}
PLOTS['voip_mos_upload']          = {'description': "VoIP MOS and upload throughput plot",
                                     'type': 'box_combine',
                                     'cutoff': VOIP_CUTOFF,
                                     'axis_labels': ['MOS value', 'Mbit/s'],
                                     'dual_axes': True,
                                     'series': [{'data': 'VoIP',
                                                 'label': 'MOS',
                                                 'combine_mode': 'mos'},
                                                # upload sum doesn't exist for
                                                # single-flow tests, so use two
                                                # globbing expressions to
                                                # support both types of tests
                                                {'data': glob('TCP upload sum'),
                                                 'label': 'Upload',
                                                 'combine_mode': 'mean',
                                                 'axis': 2},
                                                {'data': glob('TCP upload'),
                                                 'label': 'Upload',
                                                 'combine_mode': 'mean',
                                                 'axis': 2},
                                     ]}
PLOTS['voip_loss']               = {'description': 'VoIP loss',
                                    'type': 'timeseries',
                                    'axis_labels': ['Loss count'],
                                    'series': [{'data': 'VoIP::loss',
                                                'label': 'VoIP loss',
                                                'linestyle': '',
                                                'marker': '.',}
                                    ]}
PLOTS['voip_delay_loss']         = {'description': 'VoIP delay and loss plots',
                                    'type': 'meta',
                                    'subplots': ('voip_delay', 'voip_loss')}
