#!/usr/bin/env python3

import os
import argparse

from migen import Signal, FSM, If, Display, Finish

from litex.build.generic_platform import Pins, Subsignal
from litex.build.sim import SimPlatform
from litex.build.io import CRG
from litex.build.sim.config import SimConfig

from litex.soc.integration.soc import SoCRegion
from litex.soc.integration.soc_core import SoCCore
from litex.soc.integration.builder import Builder

from litex.tools.litex_sim import Platform

from libresoc import LibreSoC
from microwatt import Microwatt

# LibreSoCSim -----------------------------------------------------------------

class LibreSoCSim(SoCCore):
    def __init__(self, cpu="libresoc", debug=False):
        assert cpu in ["libresoc", "microwatt"]
        platform     = Platform()
        sys_clk_freq = int(1e6)

        # SoCCore -------------------------------------------------------------
        SoCCore.__init__(self, platform, clk_freq=sys_clk_freq,
            cpu_type                 = "microwatt",
            cpu_cls                  = LibreSoC   if cpu == "libresoc" \
                                       else Microwatt,
            uart_name                = "sim",
            integrated_rom_size      = 0x10000,
            integrated_main_ram_size = 0x10000000) # 256MB
        self.platform.name = "sim"

        # CRG -----------------------------------------------------------------
        self.submodules.crg = CRG(platform.request("sys_clk"))

        # Debug ---------------------------------------------------------------
        if debug:
            uptime = Signal(64)
            self.sync += uptime.eq(uptime + 1)
            self.sync += If(self.cpu.ibus.stb & self.cpu.ibus.ack &
                            self.cpu.ibus.we,
                Display("[%06x] iadr: %8x, s %01x w %016x",
                    uptime,
                    self.cpu.ibus.adr,
                    self.cpu.ibus.sel,
                    self.cpu.ibus.dat_w,
                )
            )
            self.sync += If(self.cpu.ibus.stb & self.cpu.ibus.ack &
                            ~self.cpu.ibus.we,
                Display("[%06x] iadr: %8x, s %01x r %016x",
                    uptime,
                    self.cpu.ibus.adr,
                    self.cpu.ibus.sel,
                    self.cpu.ibus.dat_r
                )
            )
            self.sync += If(self.cpu.dbus.stb & self.cpu.dbus.ack,
                Display("[%06x] dadr: %8x, we %d s %01x w %016x r: %016x",
                    uptime,
                    self.cpu.dbus.adr,
                    self.cpu.dbus.we,
                    self.cpu.dbus.sel,
                    self.cpu.dbus.dat_w,
                    self.cpu.dbus.dat_r
                )
            )
            # Stop after 20000 cycles
            self.sync += If(uptime == 100000, Finish())

# Build -----------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LiteX LibreSoC CPU Sim")
    parser.add_argument("--cpu",          default="libresoc",
                        help="CPU to use: libresoc (default) or microwatt")
    parser.add_argument("--debug",        action="store_true",
                        help="Enable debug traces")
    parser.add_argument("--trace",        action="store_true",
                        help="Enable tracing")
    parser.add_argument("--trace-start",  default=0,
                        help="Cycle to start FST tracing")
    parser.add_argument("--trace-end",    default=-1,
                        help="Cycle to end FST tracing")
    args = parser.parse_args()

    sim_config = SimConfig(default_clk="sys_clk")
    sim_config.add_module("serial2console", "serial")

    for i in range(2):
        soc = LibreSoCSim(cpu=args.cpu, debug=args.debug)
        builder = Builder(soc,compile_gateware = i!=0)
        builder.build(sim_config=sim_config,
            run         = i!=0,
            trace       = args.trace,
            trace_start = int(args.trace_start),
            trace_end   = int(args.trace_end),
            trace_fst   = 0)
        os.chdir("../")

if __name__ == "__main__":
    main()
