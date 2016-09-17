## -*- mode: python; coding: utf-8 -*-

# Mixin include file to add a HTTP test

if get_test_parameter('include_http', default=False):
    include("http.inc")
