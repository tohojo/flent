## -*- mode: python; coding: utf-8 -*-

# Mixin include file to add extra hosts to ping


VOIP_HOST=get_test_parameter('voip_host', default=None)
VOIP_LOCAL_BIND=get_test_parameter('voip_local_bind', default=None)
VOIP_CONTROL_HOST=get_test_parameter('voip_control_host', VOIP_HOST)
if VOIP_HOST:
    include("voip.inc")
