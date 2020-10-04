#!/usr/bin/env python3

import os
import argparse
from functools import reduce
from operator import or_

from migen import (Signal, FSM, If, Display, Finish, NextValue, NextState,
                   Cat, Record, ClockSignal, wrap, ResetInserter)

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
#from litedram.phy.gensdrphy import GENSDRPHY, HalfRateGENSDRPHY
from litedram.common import PHYPadsCombiner, PhySettings
from litedram.phy.dfi import Interface as DFIInterface
from litex.soc.cores.spi import SPIMaster
from litex.soc.cores.pwm import PWM
#from litex.soc.cores.bitbang import I2CMaster
from litex.soc.cores import uart

from litex.tools.litex_sim import sdram_module_nphases, get_sdram_phy_settings

from litex.tools.litex_sim import Platform
from libresoc.ls180 import LS180Platform

from migen import Module
from litex.soc.interconnect.csr import AutoCSR

from libresoc import LibreSoC
from microwatt import Microwatt

# HACK!
from litex.soc.integration.soc import SoCCSRHandler
SoCCSRHandler.supported_address_width.append(12)

# GPIO Tristate -------------------------------------------------------
# doesn't work properly.
#from litex.soc.cores.gpio import GPIOTristate
from litex.soc.interconnect.csr import CSRStorage, CSRStatus, CSRField
from migen.genlib.cdc import MultiReg

# Imports
from litex.soc.interconnect import wishbone
from litesdcard.phy import (SDPHY, SDPHYClocker,
                            SDPHYInit, SDPHYCMDW, SDPHYCMDR,
                            SDPHYDATAW, SDPHYDATAR,
                            _sdpads_layout)
from litesdcard.core import SDCore
from litesdcard.frontend.dma import SDBlock2MemDMA, SDMem2BlockDMA
from litex.build.io import SDROutput, SDRInput


# I2C Master Bit-Banging --------------------------------------------------

class I2CMaster(Module, AutoCSR):
    """I2C Master Bit-Banging

    Provides the minimal hardware to do software I2C Master bit banging.

    On the same write CSRStorage (_w), software can control SCL (I2C_SCL),
    SDA direction and value (I2C_OE, I2C_W). Software get back SDA value
    with the read CSRStatus (_r).
    """
    pads_layout = [("scl", 1), ("sda", 1)]
    def __init__(self, pads):
        self.pads = pads
        self._w = CSRStorage(fields=[
            CSRField("scl", size=1, offset=0),
            CSRField("oe",  size=1, offset=1),
            CSRField("sda", size=1, offset=2)],
            name="w")
        self._r = CSRStatus(fields=[
            CSRField("sda", size=1, offset=0)],
            name="r")

        self.connect(pads)

    def connect(self, pads):
        _sda_w  = Signal()
        _sda_oe = Signal()
        _sda_r  = Signal()
        self.comb += [
            pads.scl.eq(self._w.fields.scl),
            pads.sda_oe.eq( self._w.fields.oe),
            pads.sda_o.eq(  self._w.fields.sda),
            self._r.fields.sda.eq(pads.sda_i),
        ]


class GPIOTristateASIC(Module, AutoCSR):
    def __init__(self, pads):
        nbits     = len(pads.oe) # hack
        self._oe  = CSRStorage(nbits, description="GPIO Tristate(s) Control.")
        self._in  = CSRStatus(nbits,  description="GPIO Input(s) Status.")
        self._out = CSRStorage(nbits, description="GPIO Ouptut(s) Control.")

        # # #

        _pads = Record( (("i",  nbits),
                         ("o",  nbits),
                         ("oe", nbits)))
        self.comb += _pads.i.eq(pads.i)
        self.comb += pads.o.eq(_pads.o)
        self.comb += pads.oe.eq(_pads.oe)

        self.comb += _pads.oe.eq(self._oe.storage)
        self.comb += _pads.o.eq(self._out.storage)
        for i in range(nbits):
            self.specials += MultiReg(_pads.i[i], self._in.status[i])

# SDCard PHY IO -------------------------------------------------------

class SDRPad(Module):
    def __init__(self, pad, name, o, oe, i):
        clk = ClockSignal()
        _o = getattr(pad, "%s_o" % name)
        _oe = getattr(pad, "%s_oe" % name)
        _i = getattr(pad, "%s_i" % name)
        self.specials += SDROutput(clk=clk, i=oe, o=_oe)
        for j in range(len(_o)):
            self.specials += SDROutput(clk=clk, i=o[j], o=_o[j])
            self.specials += SDRInput(clk=clk, i=_i[j], o=i[j])


