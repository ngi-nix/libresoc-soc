ls180:
	./ls180soc.py --build --platform=ls180
	cp build/ls180/gateware/ls180.v .
	cp build/ls180/gateware/mem.init .
	cp libresoc/libresoc.v .
	yosys -p 'read_verilog ls180.v; read_verilog libresoc.v; write_ilang ls180.il'
	yosys -p 'read_verilog ls180.v' \
          -p 'read_verilog libresoc.v' \
          -p 'write_ilang ls180.il'
