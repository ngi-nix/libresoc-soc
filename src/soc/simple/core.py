"""simple core

not in any way intended for production use.  connects up FunctionUnits to
Register Files in a brain-dead fashion that only permits one and only one
Function Unit to be operational.

the principle here is to take the Function Units, analyse their regspecs,
and turn their requirements for access to register file read/write ports
into groupings by Register File and Register File Port name.

under each grouping - by regfile/port - a list of Function Units that
need to connect to that port is created.  as these are a contended
resource a "Broadcast Bus" per read/write port is then also created,
with access to it managed by a PriorityPicker.

the brain-dead part of this module is that even though there is no
conflict of access, regfile read/write hazards are *not* analysed,
and consequently it is safer to wait for the Function Unit to complete
before allowing a new instruction to proceed.
"""

from nmigen import Elaboratable, Module, Signal
from nmigen.cli import rtlil

from nmutil.picker import PriorityPicker
from nmutil.util import treereduce

from soc.fu.compunits.compunits import AllFunctionUnits
from soc.regfile.regfiles import RegFiles
from soc.decoder.power_decoder import create_pdecode
from soc.decoder.power_decoder2 import PowerDecode2
from soc.experiment.l0_cache import TstL0CacheBuffer # test only
from soc.experiment.testmem import TestMemory # test only for instructions
import operator


# helper function for reducing a list of signals down to a parallel
# ORed single signal.
def ortreereduce(tree, attr="data_o"):
    return treereduce(tree, operator.or_, lambda x: getattr(x, attr))

# helper function to place full regs declarations first
def sort_fuspecs(fuspecs):
    res = []
    for (regname, fspec) in fuspecs.items():
        if regname.startswith("full"):
            res.append((regname, fspec))
    for (regname, fspec) in fuspecs.items():
        if not regname.startswith("full"):
            res.append((regname, fspec))
    return res # enumerate(res)