class SDPHYIOGen(Module):
    def __init__(self, clocker, sdpads, pads):
        # Rst
        if hasattr(pads, "rst"):
            self.comb += pads.rst.eq(0)

        # Clk
        self.specials += SDROutput(
            clk = ClockSignal(),
            i   = ~clocker.clk & sdpads.clk,
            o   = pads.clk
        )

        # Cmd
        c = sdpads.cmd
        self.submodules.sd_cmd = SDRPad(pads, "cmd", c.o, c.oe, c.i)

        # Data
        d = sdpads.data
        self.submodules.sd_data = SDRPad(pads, "data", d.o, d.oe, d.i)


class SDPHY(Module, AutoCSR):
    def __init__(self, pads, device, sys_clk_freq,
                 cmd_timeout=10e-3, data_timeout=10e-3):
        self.card_detect = CSRStatus() # Assume SDCard is present if no cd pin.
        self.comb += self.card_detect.status.eq(getattr(pads, "cd", 0))

        self.submodules.clocker = clocker = SDPHYClocker()
        self.submodules.init    = init    = SDPHYInit()
        self.submodules.cmdw    = cmdw    = SDPHYCMDW()
        self.submodules.cmdr    = cmdr    = SDPHYCMDR(sys_clk_freq,
                                                      cmd_timeout, cmdw)
        self.submodules.dataw   = dataw   = SDPHYDATAW()
        self.submodules.datar   = datar   = SDPHYDATAR(sys_clk_freq,
                                                      data_timeout)

        # # #

        self.sdpads = sdpads = Record(_sdpads_layout)

        # IOs
        sdphy_cls = SDPHYIOGen
        self.submodules.io = sdphy_cls(clocker, sdpads, pads)

        # Connect pads_out of submodules to physical pads --------------
        pl = [init, cmdw, cmdr, dataw, datar]
        self.comb += [
            sdpads.clk.eq(    reduce(or_, [m.pads_out.clk     for m in pl])),
            sdpads.cmd.oe.eq( reduce(or_, [m.pads_out.cmd.oe  for m in pl])),
            sdpads.cmd.o.eq(  reduce(or_, [m.pads_out.cmd.o   for m in pl])),
            sdpads.data.oe.eq(reduce(or_, [m.pads_out.data.oe for m in pl])),
            sdpads.data.o.eq( reduce(or_, [m.pads_out.data.o  for m in pl])),
        ]
        for m in pl:
            self.comb += m.pads_out.ready.eq(self.clocker.ce)

        # Connect physical pads to pads_in of submodules ---------------
        for m in pl:
            self.comb += m.pads_in.valid.eq(self.clocker.ce)
            self.comb += m.pads_in.cmd.i.eq(sdpads.cmd.i)
            self.comb += m.pads_in.data.i.eq(sdpads.data.i)

        # Speed Throttling -------------------------------------------
        self.comb += clocker.stop.eq(dataw.stop | datar.stop)


# Generic SDR PHY ---------------------------------------------------------

