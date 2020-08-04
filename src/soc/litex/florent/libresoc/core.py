import os

from migen import *

from litex.soc.interconnect import wishbone
from litex.soc.cores.cpu import CPU

CPU_VARIANTS = ["standard"]


class LibreSoC(CPU):
    name                 = "libre_soc"
    human_name           = "Libre-SoC"
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

        self.ibus         = wishbone.Interface(data_width=64, adr_width=29)
        self.dbus         = wishbone.Interface(data_width=64, adr_width=29)

        self.periph_buses = [self.ibus, self.dbus]
        self.memory_buses = []

        # # #

        self.cpu_params = dict(
            # Clock / Reset
            i_clk              = ClockSignal(),
            i_rst              = ResetSignal() | self.reset,

            # IBus
            o_ibus__stb        = self.ibus.stb,
            o_ibus__cyc        = self.ibus.cyc,
            o_ibus__cti        = self.ibus.cti,
            o_ibus__bte        = self.ibus.bte,
            o_ibus__we         = self.ibus.we,
            o_ibus__adr        = Cat(self.ibus.adr), # bytes to words addressing
            o_ibus__dat_w      = self.ibus.dat_w,
            o_ibus__sel        = self.ibus.sel,
            i_ibus__ack        = self.ibus.ack,
            i_ibus__err        = self.ibus.err,
            i_ibus__dat_r      = self.ibus.dat_r,

            # DBus
            o_dbus__stb        = self.dbus.stb,
            o_dbus__cyc        = self.dbus.cyc,
            o_dbus__cti        = self.dbus.cti,
            o_dbus__bte        = self.dbus.bte,
            o_dbus__we         = self.dbus.we,
            o_dbus__adr        = Cat(self.dbus.adr), # bytes to words addressing
            o_dbus__dat_w      = self.dbus.dat_w,
            o_dbus__sel        = self.dbus.sel,
            i_dbus__ack        = self.dbus.ack,
            i_dbus__err        = self.dbus.err,
            i_dbus__dat_r      = self.dbus.dat_r,

            # Monitoring / Debugging
            i_go_insn_i        = 1,
            i_pc_i             = 0,
            i_pc_i_ok          = 0,
            i_core_start_i     = Signal(),
            i_core_stop_i      = Signal(),
            i_core_bigendian_i = 0, # Signal(),
            o_halted_o         = Signal(),
            o_busy_o           = Signal()
        )

        # add verilog sources
        self.add_sources(platform)

    def set_reset_address(self, reset_address):
        assert not hasattr(self, "reset_address")
        self.reset_address = reset_address
        assert reset_address == 0x00000000

    @staticmethod
    def add_sources(platform):
        cdir = os.path.dirname(__file__)
        platform.add_source(os.path.join(cdir, "libresoc.v"))

    def do_finalize(self):
        self.specials += Instance("test_issuer", **self.cpu_params)

