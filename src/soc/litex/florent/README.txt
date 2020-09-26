create verilog file "python issuer_verilog libresoc.v"
copy to libresoc/ directory
terminal 1: ./sim.py
terminal 2: openocd -f openocd.cfg -c init -c 'svf idcode_test2.svf'