class GENSDRPHY(Module):
    def __init__(self, pads, cl=2, cmd_latency=1):
        pads        = PHYPadsCombiner(pads)
        addressbits = len(pads.a)
        bankbits    = len(pads.ba)
        nranks      = 1 if not hasattr(pads, "cs_n") else len(pads.cs_n)
        databits    = len(pads.dq_i)
        assert cl in [2, 3]
        assert databits%8 == 0

        # PHY settings ----------------------------------------------------
        self.settings = PhySettings(
            phytype       = "GENSDRPHY",
            memtype       = "SDR",
            databits      = databits,
            dfi_databits  = databits,
            nranks        = nranks,
            nphases       = 1,
            rdphase       = 0,
            wrphase       = 0,
            rdcmdphase    = 0,
            wrcmdphase    = 0,
            cl            = cl,
            read_latency  = cl + cmd_latency,
            write_latency = 0
        )

        # DFI Interface ---------------------------------------------------
        self.dfi = dfi = DFIInterface(addressbits, bankbits, nranks, databits)

        # # #

        # Iterate on pads groups ------------------------------------------
        for pads_group in range(len(pads.groups)):
            pads.sel_group(pads_group)

            # Addresses and Commands --------------------------------------
            p0 = dfi.p0
            self.specials += [SDROutput(i=p0.address[i], o=pads.a[i])
                                    for i in range(len(pads.a))]
            self.specials += [SDROutput(i=p0.bank[i], o=pads.ba[i])
                                    for i in range(len(pads.ba))]
            self.specials += SDROutput(i=p0.cas_n, o=pads.cas_n)
            self.specials += SDROutput(i=p0.ras_n, o=pads.ras_n)
            self.specials += SDROutput(i=p0.we_n, o=pads.we_n)
            if hasattr(pads, "cke"):
                for i in range(len(pads.cke)):
                        self.specials += SDROutput(i=p0.cke[i], o=pads.cke[i])
            if hasattr(pads, "cs_n"):
                for i in range(len(pads.cs_n)):
                    self.specials += SDROutput(i=p0.cs_n[i], o=pads.cs_n[i])

        # DQ/DM Data Path -------------------------------------------------

        d = dfi.p0
        wren = []
        self.submodules.dq = SDRPad(pads, "dq", d.wrdata, d.wrdata_en, d.rddata)

        if hasattr(pads, "dm"):
            for i in range(len(pads.dm)):
                self.specials += SDROutput(i=d.wrdata_mask[i], o=pads.dm[i])

        # DQ/DM Control Path ----------------------------------------------
        rddata_en = Signal(cl + cmd_latency)
        self.sync += rddata_en.eq(Cat(dfi.p0.rddata_en, rddata_en))
        self.sync += dfi.p0.rddata_valid.eq(rddata_en[-1])


