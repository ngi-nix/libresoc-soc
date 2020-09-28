ls180:
	./ls180soc.py --build --platform=ls180
	cp build/ls180/gateware/ls180.v .
	cp build/ls180/gateware/mem.init .
	cp libresoc/libresoc.v .
	yosys -p 'read_verilog libresoc.v' \
          -p 'write_ilang libresoc_cvt.il'
	yosys -p 'read_verilog ls180.v' \
          -p 'write_ilang ls180_cvt.il'
	yosys -p 'read_ilang ls180_cvt.il' \
          -p 'read_ilang libresoc_cvt.il' \
          -p 'write_ilang ls180.il'
