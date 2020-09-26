#!/bin/sh
# run python3 debug/test/test_jtag_tap_srv.py  server &
# then run this script.

openocd -f debug/test/openocd.cfg -c init \
                                   -c 'svf debug/test/idcode_test2.svf' \
                                  -c shutdown