# LibreSoC 180nm ASIC -------------------------------------------------------

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
        sys_clk_freq = int(50e6)

        if platform == 'sim':
            platform     = Platform()
            uart_name = "sim"
        elif platform == 'ls180':
            platform     = LS180Platform()
            uart_name = "uart"

        #cpu_data_width = 32
        cpu_data_width = 64

        variant = "ls180"

        # reserve XICS ICP and XICS memory addresses.
        self.mem_map['icp']  = 0xc0010000
        self.mem_map['ics']  = 0xc0011000
        #self.csr_map["icp"] = 8  #  8 x 0x800 == 0x4000
        #self.csr_map["ics"] = 10 # 10 x 0x800 == 0x5000

        ram_init = []
        if False:
            #ram_init = get_mem_data({
            #    ram_fname:       "0x00000000",
            #    }, "little")
            ram_init = get_mem_data(ram_fname, "little")

            # remap the main RAM to reset-start-address

            # without sram nothing works, therefore move it to higher up
            self.mem_map["sram"] = 0x90000000

            # put UART at 0xc000200 (w00t!  this works!)
            self.csr_map["uart"] = 4

        self.mem_map["main_ram"] = 0x90000000
        self.mem_map["sram"] = 0x00000000

        # SoCCore -------------------------------------------------------------
        SoCCore.__init__(self, platform, clk_freq=sys_clk_freq,
            cpu_type                 = "microwatt",
            cpu_cls                  = LibreSoC   if cpu == "libresoc" \
                                       else Microwatt,
            #bus_data_width           = 64,
            csr_address_width        = 14, # limit to 0x8000
            cpu_variant              = variant,
            csr_data_width            = 8,
            l2_size             = 0,
            with_uart                = False,
            uart_name                = None,
            with_sdram               = with_sdram,
            sdram_module          = sdram_module,
            sdram_data_width      = sdram_data_width,
            integrated_rom_size      = 0, # if ram_fname else 0x10000,
            integrated_sram_size     = 0x200,
            #integrated_main_ram_init  = ram_init,
            integrated_main_ram_size = 0x00000000 if with_sdram \
                                        else 0x10000000 , # 256MB
            )
        self.platform.name = "ls180"

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

        # CRG -----------------------------------------------------------------
        self.submodules.crg = CRG(platform.request("sys_clk"),
                                  platform.request("sys_rst"))

        # PLL/Clock Select
        clksel_i = platform.request("sys_clksel_i")
        pll48_o = platform.request("sys_pll_48_o")

        self.comb += self.cpu.clk_sel.eq(clksel_i) # allow clock src select
        self.comb += pll48_o.eq(self.cpu.pll_48_o) # "test feed" from the PLL

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
                size                    = 0x80000000,
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

            # SDRAM clock
            sys_clk = ClockSignal()
            sdr_clk = platform.request("sdram_clock")
            #self.specials += DDROutput(1, 0, , sdram_clk)
            self.specials += SDROutput(clk=sys_clk, i=sys_clk, o=sdr_clk)

        # UART
        uart_core_pads = self.cpu.cpupads['uart']
        self.submodules.uart_phy = uart.UARTPHY(
                pads     = uart_core_pads,
                clk_freq = self.sys_clk_freq,
                baudrate = 115200)
        self.submodules.uart = ResetInserter()(uart.UART(self.uart_phy,
                tx_fifo_depth = 16,
                rx_fifo_depth = 16))

        self.csr.add("uart_phy", use_loc_if_exists=True)
        self.csr.add("uart", use_loc_if_exists=True)
        self.irq.add("uart", use_loc_if_exists=True)

        # GPIOs (bi-directional)
        gpio_core_pads = self.cpu.cpupads['gpio']
        self.submodules.gpio = GPIOTristateASIC(gpio_core_pads)
        self.add_csr("gpio")

        # SPI Master
        print ("cpupadkeys", self.cpu.cpupads.keys())
        self.submodules.spimaster = SPIMaster(
            pads         = self.cpu.cpupads['mspi1'],
            data_width   = 8,
            sys_clk_freq = sys_clk_freq,
            spi_clk_freq = 8e6,
        )
        self.add_csr("spimaster")

        # SPI SDCard (1 wide)
        spi_clk_freq = 400e3
        pads = self.cpu.cpupads['mspi0']
        spisdcard = SPIMaster(pads, 8, self.sys_clk_freq, spi_clk_freq)
        spisdcard.add_clk_divider()
        setattr(self.submodules, 'spisdcard', spisdcard)
        self.add_csr('spisdcard')

        # EINTs - very simple, wire up top 3 bits to ls180 "eint" pins
        eintpads = self.cpu.cpupads['eint']
        print ("eintpads", eintpads)
        self.comb += self.cpu.interrupt[12:16].eq(eintpads)

        # JTAG
        jtagpads = platform.request("jtag")
        self.comb += self.cpu.jtag_tck.eq(jtagpads.tck)
        self.comb += self.cpu.jtag_tms.eq(jtagpads.tms)
        self.comb += self.cpu.jtag_tdi.eq(jtagpads.tdi)
        self.comb += jtagpads.tdo.eq(self.cpu.jtag_tdo)

        # NC - allows some iopads to be connected up
        # sigh, just do something, anything, to stop yosys optimising these out
        nc_pads = platform.request("nc")
        num_nc = len(nc_pads)
        self.nc = Signal(num_nc)
        self.comb += self.nc.eq(nc_pads)
        self.dummy = Signal(num_nc)
        for i in range(num_nc):
            self.sync += self.dummy[i].eq(self.nc[i] | self.cpu.interrupt[0])

        # PWM
        pwmpads = self.cpu.cpupads['pwm']
        for i in range(2):
            name = "pwm%d" % i
            setattr(self.submodules, name, PWM(pwmpads[i]))
            self.add_csr(name)

        # I2C Master
        i2c_core_pads = self.cpu.cpupads['mtwi']
        self.submodules.i2c = I2CMaster(i2c_core_pads)
        self.add_csr("i2c")

        # SDCard -----------------------------------------------------

        # Emulator / Pads
        sdcard_pads = self.cpu.cpupads['sd0']

        # Core
        self.submodules.sdphy  = SDPHY(sdcard_pads,
                                       self.platform.device, self.clk_freq)
        self.submodules.sdcore = SDCore(self.sdphy)
        self.add_csr("sdphy")
        self.add_csr("sdcore")

        # Block2Mem DMA
        bus = wishbone.Interface(data_width=self.bus.data_width,
                                 adr_width=self.bus.address_width)
        self.submodules.sdblock2mem = SDBlock2MemDMA(bus=bus,
                                    endianness=self.cpu.endianness)
        self.comb += self.sdcore.source.connect(self.sdblock2mem.sink)
        dma_bus = self.bus if not hasattr(self, "dma_bus") else self.dma_bus
        dma_bus.add_master("sdblock2mem", master=bus)
        self.add_csr("sdblock2mem")

        # Mem2Block DMA
        bus = wishbone.Interface(data_width=self.bus.data_width,
                                 adr_width=self.bus.address_width)
        self.submodules.sdmem2block = SDMem2BlockDMA(bus=bus,
                                            endianness=self.cpu.endianness)
        self.comb += self.sdmem2block.source.connect(self.sdcore.sink)
        dma_bus = self.bus if not hasattr(self, "dma_bus") else self.dma_bus
        dma_bus.add_master("sdmem2block", master=bus)
        self.add_csr("sdmem2block")

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
