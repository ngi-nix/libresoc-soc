#!/usr/bin/env python3

import os
import argparse

import litex_boards.targets.versa_ecp5 as versa_ecp5
import litex_boards.targets.ulx3s as ulx3s

from litex.soc.integration.soc_sdram import (soc_sdram_args,
                                             soc_sdram_argdict)
from litex.soc.integration.builder import (Builder, builder_args,
                                           builder_argdict)

from libresoc import LibreSoC
#from microwatt import Microwatt

# TestSoC
# ----------------------------------------------------------------------------

from litex.build.generic_platform import Subsignal, Pins, IOStandard

class VersaECP5TestSoC(versa_ecp5.BaseSoC):
    def __init__(self, sys_clk_freq=int(16e6), **kwargs):
        kwargs["integrated_rom_size"] = 0x10000
        #kwargs["integrated_main_ram_size"] = 0x1000
        kwargs["csr_data_width"] = 32
        kwargs["l2_size"] = 0
        #bus_data_width = 16,

        versa_ecp5.BaseSoC.__init__(self,
            sys_clk_freq = sys_clk_freq,
            cpu_type     = "external",
            cpu_cls      = LibreSoC,
            cpu_variant = "standardjtagnoirq",
            #cpu_cls      = Microwatt,
            device       = "LFE5UM",
            **kwargs)

        # (thanks to daveshah for this tip)
        # use platform.add_extension to first define the pins
        # https://github.com/daveshah1/linux-on-litex-vexriscv/commit/dc97bac3aeb04cfbf5116a6c7e324ce849391770#diff-2353956cb1116676bd6b96769c8ebf7b4b86c16c47511eb2888d0dd2a979e09eR117-R134

        # define the pins, add as an extension, *then* request it
        jtag_ios = [
            ("jtag", 0,
                Subsignal("tck", Pins("B19"), IOStandard("LVCMOS25")),
                Subsignal("tms", Pins("B12"), IOStandard("LVCMOS25")),
                Subsignal("tdi", Pins("B9"), IOStandard("LVCMOS25")),
                Subsignal("tdo", Pins("E6"), IOStandard("LVCMOS25")),
            )
        ]
        self.platform.add_extension(jtag_ios)
        jtag = self.platform.request("jtag")

        # wire the pins up to CPU JTAG
        self.comb += self.cpu.jtag_tck.eq(jtag.tck)
        self.comb += self.cpu.jtag_tms.eq(jtag.tms)
        self.comb += self.cpu.jtag_tdi.eq(jtag.tdi)
        self.comb += jtag.tdo.eq(self.cpu.jtag_tdo)


        #self.add_constant("MEMTEST_BUS_SIZE",  256//16)
        #self.add_constant("MEMTEST_DATA_SIZE", 256//16)
        #self.add_constant("MEMTEST_ADDR_SIZE", 256//16)

        #self.add_constant("MEMTEST_BUS_DEBUG", 1)
        #self.add_constant("MEMTEST_ADDR_DEBUG", 1)
        #self.add_constant("MEMTEST_DATA_DEBUG", 1)


class ULX3S85FTestSoC(ulx3s.BaseSoC):
    def __init__(self, sys_clk_freq=int(16e6), **kwargs):
        kwargs["integrated_rom_size"] = 0x10000
        #kwargs["integrated_main_ram_size"] = 0x1000
        kwargs["csr_data_width"] = 32
        kwargs["l2_size"] = 0
        #bus_data_width = 16,

        ulx3s.BaseSoC.__init__(self,
            sys_clk_freq = sys_clk_freq,
            cpu_type     = "external",
            cpu_cls      = LibreSoC,
            cpu_variant  = "standardjtag",
            #cpu_cls      = Microwatt,
            device       = "LFE5U-85F",
            **kwargs)

        # get 4 arbitrarily assinged logical pins, each gpio has
        # 2 distinct physical single non-differential pins p and n
        gpio0    = self.platform.request("gpio", 0)
        gpio1    = self.platform.request("gpio", 1)

        # assign p, n litex 'subsignals' of each gpio to jtag pins
        jtag_tdi = gpio0.n
        jtag_tms = gpio0.p
        jtag_tck = gpio1.n
        jtag_tdo = gpio1.p

        # wire the pins up to CPU JTAG
        self.comb += self.cpu.jtag_tdi.eq(jtag_tdi)
        self.comb += self.cpu.jtag_tms.eq(jtag_tms)
        self.comb += self.cpu.jtag_tdi.eq(jtag_tdi)
        self.comb += jtag_tdo.eq(self.cpu.jtag_tdo)

# Build
# ----------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LiteX SoC with LibreSoC " \
                                     "CPU on Versa ECP5 or ULX3S LFE5U85F")
    parser.add_argument("--build", action="store_true", help="Build bitstream")
    parser.add_argument("--load", action="store_true", help="Load bitstream")
    parser.add_argument("--sys-clk-freq",  default=int(16e6),
                        help="System clock frequency (default=16MHz)")
    parser.add_argument("--fpga", default="versa_ecp5", help="FPGA target " \
                        "to build for/load to")

    builder_args(parser)
    soc_sdram_args(parser)
    args = parser.parse_args()

    if args.fpga == "versa_ecp5":
        soc = VersaECP5TestSoC(sys_clk_freq=int(float(args.sys_clk_freq)),
                               **soc_sdram_argdict(args))

    elif args.fpga == "ulx3s85f":
        soc = ULX3S85FTestSoC(sys_clk_freq=int(float(args.sys_clk_freq)),
                              **soc_sdram_argdict(args))

    else:
        soc = VersaECP5TestSoC(sys_clk_freq=int(float(args.sys_clk_freq)),
                               **soc_sdram_argdict(args))

    builder = Builder(soc, **builder_argdict(args))
    builder.build(run=args.build)

    if args.load:
        prog = soc.platform.create_programmer()
        prog.load_bitstream(os.path.join(builder.gateware_dir,
                                         soc.build_name + ".svf"))

if __name__ == "__main__":
    main()
