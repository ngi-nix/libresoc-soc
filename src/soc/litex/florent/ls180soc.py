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
from litex.soc.integration.common import get_mem_data

from litedram import modules as litedram_modules
from litedram.phy.model import SDRAMPHYModel
from litedram.phy.gensdrphy import GENSDRPHY, HalfRateGENSDRPHY

from litex.tools.litex_sim import sdram_module_nphases, get_sdram_phy_settings

from litex.tools.litex_sim import Platform
from libresoc.ls180 import LS180Platform

from libresoc import LibreSoC
from microwatt import Microwatt

# HACK!
from litex.soc.integration.soc import SoCCSRHandler
SoCCSRHandler.supported_address_width.append(12)

# LibreSoCSim -----------------------------------------------------------------

class LibreSoCSim(SoCCore):
    def __init__(self, cpu="libresoc", debug=False, with_sdram=True,
            sdram_module          = "AS4C16M16",
            #sdram_data_width      = 16,
            #sdram_module          = "MT48LC16M16",
            sdram_data_width      = 16,
            irq_reserved_irqs = {'uart': 0},
            platform='sim',
            ):
        assert cpu in ["libresoc", "microwatt"]
        sys_clk_freq = int(100e6)

        if platform == 'sim':
            platform     = Platform()
            uart_name = "sim"
        elif platform == 'ls180':
            platform     = LS180Platform()
            uart_name = "serial"

        #cpu_data_width = 32
        cpu_data_width = 64

        if cpu_data_width == 32:
            variant = "standard32"
        else:
            variant = "standard"

        #ram_fname = "/home/lkcl/src/libresoc/microwatt/" \
        #            "hello_world/hello_world.bin"
        #ram_fname = "/home/lkcl/src/libresoc/microwatt/" \
        #            "tests/1.bin"
        #ram_fname = "/tmp/test.bin"
        #ram_fname = None
        #ram_fname = "/home/lkcl/src/libresoc/microwatt/" \
        #            "micropython/firmware.bin"
        #ram_fname = "/home/lkcl/src/libresoc/microwatt/" \
        #            "tests/xics/xics.bin"
        ram_fname = "/home/lkcl/src/libresoc/microwatt/" \
                    "tests/decrementer/decrementer.bin"
        #ram_fname = "/home/lkcl/src/libresoc/microwatt/" \
        #            "hello_world/hello_world.bin"

        # reserve XICS ICP and XICS memory addresses.
        self.mem_map['icp'] = 0xc0004000
        self.mem_map['ics'] = 0xc0005000
        self.mem_map['gpio'] = 0xc0007000
        #self.csr_map["icp"] = 8  #  8 x 0x800 == 0x4000
        #self.csr_map["ics"] = 10 # 10 x 0x800 == 0x5000

        ram_init = []
        if ram_fname:
            #ram_init = get_mem_data({
            #    ram_fname:       "0x00000000",
            #    }, "little")
            ram_init = get_mem_data(ram_fname, "little")

            # remap the main RAM to reset-start-address
            self.mem_map["main_ram"] = 0x00000000

            # without sram nothing works, therefore move it to higher up
            self.mem_map["sram"] = 0x90000000

            # put UART at 0xc000200 (w00t!  this works!)
            self.csr_map["uart"] = 4


        # SoCCore -------------------------------------------------------------
        SoCCore.__init__(self, platform, clk_freq=sys_clk_freq,
            cpu_type                 = "microwatt",
            cpu_cls                  = LibreSoC   if cpu == "libresoc" \
                                       else Microwatt,
            #bus_data_width           = 64,
            csr_address_width        = 12, # limit to 0x4000
            cpu_variant              = variant,
            csr_data_width            = 8,
            l2_size             = 0,
            uart_name                = uart_name,
            with_sdram               = with_sdram,
            sdram_module          = sdram_module,
            sdram_data_width      = sdram_data_width,
            integrated_rom_size      = 0 if ram_fname else 0x10000,
            integrated_sram_size     = 0x40000,
            #integrated_main_ram_init  = ram_init,
            integrated_main_ram_size = 0x00000000 if with_sdram \
                                        else 0x10000000 , # 256MB
            )
        self.platform.name = "sim"

        # SDR SDRAM ----------------------------------------------
        if False: # not self.integrated_main_ram_size:
            self.submodules.sdrphy = sdrphy_cls(platform.request("sdram"))


        if cpu == "libresoc":
            # XICS interrupt devices
            icp_addr = self.mem_map['icp']
            icp_wb = self.cpu.xics_icp
            icp_region = SoCRegion(origin=icp_addr, size=0x20, cached=False)
            self.bus.add_slave(name='icp', slave=icp_wb, region=icp_region)

            ics_addr = self.mem_map['ics']
            ics_wb = self.cpu.xics_ics
            ics_region = SoCRegion(origin=ics_addr, size=0x1000, cached=False)
            self.bus.add_slave(name='ics', slave=ics_wb, region=ics_region)

            # Simple GPIO peripheral
            gpio_addr = self.mem_map['gpio']
            gpio_wb = self.cpu.simple_gpio
            gpio_region = SoCRegion(origin=gpio_addr, size=0x20, cached=False)
            self.bus.add_slave(name='gpio', slave=gpio_wb, region=gpio_region)


        # CRG -----------------------------------------------------------------
        self.submodules.crg = CRG(platform.request("sys_clk"))

        #ram_init = []

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
            #sdrphy_cls = HalfRateGENSDRPHY 
            sdrphy_cls = GENSDRPHY
            self.submodules.sdrphy = sdrphy_cls(platform.request("sdram"))
            #self.submodules.sdrphy = sdrphy_cls(sdram_module,
            #                                       phy_settings,
            #                                       init=ram_init
            #                                        )
            self.add_sdram("sdram",
                phy                     = self.sdrphy,
                module                  = sdram_module,
                origin                  = self.mem_map["main_ram"],
                size                    = 0x40000000,
                l2_cache_size           = 0, # 8192
                l2_cache_min_data_width = 128,
                l2_cache_reverse        = True
            )
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
        dmi_addr = Signal(4)
        dmi_din = Signal(64)
        dmi_dout = Signal(64)
        dmi_wen = Signal(1)
        dmi_req = Signal(1)

        # debug log out
        dbg_addr = Signal(4)
        dbg_dout = Signal(64)
        dbg_msg = Signal(1)

        # capture pc from dmi
        pc = Signal(64)
        active_dbg = Signal()
        active_dbg_cr = Signal()
        active_dbg_xer = Signal()

        # xer flags
        xer_so = Signal()
        xer_ca = Signal()
        xer_ca32 = Signal()
        xer_ov = Signal()
        xer_ov32 = Signal()

        # increment counter, Stop after 100000 cycles
        uptime = Signal(64)
        self.sync += uptime.eq(uptime + 1)
        #self.sync += If(uptime == 1000000000000, Finish())

        # DMI FSM counter and FSM itself
        dmicount = Signal(10)
        dmirunning = Signal(1)
        dmi_monitor = Signal(1)
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
                    # acknowledge received: capture data.
                    (NextState("IDLE"),
                     NextValue(dbg_addr, dmi_addr),
                     NextValue(dbg_dout, self.cpu.dmi_dout),
                     NextValue(dbg_msg, 1),
                    ),
                 ),
                ),
            )
        )

        # DMI response received: reset the dmi request and check if
        # in "monitor" mode
        dmifsm.act("IDLE",
            If(dmi_monitor,
                 NextState("FIRE_MONITOR"), # fire "monitor" on next cycle
            ).Else(
                 NextState("START"), # back to start on next cycle
            ),
            NextValue(dmi_req, 0),
            NextValue(dmi_addr, 0),
            NextValue(dmi_din, 0),
            NextValue(dmi_wen, 0),
        )

        # "monitor" mode fires off a STAT request
        dmifsm.act("FIRE_MONITOR",
            (NextValue(dmi_req, 1),
             NextValue(dmi_addr, 1), # DMI STAT address
             NextValue(dmi_din, 0),
             NextValue(dmi_wen, 0), # read STAT
             NextState("START"), # back to start on next cycle
            )
        )

        self.comb += xer_so.eq((dbg_dout & 1) == 1)
        self.comb += xer_ca.eq((dbg_dout & 4) == 4)
        self.comb += xer_ca32.eq((dbg_dout & 8) == 8)
        self.comb += xer_ov.eq((dbg_dout & 16) == 16)
        self.comb += xer_ov32.eq((dbg_dout & 32) == 32)

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
             If(dbg_addr == 0b1000, # CR
                Display("    cr : %016x", dbg_dout),
             ),
             If(dbg_addr == 0b1001, # XER
                Display("    xer: so %d ca %d 32 %d ov %d 32 %d",
                            xer_so, xer_ca, xer_ca32, xer_ov, xer_ov32),
             ),
             If(dbg_addr == 0b101, # GPR
                Display("    gpr: %016x", dbg_dout),
             ),
            # also check if this is a "stat"
            If(dbg_addr == 1, # requested a STAT
                #Display("    stat: %x", dbg_dout),
                If(dbg_dout & 2, # bit 2 of STAT is "stopped" mode
                     dmirunning.eq(1), # continue running
                     dmi_monitor.eq(0), # and stop monitor mode
                ),
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

        self.sync += If(uptime == 4,
             dmirunning.eq(1),
        )

        self.sync += If(dmirunning,
             dmicount.eq(dmicount + 1),
        )

        # loop every 1<<N cycles
        cyclewid = 9

        # get the PC
        self.sync += If(dmicount == 4,
            (dmi_addr.eq(0b10), # NIA
             dmi_req.eq(1),
             dmi_wen.eq(0),
            )
        )

        # kick off a "step"
        self.sync += If(dmicount == 8,
            (dmi_addr.eq(0), # CTRL
             dmi_din.eq(1<<3), # STEP
             dmi_req.eq(1),
             dmi_wen.eq(1),
             dmirunning.eq(0), # stop counter, need to fire "monitor"
             dmi_monitor.eq(1), # start "monitor" instead
            )
        )

        # limit range of pc for debug reporting
        #self.comb += active_dbg.eq((0x378c <= pc) & (pc <= 0x38d8))
        #self.comb += active_dbg.eq((0x0 < pc) & (pc < 0x58))
        self.comb += active_dbg.eq(1)


        # get the MSR
        self.sync += If(active_dbg & (dmicount == 12),
            (dmi_addr.eq(0b11), # MSR
             dmi_req.eq(1),
             dmi_wen.eq(0),
            )
        )

        if cpu == "libresoc":
            #self.comb += active_dbg_cr.eq((0x10300 <= pc) & (pc <= 0x12600))
            self.comb += active_dbg_cr.eq(0)

            # get the CR
            self.sync += If(active_dbg_cr & (dmicount == 16),
                (dmi_addr.eq(0b1000), # CR
                 dmi_req.eq(1),
                 dmi_wen.eq(0),
                )
            )

            #self.comb += active_dbg_xer.eq((0x10300 <= pc) & (pc <= 0x1094c))
            self.comb += active_dbg_xer.eq(active_dbg_cr)

            # get the CR
            self.sync += If(active_dbg_xer & (dmicount == 20),
                (dmi_addr.eq(0b1001), # XER
                 dmi_req.eq(1),
                 dmi_wen.eq(0),
                )
            )

        # read all 32 GPRs
        for i in range(32):
            self.sync += If(active_dbg & (dmicount == 24+(i*8)),
                (dmi_addr.eq(0b100), # GSPR addr
                 dmi_din.eq(i), # r1
                 dmi_req.eq(1),
                 dmi_wen.eq(1),
                )
            )

            self.sync += If(active_dbg & (dmicount == 28+(i*8)),
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
    parser.add_argument("--platform",     default="sim",
                        help="platform (sim or ls180)")
    parser.add_argument("--debug",        action="store_true",
                        help="Enable debug traces")
    parser.add_argument("--trace",        action="store_true",
                        help="Enable tracing")
    parser.add_argument("--trace-start",  default=0,
                        help="Cycle to start FST tracing")
    parser.add_argument("--trace-end",    default=-1,
                        help="Cycle to end FST tracing")
    parser.add_argument("--build", action="store_true", help="Build bitstream")
    args = parser.parse_args()


    if args.platform == 'ls180':
        soc = LibreSoCSim(cpu=args.cpu, debug=args.debug,
                          platform=args.platform)
        #soc.add_sdcard()
        builder = Builder(soc, compile_gateware = True)
        builder.build(run         = True)
        os.chdir("../")
    else:

        sim_config = SimConfig(default_clk="sys_clk")
        sim_config.add_module("serial2console", "serial")

        for i in range(2):
            soc = LibreSoCSim(cpu=args.cpu, debug=args.debug,
                              platform=args.platform)
            builder = Builder(soc, compile_gateware = i!=0)
            builder.build(sim_config=sim_config,
                run         = i!=0,
                trace       = args.trace,
                trace_start = int(args.trace_start),
                trace_end   = int(args.trace_end),
                trace_fst   = 0)
            os.chdir("../")

if __name__ == "__main__":
    main()
