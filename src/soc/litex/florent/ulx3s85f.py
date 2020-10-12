#!/usr/bin/env python3

import os
import argparse

from litex_boards.platforms import ulx3s
from litex_boards.targets.ulx3s import _CRG, BaseSoC

from litex.soc.integration.soc_sdram import (soc_sdram_args,
                                             soc_sdram_argdict)
from litex.soc.integration.builder import (Builder, builder_args,
                                           builder_argdict)

from libresoc import LibreSoC
#from microwatt import Microwatt

# TestSoC ------------------------------------------------------------------------------------------

class TestSoC(BaseSoC):
    def __init__(self, sys_clk_freq=int(16e6), **kwargs):
        kwargs["integrated_rom_size"] = 0x10000
        #kwargs["integrated_main_ram_size"] = 0x1000
        kwargs["csr_data_width"] = 32
        kwargs["l2_size"] = 0
        #bus_data_width = 16,
        BaseSoC.__init__(self, device="LFE5U-85F", sys_clk_freq=sys_clk_freq,
            cpu_type    = "external",
            cpu_cls     = LibreSoC,
            cpu_variant = "standardjtag",
            #cpu_cls  = Microwatt,
            **kwargs)

        #self.add_constant("MEMTEST_BUS_SIZE",  256//16)
        #self.add_constant("MEMTEST_DATA_SIZE", 256//16)
        #self.add_constant("MEMTEST_ADDR_SIZE", 256//16)

        #self.add_constant("MEMTEST_BUS_DEBUG", 1)
        #self.add_constant("MEMTEST_ADDR_DEBUG", 1)
        #self.add_constant("MEMTEST_DATA_DEBUG", 1)

# Build --------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
                description="LiteX SoC with LibreSoC CPU on ULX3S-85F")
    parser.add_argument("--build", action="store_true", help="Build bitstream")
    parser.add_argument("--load",  action="store_true", help="Load bitstream")
    parser.add_argument("--sys-clk-freq",  default=int(16e6),
                         help="System clock frequency (default=16MHz)")

    builder_args(parser)
    soc_sdram_args(parser)
    args = parser.parse_args()

    soc = TestSoC(sys_clk_freq=int(float(args.sys_clk_freq)),
                  **soc_sdram_argdict(args))
    builder = Builder(soc, **builder_argdict(args))
    builder.build(run=args.build)

    if args.load:
        prog = soc.platform.create_programmer()
        prog.load_bitstream(os.path.join(builder.gateware_dir, soc.build_name + ".svf"))

if __name__ == "__main__":
    main()
