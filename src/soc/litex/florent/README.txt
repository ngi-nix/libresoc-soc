# sim openocd test

create verilog file "python issuer_verilog libresoc.v"
copy to libresoc/ directory
terminal 1: ./sim.py
terminal 2: openocd -f openocd.cfg -c init -c 'svf idcode_test2.svf'

# ecp5 build

./versa_ecp5.py --sys-clk-freq=55e6 --build
./versa_ecp5.py --sys-clk-freq=55e6 --load
