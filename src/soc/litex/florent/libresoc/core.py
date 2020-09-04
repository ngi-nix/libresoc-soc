import os

from migen import ClockSignal, ResetSignal, Signal, Instance, Cat

from litex.soc.interconnect import wishbone
from litex.soc.cores.cpu import CPU

CPU_VARIANTS = ["standard", "standard32"]


def make_wb_bus(prefix, obj):
    res = {}
    for o in ['stb', 'cyc', 'cti', 'bte', 'we', 'adr', 'dat_w', 'sel']:
        res['o_%s_%s' % (prefix, o)] = getattr(obj, o)
    for i in ['ack', 'err', 'dat_r']:
        res['i_%s_%s' % (prefix, i)] = getattr(obj, i)
    return res


class LibreSoC(CPU):
    name                 = "libre_soc"
    human_name           = "Libre-SoC"
    variants             = CPU_VARIANTS
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
        self.interrupt    = Signal(16)

        if variant == "standard32":
            self.data_width           = 32
            self.dbus = dbus = wishbone.Interface(data_width=32, adr_width=30)
        else:
            self.dbus = dbus = wishbone.Interface(data_width=64, adr_width=29)
            self.data_width           = 64
        self.ibus = ibus = wishbone.Interface(data_width=64, adr_width=29)

        self.xics_icp = icp = wishbone.Interface(data_width=32, adr_width=3)
        self.xics_ics = ics = wishbone.Interface(data_width=32, adr_width=14)

        self.ics_buses = [icp, ics]
        self.periph_buses = [ibus, dbus]
        self.memory_buses = []

        self.dmi_addr = Signal(4)
        self.dmi_din = Signal(64)
        self.dmi_dout = Signal(64)
        self.dmi_wr = Signal(1)
        self.dmi_ack = Signal(1)
        self.dmi_req = Signal(1)

        # # #

        self.cpu_params = dict(
            # Clock / Reset
            i_clk              = ClockSignal(),
            i_rst              = ResetSignal() | self.reset,

            # Monitoring / Debugging
            i_pc_i             = 0,
            i_pc_i_ok          = 0,
            i_core_bigendian_i = 0, # Signal(),
            o_busy_o           = Signal(),
            o_memerr_o         = Signal(),

            # interrupts
            i_int_level_i      = self.interrupt,

            # Debug bus
            i_dmi_addr_i          = self.dmi_addr,
            i_dmi_din             = self.dmi_din,
            o_dmi_dout            = self.dmi_dout,
            i_dmi_req_i           = self.dmi_req,
            i_dmi_we_i            = self.dmi_wr,
            o_dmi_ack_o           = self.dmi_ack,
        )

        # add wishbone buses to cpu params
        self.cpu_params.update(make_wb_bus("ibus_", ibus))
        self.cpu_params.update(make_wb_bus("dbus_", dbus))
        self.cpu_params.update(make_wb_bus("ics_wb_", ics))
        self.cpu_params.update(make_wb_bus("icp_wb_", icp))

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

