import os

from migen import ClockSignal, ResetSignal, Signal, Instance, Cat

from litex.soc.interconnect import wishbone as wb
from litex.soc.cores.cpu import CPU

from soc.debug.jtag import Pins # TODO move to suitable location
from c4m.nmigen.jtag.tap import IOType

from libresoc.ls180io import make_uart, make_gpio
from litex.build.generic_platform import ConstraintManager


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

def make_pad(res, dirn, name, suffix, cpup, iop):
    cpud, iod = ('i', 'o') if dirn else ('o', 'i')
    res['%s_%s__%s' % (cpud, name, suffix)] = cpup
    res['%s_%s__%s' % (iod, name, suffix)] = iop


def make_jtag_ioconn(res, pin, cpupads, iopads):
    (fn, pin, iotype, pin_name) = pin
    #serial_tx__core__o, serial_rx__pad__i,
    print ("cpupads", cpupads)
    print ("iopads", iopads)
    print ("pin", fn, pin, iotype, pin_name)
    cpu = cpupads[fn]
    io = iopads[fn]
    sigs = []

    name = "%s_%s" % (fn, pin)

    if iotype in (IOType.In, IOType.Out):
        cpup = getattr(cpu, pin)
        iop = getattr(io, pin)

    if iotype == IOType.Out:
        # output from the pad is routed through C4M JTAG and so
        # is an *INPUT* into core.  ls180soc connects this to "real" peripheral
        make_pad(res, True, name, "o", cpup, iop)

    elif iotype == IOType.In:
        # input to the pad is routed through C4M JTAG and so
        # is an *OUTPUT* into core.  ls180soc connects this to "real" peripheral
        make_pad(res, False, name, "i", cpup, iop)

    elif iotype == IOType.InTriOut:
        if fn == 'gpio': # sigh decode GPIO special-case
            idx = int(pin[4:])
        cpup, iop = cpu.i[idx], io.i[idx]
        make_pad(res, False, name, "i", cpup, iop)
        cpup, iop = cpu.o[idx], io.o[idx]
        make_pad(res, True, name, "o", cpup, iop)
        cpup, iop = cpu.oe[idx], io.oe[idx]
        make_pad(res, True, name, "oe", cpup, iop)

    if iotype in (IOType.In, IOType.InTriOut):
        sigs.append(("i", 1))
    if iotype in (IOType.Out, IOType.TriOut, IOType.InTriOut):
        sigs.append(("o", 1))
    if iotype in (IOType.TriOut, IOType.InTriOut):
        sigs.append(("oe", 1))


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

        # urr yuk.  have to expose iopads / pins from core to litex
        # then back again.  cut _some_ of that out by connecting
        self.cpuresources = (make_uart('serial', 0),
                             make_gpio('gpio', 0, 16))
        self.padresources = (make_uart('serial', 0),
                             make_gpio('gpio', 0, 16))
        self.cpu_cm = ConstraintManager(self.cpuresources, [])
        self.pad_cm = ConstraintManager(self.cpuresources, [])
        self.cpupads = {'serial': self.cpu_cm.request('serial', 0),
                        'gpio': self.cpu_cm.request('gpio', 0)}
        self.iopads = {'serial': self.pad_cm.request('serial', 0),
                        'gpio': self.pad_cm.request('gpio', 0)}

        p = Pins()
        for pin in list(p):
            make_jtag_ioconn(self.cpu_params, pin, self.cpupads,
                                                   self.iopads)

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

