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
from litex.soc.integration.soc_sdram import SoCSDRAM
from litex.soc.integration.builder import Builder

from litedram import modules as litedram_modules
from litedram.phy.model import SDRAMPHYModel
from litex.tools.litex_sim import sdram_module_nphases, get_sdram_phy_settings

from litex.tools.litex_sim import Platform

from libresoc import LibreSoC
from microwatt import Microwatt

# LibreSoCSim -----------------------------------------------------------------

class LibreSoCSim(SoCSDRAM):
    def __init__(self, cpu="libresoc", debug=False, with_sdram=True,
            #sdram_module          = "AS4C16M16",
            #sdram_data_width      = 16,
            sdram_module          = "MT48LC16M16",
            sdram_data_width      = 16,
            ):
        assert cpu in ["libresoc", "microwatt"]
        platform     = Platform()
        sys_clk_freq = int(100e6)

        #cpu_data_width = 32
        cpu_data_width = 64

        if cpu_data_width == 32:
            variant = "standard32"
        else:
            variant = "standard"

        # SoCCore -------------------------------------------------------------
        SoCSDRAM.__init__(self, platform, clk_freq=sys_clk_freq,
            cpu_type                 = "microwatt",
            cpu_cls                  = LibreSoC   if cpu == "libresoc" \
                                       else Microwatt,
            #bus_data_width           = 64,
            cpu_variant              = variant,
            csr_data_width            = 32,
            l2_size             = 0,
            uart_name                = "sim",
            with_sdram               = with_sdram,
            sdram_module          = sdram_module,
            sdram_data_width      = sdram_data_width,
            integrated_rom_size      = 0x10000,
            integrated_main_ram_size = 0x00000000 if with_sdram \
                                        else 0x10000000 , # 256MB
            ) 
        self.platform.name = "sim"

        # CRG -----------------------------------------------------------------
        self.submodules.crg = CRG(platform.request("sys_clk"))

        ram_init = []

        # SDRAM ----------------------------------------------------
        if with_sdram:
            sdram_clk_freq   = int(100e6) # FIXME: use 100MHz timings
            sdram_module_cls = getattr(litedram_modules, sdram_module)
            sdram_rate       = "1:{}".format(
                    sdram_module_nphases[sdram_module_cls.memtype])
            sdram_module     = sdram_module_cls(sdram_clk_freq, sdram_rate)
            phy_settings     = get_sdram_phy_settings(
                            memtype    = sdram_module.memtype,
                            data_width = sdram_data_width,
                            clk_freq   = sdram_clk_freq)
            self.submodules.sdrphy = SDRAMPHYModel(sdram_module,
                                                   phy_settings,
                                                   init=ram_init
                                                    )
            self.register_sdram(
                            self.sdrphy,
                            sdram_module.geom_settings,
                            sdram_module.timing_settings)
            # FIXME: skip memtest to avoid corrupting memory
            self.add_constant("MEMTEST_BUS_SIZE",  128//16)
            self.add_constant("MEMTEST_DATA_SIZE", 128//16)
            self.add_constant("MEMTEST_ADDR_SIZE", 128//16)
            self.add_constant("MEMTEST_BUS_DEBUG", 1)
            self.add_constant("MEMTEST_ADDR_DEBUG", 1)
            self.add_constant("MEMTEST_DATA_DEBUG", 1)


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

        # capture pc from dmi
        pc = Signal(64)
        active_dbg = Signal()

        # increment counter, Stop after 100000 cycles
        uptime = Signal(64)
        self.sync += uptime.eq(uptime + 1)
        #self.sync += If(uptime == 1000000000000, Finish())

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
            (If(active_dbg & (dbg_addr == 0b10), # PC
                Display("pc : %016x", dbg_dout),
             ),
             If(dbg_addr == 0b10, # PC
                 pc.eq(dbg_dout),     # capture PC
             ),
             #If(dbg_addr == 0b11, # MSR
             #   Display("    msr: %016x", dbg_dout),
             #),
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

        # limit range of pc for debug reporting
        self.comb += active_dbg.eq((0x378c <= pc) & (pc <= 0x38d8))
        #self.comb += active_dbg.eq((0x0 < pc) & (pc < 0x58))
        #self.comb += active_dbg.eq(1)

        # get the MSR
        self.sync += If(active_dbg & (uptime[0:cyclewid] == 28),
            (dmi_addr.eq(0b11), # MSR
             dmi_req.eq(1),
             dmi_wen.eq(0),
            )
        )

        # read all 32 GPRs
        for i in range(32):
            self.sync += If(active_dbg & (uptime[0:cyclewid] == 30+(i*8)),
                (dmi_addr.eq(0b100), # GSPR addr
                 dmi_din.eq(i), # r1
                 dmi_req.eq(1),
                 dmi_wen.eq(1),
                )
            )

            self.sync += If(active_dbg & (uptime[0:cyclewid] == 34+(i*8)),
                (dmi_addr.eq(0b101), # GSPR data
                 dmi_req.eq(1),
                 dmi_wen.eq(0),
                )
            )

        # monitor bbus read/write
        self.sync += If(active_dbg & self.cpu.dbus.stb & self.cpu.dbus.ack,
            Display("    [%06x] dadr: %8x, we %d s %01x w %016x r: %016x",
                #uptime,
                0,
                self.cpu.dbus.adr,
                self.cpu.dbus.we,
                self.cpu.dbus.sel,
                self.cpu.dbus.dat_w,
                self.cpu.dbus.dat_r
            )
        )

        return

        # monitor ibus write
        self.sync += If(active_dbg & self.cpu.ibus.stb & self.cpu.ibus.ack &
                        self.cpu.ibus.we,
            Display("    [%06x] iadr: %8x, s %01x w %016x",
                #uptime,
                0,
                self.cpu.ibus.adr,
                self.cpu.ibus.sel,
                self.cpu.ibus.dat_w,
            )
        )
        # monitor ibus read
        self.sync += If(active_dbg & self.cpu.ibus.stb & self.cpu.ibus.ack &
                        ~self.cpu.ibus.we,
            Display("    [%06x] iadr: %8x, s %01x r %016x",
                #uptime,
                0,
                self.cpu.ibus.adr,
                self.cpu.ibus.sel,
                self.cpu.ibus.dat_r
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
