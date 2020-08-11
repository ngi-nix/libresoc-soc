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

from nmigen import Elaboratable, Module, Signal, ResetSignal, Cat
from nmigen.cli import rtlil

from nmutil.picker import PriorityPicker
from nmutil.util import treereduce

from soc.fu.compunits.compunits import AllFunctionUnits
from soc.regfile.regfiles import RegFiles
from soc.decoder.power_decoder import create_pdecode
from soc.decoder.power_decoder2 import PowerDecode2
from soc.decoder.decode2execute1 import Data
from soc.experiment.l0_cache import TstL0CacheBuffer  # test only
from soc.config.test.test_loadstore import TestMemPspec
from soc.decoder.power_enums import MicrOp
import operator

from nmutil.util import rising_edge


# helper function for reducing a list of signals down to a parallel
# ORed single signal.
def ortreereduce(tree, attr="data_o"):
    return treereduce(tree, operator.or_, lambda x: getattr(x, attr))


def ortreereduce_sig(tree):
    return treereduce(tree, operator.or_, lambda x: x)


# helper function to place full regs declarations first
def sort_fuspecs(fuspecs):
    res = []
    for (regname, fspec) in fuspecs.items():
        if regname.startswith("full"):
            res.append((regname, fspec))
    for (regname, fspec) in fuspecs.items():
        if not regname.startswith("full"):
            res.append((regname, fspec))
    return res  # enumerate(res)


