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
    parser.add_argument("--disable-xics", action="store_true",
                        help="Disable interrupts")
    parser.add_argument("--use-pll", action="store_true", help="Enable pll")
    parser.add_argument("--disable-gpio", action="store_true",
                        help="Disable gpio pins")
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
                         xics=False if args.disable_xics else True,
                         # to help test coriolis2 ioring
                         #nocore=True,
                         # bypass PLL
                         use_pll=True if args.use_pll else False,
                         # for test purposes
                         gpio=False if args.disable_gpio else True,
                         # set to jtag or dmi
                         debug=args.debug,
                         units=units)

    dut = TestIssuer(pspec)

    vl = verilog.convert(dut, ports=dut.external_ports(), name="test_issuer")
    with open(args.output_filename, "w") as f:
        f.write(vl)
