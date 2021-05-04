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

from nmigen import Elaboratable, Module, Signal, ResetSignal, Cat, Mux
from nmigen.cli import rtlil

from openpower.decoder.power_decoder2 import PowerDecodeSubset
from openpower.decoder.power_regspec_map import regspec_decode_read
from openpower.decoder.power_regspec_map import regspec_decode_write

from nmutil.picker import PriorityPicker
from nmutil.util import treereduce

from soc.fu.compunits.compunits import AllFunctionUnits
from soc.regfile.regfiles import RegFiles
from openpower.decoder.decode2execute1 import Decode2ToExecute1Type
from openpower.decoder.decode2execute1 import IssuerDecode2ToOperand
from openpower.decoder.power_decoder2 import get_rdflags
from openpower.decoder.decode2execute1 import Data
from soc.experiment.l0_cache import TstL0CacheBuffer  # test only
from soc.config.test.test_loadstore import TestMemPspec
from openpower.decoder.power_enums import MicrOp
from soc.config.state import CoreState

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
        self.pspec = pspec

        # test is SVP64 is to be enabled
        self.svp64_en = hasattr(pspec, "svp64") and (pspec.svp64 == True)

        # test to see if regfile ports should be reduced
        self.regreduce_en = (hasattr(pspec, "regreduce") and
                             (pspec.regreduce == True))

        # single LD/ST funnel for memory access
        self.l0 = l0 = TstL0CacheBuffer(pspec, n_units=1)
        pi = l0.l0.dports[0]

        # function units (only one each)
        # only include mmu if enabled in pspec
        self.fus = AllFunctionUnits(pspec, pilist=[pi])

        # link LoadStore1 into MMU
        mmu = self.fus.get_fu('mmu0')
        print ("core pspec", pspec.ldst_ifacetype)
        print ("core mmu", mmu)
        print ("core lsmem.lsi", l0.cmpi.lsmem.lsi)
        if mmu is not None:
            mmu.alu.set_ldst_interface(l0.cmpi.lsmem.lsi)

        # register files (yes plural)
        self.regs = RegFiles(pspec)

        # instruction decoder - needs a Trap-capable Record (captures EINT etc.)
        self.e = Decode2ToExecute1Type("core", opkls=IssuerDecode2ToOperand,
                                regreduce_en=self.regreduce_en)

        # SVP64 RA_OR_ZERO needs to know if the relevant EXTRA2/3 field is zero
        self.sv_a_nz = Signal()

        # state and raw instruction
        self.state = CoreState("core")
        self.raw_insn_i = Signal(32) # raw instruction
        self.bigendian_i = Signal() # bigendian - TODO, set by MSR.BE

        # issue/valid/busy signalling
        self.ivalid_i = Signal(reset_less=True) # instruction is valid
        self.issue_i = Signal(reset_less=True)
        self.busy_o = Signal(name="corebusy_o", reset_less=True)

        # start/stop and terminated signalling
        self.core_terminate_o = Signal(reset=0)  # indicates stopped

        # create per-FU instruction decoders (subsetted)
        self.decoders = {}
        self.des = {}

        for funame, fu in self.fus.fus.items():
            f_name = fu.fnunit.name
            fnunit = fu.fnunit.value
            opkls = fu.opsubsetkls
            if f_name == 'TRAP':
                self.trapunit = funame
                continue
            self.decoders[funame] = PowerDecodeSubset(None, opkls, f_name,
                                                      final=True,
                                                      state=self.state,
                                            svp64_en=self.svp64_en,
                                            regreduce_en=self.regreduce_en)
            self.des[funame] = self.decoders[funame].do

        if "mmu0" in self.decoders:
            self.decoders["mmu0"].mmu0_spr_dec = self.decoders["spr0"]

    def elaborate(self, platform):
        m = Module()
        # for testing purposes, to cut down on build time in coriolis2
        if hasattr(self.pspec, "nocore") and self.pspec.nocore == True:
            x = Signal() # dummy signal
            m.d.sync += x.eq(~x)
            return m
        comb = m.d.comb

        m.submodules.fus = self.fus
        m.submodules.l0 = l0 = self.l0
        self.regs.elaborate_into(m, platform)
        regs = self.regs
        fus = self.fus.fus

        # connect decoders
        for k, v in self.decoders.items():
            setattr(m.submodules, "dec_%s" % v.fn_name, v)
            comb += v.dec.raw_opcode_in.eq(self.raw_insn_i)
            comb += v.dec.bigendian.eq(self.bigendian_i)
            # sigh due to SVP64 RA_OR_ZERO detection connect these too
            comb += v.sv_a_nz.eq(self.sv_a_nz)

        # ssh, cheat: trap uses the main decoder because of the rewriting
        self.des[self.trapunit] = self.e.do

        # connect up Function Units, then read/write ports
        fu_bitdict = self.connect_instruction(m)
        self.connect_rdports(m, fu_bitdict)
        self.connect_wrports(m, fu_bitdict)

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
            comb += enable.eq((self.e.do.fn_unit & fnunit).bool())
            comb += fu_bitdict[funame].eq(enable)

        # sigh - need a NOP counter
        counter = Signal(2)
        with m.If(counter != 0):
            sync += counter.eq(counter - 1)
            comb += self.busy_o.eq(1)

        with m.If(self.ivalid_i): # run only when valid
            with m.Switch(self.e.do.insn_type):
                # check for ATTN: halt if true
                with m.Case(MicrOp.OP_ATTN):
                    m.d.sync += self.core_terminate_o.eq(1)

                with m.Case(MicrOp.OP_NOP):
                    sync += counter.eq(2)
                    comb += self.busy_o.eq(1)

                with m.Default():
                    # connect up instructions.  only one enabled at a time
                    for funame, fu in fus.items():
                        do = self.des[funame]
                        enable = fu_bitdict[funame]

                        # run this FunctionUnit if enabled
                        # route op, issue, busy, read flags and mask to FU
                        with m.If(enable):
                            # operand comes from the *local*  decoder
                            comb += fu.oper_i.eq_from(do)
                            #comb += fu.oper_i.eq_from_execute1(e)
                            comb += fu.issue_i.eq(self.issue_i)
                            comb += self.busy_o.eq(fu.busy_o)
                            # rdmask, which is for registers, needs to come
                            # from the *main* decoder
                            rdmask = get_rdflags(self.e, fu)
                            comb += fu.rdmaskn.eq(~rdmask)

        return fu_bitdict

    def connect_rdport(self, m, fu_bitdict, rdpickers, regfile, regname, fspec):
        comb, sync = m.d.comb, m.d.sync
        fus = self.fus.fus
        regs = self.regs

        rpidx = regname

        # select the required read port.  these are pre-defined sizes
        rfile = regs.rf[regfile.lower()]
        rport = rfile.r_ports[rpidx]
        print("read regfile", rpidx, regfile, regs.rf.keys(),
                              rfile, rfile.unary)

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

        rens = []
        addrs = []
        for i, fspec in enumerate(fspecs):
            (rf, read, write, wid, fuspec) = fspec
            # connect up the FU req/go signals, and the reg-read to the FU
            # and create a Read Broadcast Bus
            for pi, (funame, fu, idx) in enumerate(fuspec):
                pi += ppoffs[i]

                # connect request-read to picker input, and output to go-rd
                fu_active = fu_bitdict[funame]
                name = "%s_%s_%s_%i" % (regfile, rpidx, funame, pi)
                addr_en = Signal.like(reads[i], name="addr_en_"+name)
                pick = Signal(name="pick_"+name)     # picker input
                rp = Signal(name="rp_"+name)         # picker output
                delay_pick = Signal(name="dp_"+name) # read-enable "underway"

                # exclude any currently-enabled read-request (mask out active)
                comb += pick.eq(fu.rd_rel_o[idx] & fu_active & rdflags[i] &
                                ~delay_pick)
                comb += rdpick.i[pi].eq(pick)
                comb += fu.go_rd_i[idx].eq(delay_pick) # pass in *delayed* pick

                # if picked, select read-port "reg select" number to port
                comb += rp.eq(rdpick.o[pi] & rdpick.en_o)
                sync += delay_pick.eq(rp) # delayed "pick"
                comb += addr_en.eq(Mux(rp, reads[i], 0))

                # the read-enable happens combinatorially (see mux-bus below)
                # but it results in the data coming out on a one-cycle delay.
                if rfile.unary:
                    rens.append(addr_en)
                else:
                    addrs.append(addr_en)
                    rens.append(rp)

                # use the *delayed* pick signal to put requested data onto bus
                with m.If(delay_pick):
                    # connect regfile port to input, creating fan-out Bus
                    src = fu.src_i[idx]
                    print("reg connect widths",
                          regfile, regname, pi, funame,
                          src.shape(), rport.data_o.shape())
                    # all FUs connect to same port
                    comb += src.eq(rport.data_o)

        # or-reduce the muxed read signals
        if rfile.unary:
            # for unary-addressed
            comb += rport.ren.eq(ortreereduce_sig(rens))
        else:
            # for binary-addressed
            comb += rport.addr.eq(ortreereduce_sig(addrs))
            comb += rport.ren.eq(Cat(*rens).bool())
            print ("binary", regfile, rpidx, rport, rport.ren, rens, addrs)

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
            if self.regreduce_en:
                if regfile == 'INT':
                    fuspecs['rabc'] = [fuspecs.pop('rb')]
                    fuspecs['rabc'].append(fuspecs.pop('rc'))
                    fuspecs['rabc'].append(fuspecs.pop('ra'))
                if regfile == 'FAST':
                    fuspecs['fast1'] = [fuspecs.pop('fast1')]
                    if 'fast2' in fuspecs:
                        fuspecs['fast1'].append(fuspecs.pop('fast2'))
                    if 'fast3' in fuspecs:
                        fuspecs['fast1'].append(fuspecs.pop('fast3'))

            # for each named regfile port, connect up all FUs to that port
            for (regname, fspec) in sort_fuspecs(fuspecs):
                print("connect rd", regname, fspec)
                self.connect_rdport(m, fu_bitdict, rdpickers, regfile,
                                       regname, fspec)

    def connect_wrport(self, m, fu_bitdict, wrpickers, regfile, regname, fspec):
        comb, sync = m.d.comb, m.d.sync
        fus = self.fus.fus
        regs = self.regs

        print("connect wr", regname, fspec)
        rpidx = regname

        # select the required write port.  these are pre-defined sizes
        print(regfile, regs.rf.keys())
        rfile = regs.rf[regfile.lower()]
        wport = rfile.w_ports[rpidx]

        fspecs = fspec
        if not isinstance(fspecs, list):
            fspecs = [fspecs]

        pplen = 0
        writes = []
        ppoffs = []
        for i, fspec in enumerate(fspecs):
            # get the regfile specs for this regfile port
            (rf, read, write, wid, fuspec) = fspec
            print ("fpsec", i, fspec, len(fuspec))
            ppoffs.append(pplen) # record offset for picker
            pplen += len(fuspec)

        # create a priority picker to manage this port
        wrpickers[regfile][rpidx] = wrpick = PriorityPicker(pplen)
        setattr(m.submodules, "wrpick_%s_%s" % (regfile, rpidx), wrpick)

        wsigs = []
        wens = []
        addrs = []
        for i, fspec in enumerate(fspecs):
            # connect up the FU req/go signals and the reg-read to the FU
            # these are arbitrated by Data.ok signals
            (rf, read, write, wid, fuspec) = fspec
            for pi, (funame, fu, idx) in enumerate(fuspec):
                pi += ppoffs[i]

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

                # connect the regspec write "reg select" number to this port
                # only if one FU actually requests (and is granted) the port
                # will the write-enable be activated
                addr_en = Signal.like(write)
                wp = Signal()
                comb += wp.eq(wr_pick & wrpick.en_o)
                comb += addr_en.eq(Mux(wp, write, 0))
                if rfile.unary:
                    wens.append(addr_en)
                else:
                    addrs.append(addr_en)
                    wens.append(wp)

                # connect regfile port to input
                print("reg connect widths",
                      regfile, regname, pi, funame,
                      dest.shape(), wport.data_i.shape())
                wsigs.append(fu_dest_latch)

        # here is where we create the Write Broadcast Bus. simple, eh?
        comb += wport.data_i.eq(ortreereduce_sig(wsigs))
        if rfile.unary:
            # for unary-addressed
            comb += wport.wen.eq(ortreereduce_sig(wens))
        else:
            # for binary-addressed
            comb += wport.addr.eq(ortreereduce_sig(addrs))
            comb += wport.wen.eq(ortreereduce_sig(wens))

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

            if self.regreduce_en:
                # argh, more port-merging
                if regfile == 'INT':
                    fuspecs['o'] = [fuspecs.pop('o')]
                    fuspecs['o'].append(fuspecs.pop('o1'))
                if regfile == 'FAST':
                    fuspecs['fast1'] = [fuspecs.pop('fast1')]
                    if 'fast2' in fuspecs:
                        fuspecs['fast1'].append(fuspecs.pop('fast2'))
                    if 'fast3' in fuspecs:
                        fuspecs['fast1'].append(fuspecs.pop('fast3'))

            for (regname, fspec) in sort_fuspecs(fuspecs):
                self.connect_wrport(m, fu_bitdict, wrpickers,
                                        regfile, regname, fspec)

    def get_byregfiles(self, readmode):

        mode = "read" if readmode else "write"
        regs = self.regs
        fus = self.fus.fus
        e = self.e # decoded instruction to execute

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
                    rdflag, read = regspec_decode_read(e, regfile, regname)
                    write = None
                else:
                    rdflag, read = None, None
                    wrport, write = regspec_decode_write(e, regfile, regname)
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
        yield from self.e.ports()
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
