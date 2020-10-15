"""simple core issuer verilog generator
"""

import argparse
from nmigen.cli import verilog

from soc.config.test.test_loadstore import TestMemPspec
from soc.simple.issuer import TestIssuer


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Simple core issuer " \
                                     "verilog generator")
    parser.add_argument("output_filename")
    parser.add_argument("--enable-xics", action="store_true",
                        help="Enable interrupts",
                        default=True)
    parser.add_argument("--enable-core", action="store_true",
                        help="Enable main core",
                        default=True)
    parser.add_argument("--use-pll", action="store_true", help="Enable pll",
                        default=False)
    parser.add_argument("--enable-testgpio", action="store_true",
                        help="Disable gpio pins",
                        default=False)
    parser.add_argument("--debug", default="jtag", help="Select debug " \
                        "interface [jtag | dmi] [default jtag]")

    args = parser.parse_args()

    print(args)

    units = {'alu': 1,
             'cr': 1, 'branch': 1, 'trap': 1,
             'logical': 1,
             'spr': 1,
             'div': 1,
             'mul': 1,
             'shiftrot': 1
            }
    pspec = TestMemPspec(ldst_ifacetype='bare_wb',
                         imem_ifacetype='bare_wb',
                         addr_wid=48,
                         mask_wid=8,
                         # must leave at 64
                         reg_wid=64,
                         # set to 32 for instruction-memory width=32
                         imem_reg_wid=64,
                         # set to 32 to make data wishbone bus 32-bit
                         #wb_data_wid=32,
                         xics=args.enable_xics, # XICS interrupt controller
                         nocore=not args.enable_core, # test coriolis2 ioring
                         use_pll=args.use_pll,  # bypass PLL
                         gpio=args.enable_testgpio, # for test purposes
                         debug=args.debug,      # set to jtag or dmi
                         units=units)

    dut = TestIssuer(pspec)

    vl = verilog.convert(dut, ports=dut.external_ports(), name="test_issuer")
    with open(args.output_filename, "w") as f:
        f.write(vl)
