import os

from migen import ClockSignal, ResetSignal, Signal, Instance, Cat

from litex.soc.interconnect import wishbone as wb
from litex.soc.cores.cpu import CPU

CPU_VARIANTS = ["standard", "standard32", "standardjtag", "ls180"]


def make_wb_bus(prefix, obj, simple=False):
    res = {}
    outpins = ['stb', 'cyc', 'we', 'adr', 'dat_w', 'sel']
    if not simple:
        outpins += ['cti', 'bte']
    for o in outpins:
        res['o_%s__%s' % (prefix, o)] = getattr(obj, o)
    for i in ['ack', 'err', 'dat_r']:
        res['i_%s__%s' % (prefix, i)] = getattr(obj, i)
    return res

def make_wb_slave(prefix, obj):
    res = {}
    for i in ['stb', 'cyc', 'cti', 'bte', 'we', 'adr', 'dat_w', 'sel']:
        res['i_%s__%s' % (prefix, i)] = getattr(obj, i)
    for o in ['ack', 'err', 'dat_r']:
        res['o_%s__%s' % (prefix, o)] = getattr(obj, o)
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
            self.dbus = dbus = wb.Interface(data_width=32, adr_width=30)
        else:
            self.dbus = dbus = wb.Interface(data_width=64, adr_width=29)
            self.data_width           = 64
        self.ibus = ibus = wb.Interface(data_width=64, adr_width=29)

        self.xics_icp = icp = wb.Interface(data_width=32, adr_width=30)
        self.xics_ics = ics = wb.Interface(data_width=32, adr_width=30)

        jtag_en = ('jtag' in variant) or variant == 'ls180'

        if variant != "ls180":
            self.simple_gpio = gpio = wb.Interface(data_width=32, adr_width=30)
        if jtag_en:
            self.jtag_wb = jtag_wb = wb.Interface(data_width=64, adr_width=29)

        self.periph_buses = [ibus, dbus]
        self.memory_buses = []

        if jtag_en:
            self.periph_buses.append(jtag_wb)
            self.jtag_tck = Signal(1)
            self.jtag_tms = Signal(1)
            self.jtag_tdi = Signal(1)
            self.jtag_tdo = Signal(1)
        else:
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
            o_busy_o           = Signal(),   # not connected
            o_memerr_o         = Signal(),   # not connected
            o_pc_o             = Signal(64), # not connected

            # interrupts
            i_int_level_i      = self.interrupt,

        )

        if jtag_en:
            self.cpu_params.update(dict(
                # JTAG Debug bus
                o_TAP_bus__tdo = self.jtag_tdo,
                i_TAP_bus__tdi = self.jtag_tdi,
                i_TAP_bus__tms = self.jtag_tms,
                i_TAP_bus__tck = self.jtag_tck,
            ))
        else:
            self.cpu_params.update(dict(
                # DMI Debug bus
                i_dmi_addr_i          = self.dmi_addr,
                i_dmi_din             = self.dmi_din,
                o_dmi_dout            = self.dmi_dout,
                i_dmi_req_i           = self.dmi_req,
                i_dmi_we_i            = self.dmi_wr,
                o_dmi_ack_o           = self.dmi_ack,
            ))

        # add wishbone buses to cpu params
        self.cpu_params.update(make_wb_bus("ibus", ibus))
        self.cpu_params.update(make_wb_bus("dbus", dbus))
        self.cpu_params.update(make_wb_slave("ics_wb", ics))
        self.cpu_params.update(make_wb_slave("icp_wb", icp))
        if variant != "ls180":
            self.cpu_params.update(make_wb_slave("gpio_wb", gpio))
        if jtag_en:
            self.cpu_params.update(make_wb_bus("jtag_wb", jtag_wb, simple=True))

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

