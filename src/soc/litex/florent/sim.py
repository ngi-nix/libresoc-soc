#!/usr/bin/env python3

import os
import argparse

from migen import (Signal, FSM, If, Display, Finish, NextValue, NextState)

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
            #bus_data_width           = 64,
            uart_name                = "sim",
            integrated_rom_size      = 0x10000,
            integrated_main_ram_size = 0x10000000) # 256MB
        self.platform.name = "sim"

        # CRG -----------------------------------------------------------------
        self.submodules.crg = CRG(platform.request("sys_clk"))

        # Debug ---------------------------------------------------------------
        if not debug:
            return

        # setup running of DMI FSM
        dmi_addr = Signal(3)
        dmi_din = Signal(64)
        dmi_dout = Signal(64)
        dmi_wen = Signal(1)
        dmi_req = Signal(1)

        # debug log out
        dbg_addr = Signal(3)
        dbg_dout = Signal(64)
        dbg_msg = Signal(1)

        uptime = Signal(64)
        # increment counter, Stop after 100000 cycles
        uptime = Signal(64)
        self.sync += uptime.eq(uptime + 1)
        self.sync += If(uptime == 100000, Finish())

        dmifsm = FSM()
        self.submodules += dmifsm

        # DMI FSM
        dmifsm.act("START",
            If(dmi_req & dmi_wen,
                (self.cpu.dmi_addr.eq(dmi_addr),   # DMI Addr
                 self.cpu.dmi_din.eq(dmi_din), # DMI in
                 self.cpu.dmi_req.eq(1),    # DMI request
                 self.cpu.dmi_wr.eq(1),    # DMI write
                 If(self.cpu.dmi_ack,
                    (NextState("IDLE"),
                    )
                 ),
                ),
            ),
            If(dmi_req & ~dmi_wen,
                (self.cpu.dmi_addr.eq(dmi_addr),   # DMI Addr
                 self.cpu.dmi_req.eq(1),    # DMI request
                 self.cpu.dmi_wr.eq(0),    # DMI read
                 If(self.cpu.dmi_ack,
                    (NextState("IDLE"),
                     NextValue(dbg_addr, dmi_addr),
                     NextValue(dbg_dout, self.cpu.dmi_dout),
                     NextValue(dbg_msg, 1),
                    )
                 ),
                ),
            )
        )

        dmifsm.act("IDLE",
            (NextValue(dmi_req, 0),
             NextValue(dmi_addr, 0),
             NextValue(dmi_din, 0),
             NextValue(dmi_wen, 0),
             NextState("START"), # back to start on next cycle
            )
        )

        # debug messages out
        self.sync += If(dbg_msg,
            (If(dbg_addr == 0b10, # PC
                Display("pc : %016x", dbg_dout),
             ),
             If(dbg_addr == 0b11, # PC
                Display("    msr: %016x", dbg_dout),
             ),
             If(dbg_addr == 0b101, # GPR
                Display("    gpr: %016x", dbg_dout),
             ),
             dbg_msg.eq(0)
            )
        )

        # kick off a "stop"
        self.sync += If(uptime == 0,
            (dmi_addr.eq(0), # CTRL
             dmi_din.eq(1<<0), # STOP
             dmi_req.eq(1),
             dmi_wen.eq(1),
            )
        )

        # loop every 1<<N cycles
        cyclewid = 9

        # get the PC
        self.sync += If(uptime[0:cyclewid] == 4,
            (dmi_addr.eq(0b10), # NIA
             dmi_req.eq(1),
             dmi_wen.eq(0),
            )
        )

        # kick off a "step"
        self.sync += If(uptime[0:cyclewid] == 8,
            (dmi_addr.eq(0), # CTRL
             dmi_din.eq(1<<3), # STEP
             dmi_req.eq(1),
             dmi_wen.eq(1),
            )
        )

        # get the MSR
        self.sync += If(uptime[0:cyclewid] == 28,
            (dmi_addr.eq(0b11), # MSR
             dmi_req.eq(1),
             dmi_wen.eq(0),
            )
        )

        # read all 32 GPRs
        for i in range(32):
            self.sync += If(uptime[0:cyclewid] == 30+(i*8),
                (dmi_addr.eq(0b100), # GSPR addr
                 dmi_din.eq(i), # r1
                 dmi_req.eq(1),
                 dmi_wen.eq(1),
                )
            )

            self.sync += If(uptime[0:cyclewid] == 34+(i*8),
                (dmi_addr.eq(0b101), # GSPR data
                 dmi_req.eq(1),
                 dmi_wen.eq(0),
                )
            )

        # monitor ibus write
        self.sync += If(self.cpu.ibus.stb & self.cpu.ibus.ack &
                        self.cpu.ibus.we,
            Display("    [%06x] iadr: %8x, s %01x w %016x",
                uptime,
                self.cpu.ibus.adr,
                self.cpu.ibus.sel,
                self.cpu.ibus.dat_w,
            )
        )
        # monitor ibus read
        self.sync += If(self.cpu.ibus.stb & self.cpu.ibus.ack &
                        ~self.cpu.ibus.we,
            Display("    [%06x] iadr: %8x, s %01x r %016x",
                uptime,
                self.cpu.ibus.adr,
                self.cpu.ibus.sel,
                self.cpu.ibus.dat_r
            )
        )

        # monitor bbus read/write
        self.sync += If(self.cpu.dbus.stb & self.cpu.dbus.ack,
            Display("    [%06x] dadr: %8x, we %d s %01x w %016x r: %016x",
                uptime,
                self.cpu.dbus.adr,
                self.cpu.dbus.we,
                self.cpu.dbus.sel,
                self.cpu.dbus.dat_w,
                self.cpu.dbus.dat_r
            )
        )

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
