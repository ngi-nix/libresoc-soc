# Copyright (c) 2018 Jean-François Nguyen <jf@lambdaconcept.fr>
# Copyright (c) 2018-2019 Florent Kermarrec <florent@enjoy-digital.fr>
# License: BSD

import os
import subprocess

from migen import *

from litex import get_data_mod
from litex.soc.interconnect import wishbone
from litex.soc.cores.cpu import CPU, CPU_GCC_TRIPLE_RISCV32

CPU_VARIANTS = ["standard"]


class LibreSOC(CPU):
    name                 = "libre-soc"
    human_name           = "Libre-SOC"
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
        flags += "-D__microwatt__ "
        return flags

    def __init__(self, platform, variant="standard"):
        self.platform     = platform
        self.variant      = variant
        self.reset        = Signal()
        self.interrupt    = Signal(32)

        self.pc           = Signal(64) # new program counter
        self.pc_ok        = Signal()   # change PC
        self.core_start   = Signal()   # stop the core
        self.core_stop    = Signal()   # start the core
        self.bigendian    = Signal()   # set to 1 for bigendian
        self.core_halted  = Signal()   # core is halted
        self.core_busy    = Signal()   # core is running (busy)

        # instruction and data bus: 64-bit, 48 bit addressing
        self.ibus         = wishbone.Interface(data_width=64, adr_width=48)
        self.dbus         = wishbone.Interface(data_width=64, adr_width=48)

        self.periph_buses = [self.ibus, self.dbus]
        self.memory_buses = []

        # TODO: create variants

        # # #

        self.cpu_params = dict(
            # clock / reset
            i_clk=ClockSignal(),
            i_rst=ResetSignal() | self.reset,

            # TODO interrupts
            #i_timer_interrupt    = 0,
            #i_software_interrupt = 0,
            #i_external_interrupt = self.interrupt,

            # ibus
            o_ibus__stb   = self.ibus.stb,
            o_ibus__cyc   = self.ibus.cyc,
            o_ibus__cti   = self.ibus.cti,
            o_ibus__bte   = self.ibus.bte,
            o_ibus__we    = self.ibus.we,
            o_ibus__adr   = Cat(Signal(3), self.ibus.adr), # 64-bit
            o_ibus__dat_w = self.ibus.dat_w,
            o_ibus__sel   = self.ibus.sel,
            i_ibus__ack   = self.ibus.ack,
            i_ibus__err   = self.ibus.err,
            i_ibus__dat_r = self.ibus.dat_r,

            # dbus
            o_dbus__stb   = self.dbus.stb,
            o_dbus__cyc   = self.dbus.cyc,
            o_dbus__cti   = self.dbus.cti,
            o_dbus__bte   = self.dbus.bte,
            o_dbus__we    = self.dbus.we,
            o_dbus__adr   = Cat(Signal(3), self.dbus.adr), # 64-bit
            o_dbus__dat_w = self.dbus.dat_w,
            o_dbus__sel   = self.dbus.sel,
            i_dbus__ack   = self.dbus.ack,
            i_dbus__err   = self.dbus.err,
            i_dbus__dat_r = self.dbus.dat_r,

            # monitoring / debugging
            i_go_insn_i        = 1,  # set to "always running"
            i_pc_i             = self.pc,
            i_ pc_i_ok         = self.pc_ok,
            i_core_start_i     = self.core_start,
            i_core_stop_i      = self.core_stop,
            i_core_bigendian_i = self.bigendian,
            o_halted_o         = self.core_halted,
            o_busy_o           = self.core_busy
        )

    def set_reset_address(self, reset_address):
        assert not hasattr(self, "reset_address")
        self.reset_address = reset_address
        assert reset_address == 0x00000000

    @staticmethod
    def elaborate(verilog_filename):
        cli_params = []
        sdir = get_data_mod("cpu", "libre-soc").data_location
        if subprocess.call(["python3", os.path.join(sdir, "cli.py"),
                            *cli_params, verilog_filename],
                            ):
            raise OSError("Unable to elaborate Libre-SOC CPU, "
                          "please check your nMigen/Yosys install")

    def do_finalize(self):
        verilog_filename = os.path.join(self.platform.output_dir,
                                        "gateware", "libre-soc.v")
        self.elaborate(
            verilog_filename = verilog_filename)
        self.platform.add_source(verilog_filename)
        self.specials += Instance("test_issuer", **self.cpu_params)

