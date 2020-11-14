import os

from migen import ClockSignal, ResetSignal, Signal, Instance, Cat

from litex.soc.interconnect import wishbone as wb
from litex.soc.cores.cpu import CPU

from soc.config.pinouts import get_pinspecs
from soc.debug.jtag import Pins
from c4m.nmigen.jtag.tap import IOType

from libresoc.ls180 import io
from litex.build.generic_platform import ConstraintManager


CPU_VARIANTS = ["standard", "standard32", "standardjtag",
                "standardjtagtestgpio", "ls180",
                "standardjtagnoirq"]


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
    cname = '%s_%s__core__%s' % (cpud, name, suffix)
    pname = '%s_%s__pad__%s' % (iod, name, suffix)
    print ("make pad", name, dirn, cpud, iod, cname, pname, suffix, cpup, iop)
    res[cname], res[pname] = cpup, iop

def get_field(rec, name):
    for f in rec.layout:
        f = f[0]
        if f.endswith(name):
            return getattr(rec, f)


def make_jtag_ioconn(res, pin, cpupads, iopads):
    (fn, pin, iotype, pin_name, scan_idx) = pin
    #serial_tx__core__o, serial_rx__pad__i,
    # special-case sdram_clock
    if pin == 'clock' and fn == 'sdr':
        cpu = cpupads['sdram_clock']
        io = iopads['sdram_clock']
    else:
        cpu = cpupads[fn]
        io = iopads[fn]
    print ("cpupads", cpupads)
    print ("iopads", iopads)
    print ("pin", fn, pin, iotype, pin_name)
    print ("cpu fn", cpu)
    print ("io fn", io)
    name = "%s_%s" % (fn, pin)
    print ("name", name)
    sigs = []

    if iotype in (IOType.In, IOType.Out):
        ps = pin.split("_")
        if pin == 'clock' and fn == 'sdr':
            cpup = cpu
            iop = io
        elif len(ps) == 2 and ps[-1].isdigit():
            pin, idx = ps
            idx = int(idx)
            print ("ps split", pin, idx)
            cpup = getattr(cpu, pin)[idx]
            iop = getattr(io, pin)[idx]
        elif pin.isdigit():
            idx = int(pin)
            print ("digit", idx)
            cpup = cpu[idx]
            iop = io[idx]
        else:
            cpup = getattr(cpu, pin)
            iop = getattr(io, pin)

    if iotype == IOType.Out:
        # output from the pad is routed through C4M JTAG and so
        # is an *INPUT* into core.  ls180soc connects this to "real" peripheral
        make_pad(res, True, name, "o", cpup, iop)

    elif iotype == IOType.In:
        # input to the pad is routed through C4M JTAG and so
        # is an *OUTPUT* into core.  ls180soc connects this to "real" peripheral
        make_pad(res, True, name, "i", cpup, iop)

    elif iotype == IOType.InTriOut:
        if fn == 'gpio': # sigh decode GPIO special-case
            idx = int(pin[1:])
            oe_idx = idx
        elif fn == 'sdr': # sigh
            idx = int(pin.split('_')[-1])
            oe_idx = 0
        else:
            idx = 0
            oe_idx = 0
        print ("gpio tri", fn, pin, iotype, pin_name, scan_idx, idx)
        cpup, iop = get_field(cpu, "i")[idx], get_field(io, "i")[idx]
        make_pad(res, True, name, "i", cpup, iop)
        cpup, iop = get_field(cpu, "o")[idx], get_field(io, "o")[idx]
        make_pad(res, True, name, "o", cpup, iop)
        cpup, iop = get_field(cpu, "oe")[oe_idx], get_field(io, "oe")[oe_idx]
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

        irq_en = "noirq" not in variant

        if irq_en:
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

        if "testgpio" in variant:
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
        )

        if irq_en:
            # interrupts
            self.cpu_params['i_int_level_i'] = self.interrupt

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

        # add clock select, pll output
        if variant == "ls180":
            self.pll_18_o = Signal()
            self.clk_sel = Signal(2)
            self.pll_lck_o = Signal()
            self.cpu_params['i_clk_sel_i'] = self.clk_sel
            self.cpu_params['o_pll_18_o'] = self.pll_18_o
            self.cpu_params['o_pll_lck_o'] = self.pll_lck_o

        # add wishbone buses to cpu params
        self.cpu_params.update(make_wb_bus("ibus", ibus))
        self.cpu_params.update(make_wb_bus("dbus", dbus))
        self.cpu_params.update(make_wb_slave("ics_wb", ics))
        self.cpu_params.update(make_wb_slave("icp_wb", icp))
        if "testgpio" in variant:
            self.cpu_params.update(make_wb_slave("gpio_wb", gpio))
        if jtag_en:
            self.cpu_params.update(make_wb_bus("jtag_wb", jtag_wb, simple=True))

        if variant == 'ls180':
            # urr yuk.  have to expose iopads / pins from core to litex
            # then back again.  cut _some_ of that out by connecting
            self.padresources = io()
            self.pad_cm = ConstraintManager(self.padresources, [])
            self.cpupads = {}
            iopads = {}
            litexmap = {}
            subset = {'uart', 'mtwi', 'eint', 'gpio', 'mspi0', 'mspi1',
                      'pwm', 'sd0', 'sdr'}
            for periph in subset:
                origperiph = periph
                num = None
                if periph[-1].isdigit():
                    periph, num = periph[:-1], int(periph[-1])
                print ("periph request", periph, num)
                if periph == 'mspi':
                    if num == 0:
                        periph, num = 'spimaster', None
                    else:
                        periph, num = 'spisdcard', None
                elif periph == 'sdr':
                    periph = 'sdram'
                elif periph == 'mtwi':
                    periph = 'i2c'
                elif periph == 'sd':
                    periph, num = 'sdcard', None
                litexmap[origperiph] = (periph, num)
                self.cpupads[origperiph] = platform.request(periph, num)
                iopads[origperiph] = self.pad_cm.request(periph, num)
                if periph == 'sdram':
                    # special-case sdram clock
                    ck = platform.request("sdram_clock")
                    self.cpupads['sdram_clock'] = ck
                    ck = self.pad_cm.request("sdram_clock")
                    iopads['sdram_clock'] = ck

            pinset = get_pinspecs(subset=subset)
            p = Pins(pinset)
            for pin in list(p):
                make_jtag_ioconn(self.cpu_params, pin, self.cpupads, iopads)

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

