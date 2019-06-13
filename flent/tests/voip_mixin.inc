## -*- mode: python; coding: utf-8 -*-

# Mixin include file to add a host to receive a VoIP flow


VOIP_HOST=get_test_parameter('voip_host', default=None)
VOIP_LOCAL_BIND=get_test_parameter('voip_local_bind', default=None)
VOIP_CONTROL_HOST=get_test_parameter('voip_control_host', VOIP_HOST)
VOIP_MARKING=get_test_parameter("voip_marking", default=None)
VOIP_LENGTH=TOTAL_LENGTH
VOIP_CUTOFF=(DELAY,-DELAY)
if VOIP_HOST:
    include("voip.inc")
