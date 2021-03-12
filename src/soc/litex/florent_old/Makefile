ls180:
	./ls180soc.py --build --platform=ls180
	cp build/ls180/gateware/ls180.v .
	cp build/ls180/gateware/mem.init .
	cp build/ls180/gateware/mem_1.init .
	cp build/ls180/gateware/mem_2.init .
	cp build/ls180/gateware/mem_3.init .
	cp build/ls180/gateware/mem_4.init .
	cp libresoc/libresoc.v .
	yosys -p 'read_verilog libresoc.v' \
          -p 'write_ilang libresoc_cvt.il'
	yosys -p 'read_verilog ls180.v' \
	      -p 'read_verilog SPBlock_512W64B8W.v' \
          -p 'write_ilang ls180_cvt.il'
	yosys -p 'read_ilang ls180_cvt.il' \
          -p 'read_ilang libresoc_cvt.il' \
          -p 'write_ilang ls180.il'

versaecp5:
	 ./versa_ecp5.py --sys-clk-freq=55e6 --build

versaecp5load:
	./versa_ecp5.py --sys-clk-freq=55e6 --load
