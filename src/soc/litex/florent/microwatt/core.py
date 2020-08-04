# This file is Copyright (c) 2019 Florent Kermarrec <florent@enjoy-digital.fr>
# This file is Copyright (c) 2019 Benjamin Herrenschmidt <benh@ozlabs.org>
# License: BSD

import os

from migen import ClockSignal, ResetSignal, Signal, Instance, Cat

from litex.soc.interconnect import wishbone
from litex.soc.cores.cpu import CPU


CPU_VARIANTS = ["standard"]


class Microwatt(CPU):
    name                 = "microwatt"
    human_name           = "Microwatt"
    variants             = CPU_VARIANTS
    data_width           = 64
    endianness           = "little"
    gcc_triple           = ("powerpc64le-linux", "powerpc64le-linux-gnu")
    linker_output_format = "elf64-powerpcle"
    nop                  = "nop"
    io_regions           = {0xc0000000: 0x10000000} # origin, length

    @property
    def mem_map(self):
        return {"csr": 0xc0000000}

    @property
    def gcc_flags(self):
        flags  = "-m64 "
        flags += "-mabi=elfv2 "
        flags += "-msoft-float "
        flags += "-mno-string "
        flags += "-mno-multiple "
        flags += "-mno-vsx "
        flags += "-mno-altivec "
        flags += "-mlittle-endian "
        flags += "-mstrict-align "
        flags += "-fno-stack-protector "
        flags += "-mcmodel=small "
        flags += "-D__microwatt__ "
        return flags

    def __init__(self, platform, variant="standard"):
        self.platform     = platform
        self.variant      = variant
        self.reset        = Signal()
        self.ibus = ibus = wishbone.Interface(data_width=64, adr_width=29)
        self.dbus = dbus = wishbone.Interface(data_width=64, adr_width=29)
        self.periph_buses = [ibus, dbus]
        self.memory_buses = []

        # # #

        self.cpu_params = dict(
            # Clock / Reset
            i_clk                 = ClockSignal(),
            i_rst                 = ResetSignal() | self.reset,

            # Wishbone instruction bus
            i_wishbone_insn_dat_r = ibus.dat_r,
            i_wishbone_insn_ack   = ibus.ack,
            i_wishbone_insn_stall = ibus.cyc & ~ibus.ack, # No burst support

            o_wishbone_insn_adr   = Cat(Signal(3), ibus.adr),
            o_wishbone_insn_dat_w = ibus.dat_w,
            o_wishbone_insn_cyc   = ibus.cyc,
            o_wishbone_insn_stb   = ibus.stb,
            o_wishbone_insn_sel   = ibus.sel,
            o_wishbone_insn_we    = ibus.we,

            # Wishbone data bus
            i_wishbone_data_dat_r = dbus.dat_r,
            i_wishbone_data_ack   = dbus.ack,
            i_wishbone_data_stall = dbus.cyc & ~dbus.ack, # No burst support

            o_wishbone_data_adr   = Cat(Signal(3), dbus.adr),
            o_wishbone_data_dat_w = dbus.dat_w,
            o_wishbone_data_cyc   = dbus.cyc,
            o_wishbone_data_stb   = dbus.stb,
            o_wishbone_data_sel   = dbus.sel,
            o_wishbone_data_we    = dbus.we,

            # Debug bus
            i_dmi_addr            = 0,
            i_dmi_din             = 0,
            #o_dmi_dout           =,
            i_dmi_req             = 0,
            i_dmi_wr              = 0,
            #o_dmi_ack            =,
        )

        # add vhdl sources
        self.add_sources(platform)

    def set_reset_address(self, reset_address):
        assert not hasattr(self, "reset_address")
        self.reset_address = reset_address
        assert reset_address == 0x00000000

    @staticmethod
    def add_sources(platform):
        cdir = os.path.dirname(__file__)
        platform.add_source(os.path.join(cdir, "microwatt.v"))

    def do_finalize(self):
        self.specials += Instance("microwatt_wrapper", **self.cpu_params)