class NonProductionCore(Elaboratable):
    def __init__(self, pspec):
        # single LD/ST funnel for memory access
        self.l0 = TstL0CacheBuffer(pspec, n_units=1)
        pi = self.l0.l0.dports[0]

        # function units (only one each)
        self.fus = AllFunctionUnits(pspec, pilist=[pi])

        # register files (yes plural)
        self.regs = RegFiles()

        # instruction decoder
        pdecode = create_pdecode()
        self.pdecode2 = PowerDecode2(pdecode)   # instruction decoder

        # issue/valid/busy signalling
        self.ivalid_i = self.pdecode2.valid   # instruction is valid
        self.issue_i = Signal(reset_less=True)
        self.busy_o = Signal(name="corebusy_o", reset_less=True)

        # instruction input
        self.bigendian_i = self.pdecode2.dec.bigendian
        self.raw_opcode_i = self.pdecode2.dec.raw_opcode_in

        # start/stop and terminated signalling
        self.core_stopped_i = Signal(reset_less=True)
        self.core_reset_i = Signal()
        self.core_terminate_o = Signal(reset=0)  # indicates stopped

    def elaborate(self, platform):
        m = Module()

        m.submodules.pdecode2 = dec2 = self.pdecode2
        m.submodules.fus = self.fus
        m.submodules.l0 = l0 = self.l0
        self.regs.elaborate_into(m, platform)
        regs = self.regs
        fus = self.fus.fus

        # connect up Function Units, then read/write ports
        fu_bitdict = self.connect_instruction(m)
        self.connect_rdports(m, fu_bitdict)
        self.connect_wrports(m, fu_bitdict)

        # connect up reset
        m.d.comb += ResetSignal().eq(self.core_reset_i)

        return m

    def connect_instruction(self, m):
        """connect_instruction

        uses decoded (from PowerOp) function unit information from CSV files
        to ascertain which Function Unit should deal with the current
        instruction.

        some (such as OP_ATTN, OP_NOP) are dealt with here, including
        ignoring it and halting the processor.  OP_NOP is a bit annoying
        because the issuer expects busy flag still to be raised then lowered.
        (this requires a fake counter to be set).
        """
        comb, sync = m.d.comb, m.d.sync
        fus = self.fus.fus
        dec2 = self.pdecode2

        # enable-signals for each FU, get one bit for each FU (by name)
        fu_enable = Signal(len(fus), reset_less=True)
        fu_bitdict = {}
        for i, funame in enumerate(fus.keys()):
            fu_bitdict[funame] = fu_enable[i]

        # enable the required Function Unit based on the opcode decode
        # note: this *only* works correctly for simple core when one and
        # *only* one FU is allocated per instruction
        for funame, fu in fus.items():
            fnunit = fu.fnunit.value
            enable = Signal(name="en_%s" % funame, reset_less=True)
            comb += enable.eq((dec2.e.do.fn_unit & fnunit).bool())
            comb += fu_bitdict[funame].eq(enable)

        # sigh - need a NOP counter
        counter = Signal(2)
        with m.If(counter != 0):
            sync += counter.eq(counter - 1)
            comb += self.busy_o.eq(1)

        with m.If(self.ivalid_i): # run only when valid
            with m.Switch(dec2.e.do.insn_type):
                # check for ATTN: halt if true
                with m.Case(MicrOp.OP_ATTN):
                    m.d.sync += self.core_terminate_o.eq(1)

                with m.Case(MicrOp.OP_NOP):
                    sync += counter.eq(2)
                    comb += self.busy_o.eq(1)

                with m.Default():
                    # connect up instructions.  only one enabled at a time
                    for funame, fu in fus.items():
                        enable = fu_bitdict[funame]

                        # run this FunctionUnit if enabled
                        with m.If(enable):
                            # route op, issue, busy, read flags and mask to FU
                            comb += fu.oper_i.eq_from_execute1(dec2.e)
                            comb += fu.issue_i.eq(self.issue_i)
                            comb += self.busy_o.eq(fu.busy_o)
                            rdmask = dec2.rdflags(fu)
                            comb += fu.rdmaskn.eq(~rdmask)

        return fu_bitdict

    def connect_rdport(self, m, fu_bitdict, rdpickers, regfile, regname, fspec):
        comb, sync = m.d.comb, m.d.sync
        fus = self.fus.fus
        regs = self.regs

        rpidx = regname

        # select the required read port.  these are pre-defined sizes
        print(rpidx, regfile, regs.rf.keys())
        rport = regs.rf[regfile.lower()].r_ports[rpidx]

        fspecs = fspec
        if not isinstance(fspecs, list):
            fspecs = [fspecs]

        rdflags = []
        pplen = 0
        reads = []
        ppoffs = []
        for i, fspec in enumerate(fspecs):
            # get the regfile specs for this regfile port
            (rf, read, write, wid, fuspec) = fspec
            print ("fpsec", i, fspec, len(fuspec))
            ppoffs.append(pplen) # record offset for picker
            pplen += len(fuspec)
            name = "rdflag_%s_%s_%d" % (regfile, regname, i)
            rdflag = Signal(name=name, reset_less=True)
            comb += rdflag.eq(rf)
            rdflags.append(rdflag)
            reads.append(read)

        print ("pplen", pplen)

        # create a priority picker to manage this port
        rdpickers[regfile][rpidx] = rdpick = PriorityPicker(pplen)
        setattr(m.submodules, "rdpick_%s_%s" % (regfile, rpidx), rdpick)

        for i, fspec in enumerate(fspecs):
            (rf, read, write, wid, fuspec) = fspec
            # connect up the FU req/go signals, and the reg-read to the FU
            # and create a Read Broadcast Bus
            for pi, (funame, fu, idx) in enumerate(fuspec):
                pi += ppoffs[i]
                src = fu.src_i[idx]

                # connect request-read to picker input, and output to go-rd
                fu_active = fu_bitdict[funame]
                pick = Signal()
                comb += pick.eq(fu.rd_rel_o[idx] & fu_active & rdflags[i])
                print (pick, len(pick))
                print (rdpick.i, len(rdpick.i), pi)
                comb += rdpick.i[pi].eq(pick)
                comb += fu.go_rd_i[idx].eq(rdpick.o[pi])

                # if picked, select read-port "reg select" number to port
                with m.If(rdpick.o[pi] & rdpick.en_o):
                    comb += rport.ren.eq(reads[i])

                    # connect regfile port to input, creating a Broadcast Bus
                    print("reg connect widths",
                          regfile, regname, pi, funame,
                          src.shape(), rport.data_o.shape())
                    # all FUs connect to same port
                    comb += src.eq(rport.data_o)

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

            # argh.  an experiment to merge RA and RB in the INT regfile
            # (we have too many read/write ports)
            if regfile == 'INT':
                fuspecs['rbc'] = [fuspecs.pop('rb')]
                fuspecs['rbc'].append(fuspecs.pop('rc'))
            if regfile == 'FAST':
                fuspecs['fast1'] = [fuspecs.pop('fast1')]
                fuspecs['fast1'].append(fuspecs.pop('fast2'))

            # for each named regfile port, connect up all FUs to that port
            for (regname, fspec) in sort_fuspecs(fuspecs):
                print("connect rd", regname, fspec)
                self.connect_rdport(m, fu_bitdict, rdpickers, regfile,
                                       regname, fspec)

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
                print("connect wr", regname, fspec)
                rpidx = regname
                # get the regfile specs for this regfile port
                (rf, read, write, wid, fuspec) = fspec

                # select the required write port.  these are pre-defined sizes
                print(regfile, regs.rf.keys())
                wport = regs.rf[regfile.lower()].w_ports[rpidx]

                # create a priority picker to manage this port
                wrpickers[regfile][rpidx] = wrpick = PriorityPicker(
                    len(fuspec))
                setattr(m.submodules, "wrpick_%s_%s" %
                        (regfile, rpidx), wrpick)

                # connect the regspec write "reg select" number to this port
                # only if one FU actually requests (and is granted) the port
                # will the write-enable be activated
                with m.If(wrpick.en_o):
                    comb += wport.wen.eq(write)
                with m.Else():
                    comb += wport.wen.eq(0)

                # connect up the FU req/go signals and the reg-read to the FU
                # these are arbitrated by Data.ok signals
                wsigs = []
                for pi, (funame, fu, idx) in enumerate(fuspec):
                    # write-request comes from dest.ok
                    dest = fu.get_out(idx)
                    fu_dest_latch = fu.get_fu_out(idx)  # latched output
                    name = "wrflag_%s_%s_%d" % (funame, regname, idx)
                    wrflag = Signal(name=name, reset_less=True)
                    comb += wrflag.eq(dest.ok & fu.busy_o)

                    # connect request-write to picker input, and output to go-wr
                    fu_active = fu_bitdict[funame]
                    pick = fu.wr.rel_o[idx] & fu_active  # & wrflag
                    comb += wrpick.i[pi].eq(pick)
                    # create a single-pulse go write from the picker output
                    wr_pick = Signal()
                    comb += wr_pick.eq(wrpick.o[pi] & wrpick.en_o)
                    comb += fu.go_wr_i[idx].eq(rising_edge(m, wr_pick))
                    # connect regfile port to input
                    print("reg connect widths",
                          regfile, regname, pi, funame,
                          dest.shape(), wport.data_i.shape())
                    wsigs.append(fu_dest_latch)

                # here is where we create the Write Broadcast Bus. simple, eh?
                comb += wport.data_i.eq(ortreereduce_sig(wsigs))

    def get_byregfiles(self, readmode):

        mode = "read" if readmode else "write"
        dec2 = self.pdecode2
        regs = self.regs
        fus = self.fus.fus

        # dictionary of lists of regfile ports
        byregfiles = {}
        byregfiles_spec = {}
        for (funame, fu) in fus.items():
            print("%s ports for %s" % (mode, funame))
            for idx in range(fu.n_src if readmode else fu.n_dst):
                if readmode:
                    (regfile, regname, wid) = fu.get_in_spec(idx)
                else:
                    (regfile, regname, wid) = fu.get_out_spec(idx)
                print("    %d %s %s %s" % (idx, regfile, regname, str(wid)))
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
                        (rdflag, read, write, wid, [])
                # here we start to create "lanes"
                if idx not in byregfiles[regfile]:
                    byregfiles[regfile][idx] = []
                fuspec = (funame, fu, idx)
                byregfiles[regfile][idx].append(fuspec)
                byregfiles_spec[regfile][regname][4].append(fuspec)

        # ok just print that out, for convenience
        for regfile, spec in byregfiles.items():
            print("regfile %s ports:" % mode, regfile)
            fuspecs = byregfiles_spec[regfile]
            for regname, fspec in fuspecs.items():
                [rdflag, read, write, wid, fuspec] = fspec
                print("  rf %s port %s lane: %s" % (mode, regfile, regname))
                print("  %s" % regname, wid, read, write, rdflag)
                for (funame, fu, idx) in fuspec:
                    fusig = fu.src_i[idx] if readmode else fu.dest[idx]
                    print("    ", funame, fu, idx, fusig)
                    print()

        return byregfiles, byregfiles_spec

    def __iter__(self):
        yield from self.fus.ports()
        yield from self.pdecode2.ports()
        yield from self.l0.ports()
        # TODO: regs

    def ports(self):
        return list(self)


if __name__ == '__main__':
    pspec = TestMemPspec(ldst_ifacetype='testpi',
                         imem_ifacetype='',
                         addr_wid=48,
                         mask_wid=8,
                         reg_wid=64)
    dut = NonProductionCore(pspec)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_core.il", "w") as f:
        f.write(vl)