class NonProductionCore(Elaboratable):
    def __init__(self, addrwid=6, idepth=16):
        # single LD/ST funnel for memory access
        self.l0 = TstL0CacheBuffer(n_units=1, regwid=64, addrwid=addrwid)
        pi = self.l0.l0.dports[0].pi

        # Instruction memory
        self.imem = TestMemory(32, idepth)

        # function units (only one each)
        self.fus = AllFunctionUnits(pilist=[pi], addrwid=addrwid)

        # register files (yes plural)
        self.regs = RegFiles()

        # instruction decoder
        self.pdecode = pdecode = create_pdecode()
        self.pdecode2 = PowerDecode2(pdecode)   # instruction decoder

        # issue/valid/busy signalling
        self.ivalid_i = self.pdecode2.e.valid   # instruction is valid
        self.issue_i = Signal(reset_less=True)
        self.busy_o = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()

        m.submodules.pdecode2 = dec2 = self.pdecode2
        m.submodules.fus = self.fus
        m.submodules.l0 = l0 = self.l0
        m.submodules.imem = imem = self.imem
        self.regs.elaborate_into(m, platform)
        regs = self.regs
        fus = self.fus.fus

        fu_bitdict = self.connect_instruction(m)
        self.connect_rdports(m, fu_bitdict)
        self.connect_wrports(m, fu_bitdict)

        return m

    def connect_instruction(self, m):
        comb, sync = m.d.comb, m.d.sync
        fus = self.fus.fus
        dec2 = self.pdecode2

        # enable-signals for each FU, get one bit for each FU (by name)
        fu_enable = Signal(len(fus), reset_less=True)
        fu_bitdict = {}
        for i, funame in enumerate(fus.keys()):
            fu_bitdict[funame] = fu_enable[i]

        # connect up instructions.  only one is enabled at any given time
        for funame, fu in fus.items():
            fnunit = fu.fnunit.value
            enable = Signal(name="en_%s" % funame, reset_less=True)
            comb += enable.eq(self.ivalid_i & (dec2.e.fn_unit & fnunit).bool())
            with m.If(enable):
                comb += fu.oper_i.eq_from_execute1(dec2.e)
                comb += fu.issue_i.eq(self.issue_i)
                comb += self.busy_o.eq(fu.busy_o)
                rdmask = dec2.rdflags(fu)
                comb += fu.rdmaskn.eq(~rdmask)
            comb += fu_bitdict[funame].eq(enable)

        return fu_bitdict

    def connect_rdports(self, m, fu_bitdict):
        """connect read ports

        orders the read regspecs into a dict-of-dicts, by regfile, by
        regport name, then connects all FUs that want that regport by
        way of a PriorityPicker.
        """
        comb, sync = m.d.comb, m.d.sync
        fus = self.fus.fus
        regs = self.regs

        # dictionary of lists of regfile read ports
        byregfiles_rd, byregfiles_rdspec = self.get_byregfiles(True)

        # okaay, now we need a PriorityPicker per regfile per regfile port
        # loootta pickers... peter piper picked a pack of pickled peppers...
        rdpickers = {}
        for regfile, spec in byregfiles_rd.items():
            fuspecs = byregfiles_rdspec[regfile]
            rdpickers[regfile] = {}

            # for each named regfile port, connect up all FUs to that port
            for (regname, fspec) in sort_fuspecs(fuspecs):
                print ("connect rd", regname, fspec)
                rpidx = regname
                # get the regfile specs for this regfile port
                (rf, read, write, wid, fuspec) = fspec
                name = "rdflag_%s_%s" % (regfile, regname)
                rdflag = Signal(name=name, reset_less=True)
                comb += rdflag.eq(rf)

                # select the required read port.  these are pre-defined sizes
                print (rpidx, regfile, regs.rf.keys())
                rport = regs.rf[regfile.lower()].r_ports[rpidx]

                # create a priority picker to manage this port
                rdpickers[regfile][rpidx] = rdpick = PriorityPicker(len(fuspec))
                setattr(m.submodules, "rdpick_%s_%s" % (regfile, rpidx), rdpick)

                # connect the regspec "reg select" number to this port
                with m.If(rdpick.en_o):
                    comb += rport.ren.eq(read)

                # connect up the FU req/go signals, and the reg-read to the FU
                # and create a Read Broadcast Bus
                for pi, (funame, fu, idx) in enumerate(fuspec):
                    src = fu.src_i[idx]

                    # connect request-read to picker input, and output to go-rd
                    fu_active = fu_bitdict[funame]
                    pick = fu.rd_rel_o[idx] & fu_active & rdflag
                    comb += rdpick.i[pi].eq(pick)
                    comb += fu.go_rd_i[idx].eq(rdpick.o[pi])

                    # connect regfile port to input, creating a Broadcast Bus
                    print ("reg connect widths",
                           regfile, regname, pi, funame,
                           src.shape(), rport.data_o.shape())
                    comb += src.eq(rport.data_o) # all FUs connect to same port

    def connect_wrports(self, m, fu_bitdict):
        """connect write ports

        orders the write regspecs into a dict-of-dicts, by regfile,
        by regport name, then connects all FUs that want that regport
        by way of a PriorityPicker.

        note that the write-port wen, write-port data, and go_wr_i all need to
        be on the exact same clock cycle.  as there is a combinatorial loop bug
        at the moment, these all use sync.
        """
        comb, sync = m.d.comb, m.d.sync
        fus = self.fus.fus
        regs = self.regs
        # dictionary of lists of regfile write ports
        byregfiles_wr, byregfiles_wrspec = self.get_byregfiles(False)

        # same for write ports.
        # BLECH!  complex code-duplication! BLECH!
        wrpickers = {}
        for regfile, spec in byregfiles_wr.items():
            fuspecs = byregfiles_wrspec[regfile]
            wrpickers[regfile] = {}
            for (regname, fspec) in sort_fuspecs(fuspecs):
                print ("connect wr", regname, fspec)
                rpidx = regname
                # get the regfile specs for this regfile port
                (rf, read, write, wid, fuspec) = fspec

                # select the required write port.  these are pre-defined sizes
                print (regfile, regs.rf.keys())
                wport = regs.rf[regfile.lower()].w_ports[rpidx]

                # create a priority picker to manage this port
                wrpickers[regfile][rpidx] = wrpick = PriorityPicker(len(fuspec))
                setattr(m.submodules, "wrpick_%s_%s" % (regfile, rpidx), wrpick)

                # connect the regspec write "reg select" number to this port
                # only if one FU actually requests (and is granted) the port
                # will the write-enable be activated
                with m.If(wrpick.en_o):
                    sync += wport.wen.eq(write)
                with m.Else():
                    sync += wport.wen.eq(0)

                # connect up the FU req/go signals and the reg-read to the FU
                # these are arbitrated by Data.ok signals
                wsigs = []
                for pi, (funame, fu, idx) in enumerate(fuspec):
                    # write-request comes from dest.ok
                    dest = fu.get_out(idx)
                    name = "wrflag_%s_%s_%d" % (funame, regname, idx)
                    wrflag = Signal(name=name, reset_less=True)
                    comb += wrflag.eq(dest.ok)

                    # connect request-read to picker input, and output to go-wr
                    fu_active = fu_bitdict[funame]
                    pick = fu.wr.rel[idx] & fu_active #& wrflag
                    comb += wrpick.i[pi].eq(pick)
                    sync += fu.go_wr_i[idx].eq(wrpick.o[pi] & wrpick.en_o)
                    # connect regfile port to input
                    print ("reg connect widths",
                           regfile, regname, pi, funame,
                           dest.shape(), wport.data_i.shape())
                    wsigs.append(dest)

                # here is where we create the Write Broadcast Bus. simple, eh?
                sync += wport.data_i.eq(ortreereduce(wsigs, "data"))

    def get_byregfiles(self, readmode):

        mode = "read" if readmode else "write"
        dec2 = self.pdecode2
        regs = self.regs
        fus = self.fus.fus

        # dictionary of lists of regfile ports
        byregfiles = {}
        byregfiles_spec = {}
        for (funame, fu) in fus.items():
            print ("%s ports for %s" % (mode, funame))
            for idx in range(fu.n_src if readmode else fu.n_dst):
                if readmode:
                    (regfile, regname, wid) = fu.get_in_spec(idx)
                else:
                    (regfile, regname, wid) = fu.get_out_spec(idx)
                print ("    %d %s %s %s" % (idx, regfile, regname, str(wid)))
                if readmode:
                    rdflag, read = dec2.regspecmap_read(regfile, regname)
                    write = None
                else:
                    rdflag, read = None, None
                    wrport, write = dec2.regspecmap_write(regfile, regname)
                if regfile not in byregfiles:
                    byregfiles[regfile] = {}
                    byregfiles_spec[regfile] = {}
                if regname not in byregfiles_spec[regfile]:
                    byregfiles_spec[regfile][regname] = \
                                [rdflag, read, write, wid, []]
                # here we start to create "lanes"
                if idx not in byregfiles[regfile]:
                    byregfiles[regfile][idx] = []
                fuspec = (funame, fu, idx)
                byregfiles[regfile][idx].append(fuspec)
                byregfiles_spec[regfile][regname][4].append(fuspec)

        # ok just print that out, for convenience
        for regfile, spec in byregfiles.items():
            print ("regfile %s ports:" % mode, regfile)
            fuspecs = byregfiles_spec[regfile]
            for regname, fspec in fuspecs.items():
                [rdflag, read, write, wid, fuspec] = fspec
                print ("  rf %s port %s lane: %s" % (mode, regfile, regname))
                print ("  %s" % regname, wid, read, write, rdflag)
                for (funame, fu, idx) in fuspec:
                    fusig = fu.src_i[idx] if readmode else fu.dest[idx]
                    print ("    ", funame, fu, idx, fusig)
                    print ()

        return byregfiles, byregfiles_spec

    def __iter__(self):
        yield from self.fus.ports()
        yield from self.pdecode2.ports()
        # TODO: regs

    def ports(self):
        return list(self)


if __name__ == '__main__':
    dut = NonProductionCore()
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("non_production_core.il", "w") as f:
        f.write(vl)
