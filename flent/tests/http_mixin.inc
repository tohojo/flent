## -*- mode: python; coding: utf-8 -*-

# Mixin include file to add a HTTP test

HTTP_CUTOFF=(DELAY,-DELAY)
if get_test_parameter('include_http', default=False):
    include("http.inc")
