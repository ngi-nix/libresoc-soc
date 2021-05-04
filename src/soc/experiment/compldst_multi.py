"""LOAD / STORE Computation Unit.

This module covers POWER9-compliant Load and Store operations,
with selection on each between immediate and indexed mode as
options for the calculation of the Effective Address (EA),
and also "update" mode which optionally stores that EA into
an additional register.

----
Note: it took 15 attempts over several weeks to redraw the diagram
needed to capture this FSM properly.  To understand it fully, please
take the time to review the links, video, and diagram.
----

Stores are activated when Go_Store is enabled, and use a sync'd "ADD" to
compute the "Effective Address", and, when ready the operand (src3_i)
is stored in the computed address (passed through to the PortInterface)

Loads are activated when Go_Write[0] is enabled.  The EA is computed,
and (as long as there was no exception) the data comes out (at any
time from the PortInterface), and is captured by the LDCompSTUnit.

Both LD and ST may request that the address be computed from summing
operand1 (src[0]) with operand2 (src[1]) *or* by summing operand1 with
the immediate (from the opcode).

Both LD and ST may also request "update" mode (op_is_update) which
activates the use of Go_Write[1] to control storage of the EA into
a *second* operand in the register file.

Thus this module has *TWO* write-requests to the register file and
*THREE* read-requests to the register file (not all at the same time!)
The regfile port usage is:

    * LD-imm         1R1W
    * LD-imm-update  1R2W
    * LD-idx         2R1W
    * LD-idx-update  2R2W

    * ST-imm         2R
    * ST-imm-update  2R1W
    * ST-idx         3R
    * ST-idx-update  3R1W

It's a multi-level Finite State Machine that (unfortunately) nmigen.FSM
is not suited to (nmigen.FSM is clock-driven, and some aspects of
the nested FSMs below are *combinatorial*).

    * One FSM covers Operand collection and communication address-side
      with the LD/ST PortInterface.  its role ends when "RD_DONE" is asserted

    * A second FSM activates to cover LD.  it activates if op_is_ld is true

    * A third FSM activates to cover ST.  it activates if op_is_st is true

    * The "overall" (fourth) FSM coordinates the progression and completion
      of the three other FSMs, firing "WR_RESET" which switches off "busy"

Full diagram:

    https://libre-soc.org/3d_gpu/ld_st_comp_unit.jpg

Links including to walk-through videos:

    * https://libre-soc.org/3d_gpu/architecture/6600scoreboard/
    * http://libre-soc.org/openpower/isa/fixedload
    * http://libre-soc.org/openpower/isa/fixedstore

Related Bugreports:

    * https://bugs.libre-soc.org/show_bug.cgi?id=302
    * https://bugs.libre-soc.org/show_bug.cgi?id=216

Terminology:

    * EA - Effective Address
    * LD - Load
    * ST - Store
"""

from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Mux, Cat, Elaboratable, Array, Repl
from nmigen.hdl.rec import Record, Layout

from nmutil.latch import SRLatch, latchregister
from nmutil.byterev import byte_reverse
from nmutil.extend import exts

from soc.experiment.compalu_multi import go_record, CompUnitRecord
from soc.experiment.l0_cache import PortInterface
from soc.experiment.pimem import LDSTException
from soc.fu.regspec import RegSpecAPI

from openpower.decoder.power_enums import MicrOp, Function, LDSTMode
from soc.fu.ldst.ldst_input_record import CompLDSTOpSubset
from openpower.decoder.power_decoder2 import Data

# TODO: LDSTInputData and LDSTOutputData really should be used
# here, to make things more like the other CompUnits.  currently,
# also, RegSpecAPI is used explicitly here

class LDSTCompUnitRecord(CompUnitRecord):
    def __init__(self, rwid, opsubset=CompLDSTOpSubset, name=None):
        CompUnitRecord.__init__(self, opsubset, rwid,
                                n_src=3, n_dst=2, name=name)

        self.ad = go_record(1, name="cu_ad")  # address go in, req out
        self.st = go_record(1, name="cu_st")  # store go in, req out

        self.exc_o = LDSTException("exc_o")

        self.ld_o = Signal(reset_less=True)  # operation is a LD
        self.st_o = Signal(reset_less=True)  # operation is a ST

        # hmm... are these necessary?
        self.load_mem_o = Signal(reset_less=True)  # activate memory LOAD
        self.stwd_mem_o = Signal(reset_less=True)  # activate memory STORE


class LDSTCompUnit(RegSpecAPI, Elaboratable):
    """LOAD / STORE Computation Unit

    Inputs
    ------

    * :pi:     a PortInterface to the memory subsystem (read-write capable)
    * :rwid:   register width
    * :awid:   address width

    Data inputs
    -----------
    * :src_i:  Source Operands (RA/RB/RC) - managed by rd[0-3] go/req

    Data (outputs)
    --------------
    * :data_o:  Dest out (LD)          - managed by wr[0] go/req
    * :addr_o:  Address out (LD or ST) - managed by wr[1] go/req
    * :exc_o:   Address/Data Exception occurred.  LD/ST must terminate

    TODO: make exc_o a data-type rather than a single-bit signal
          (see bug #302)

    Control Signals (In)
    --------------------

    * :oper_i:     operation being carried out (POWER9 decode LD/ST subset)
    * :issue_i:    LD/ST is being "issued".
    * :shadown_i:  Inverted-shadow is being held (stops STORE *and* WRITE)
    * :go_rd_i:    read is being actioned (latches in src regs)
    * :go_wr_i:    write mode (exactly like ALU CompUnit)
    * :go_ad_i:    address is being actioned (triggers actual mem LD)
    * :go_st_i:    store is being actioned (triggers actual mem STORE)
    * :go_die_i:   resets the unit back to "wait for issue"

    Control Signals (Out)
    ---------------------

    * :busy_o:      function unit is busy
    * :rd_rel_o:    request src1/src2
    * :adr_rel_o:   request address (from mem)
    * :sto_rel_o:   request store (to mem)
    * :req_rel_o:   request write (result)
    * :load_mem_o:  activate memory LOAD
    * :stwd_mem_o:  activate memory STORE

    Note: load_mem_o, stwd_mem_o and req_rel_o MUST all be acknowledged
    in a single cycle and the CompUnit set back to doing another op.
    This means deasserting go_st_i, go_ad_i or go_wr_i as appropriate
    depending on whether the operation is a ST or LD.

    Note: LDSTCompUnit takes care of LE/BE normalisation:
    * LD data is normalised after receipt from the PortInterface
    * ST data is normalised *prior* to sending onto the PortInterface
    TODO: use one module for the byte-reverse as it's quite expensive in gates
    """

    def __init__(self, pi=None, rwid=64, awid=48, opsubset=CompLDSTOpSubset,
                 debugtest=False, name=None):
        super().__init__(rwid)
        self.awid = awid
        self.pi = pi
        self.cu = cu = LDSTCompUnitRecord(rwid, opsubset, name=name)
        self.debugtest = debugtest

        # POWER-compliant LD/ST has index and update: *fixed* number of ports
        self.n_src = n_src = 3   # RA, RB, RT/RS
        self.n_dst = n_dst = 2  # RA, RT/RS

        # set up array of src and dest signals
        for i in range(n_src):
            j = i + 1  # name numbering to match src1/src2
            name = "src%d_i" % j
            setattr(self, name, getattr(cu, name))

        dst = []
        for i in range(n_dst):
            j = i + 1  # name numbering to match dest1/2...
            name = "dest%d_o" % j
            setattr(self, name, getattr(cu, name))

        # convenience names
        self.rd = cu.rd
        self.wr = cu.wr
        self.rdmaskn = cu.rdmaskn
        self.wrmask = cu.wrmask
        self.ad = cu.ad
        self.st = cu.st
        self.dest = cu._dest

        # HACK: get data width from dest[0].  this is used across the board
        # (it really shouldn't be)
        self.data_wid = self.dest[0].shape()

        self.go_rd_i = self.rd.go_i  # temporary naming
        self.go_wr_i = self.wr.go_i  # temporary naming
        self.go_ad_i = self.ad.go_i  # temp naming: go address in
        self.go_st_i = self.st.go_i  # temp naming: go store in

        self.rd_rel_o = self.rd.rel_o  # temporary naming
        self.req_rel_o = self.wr.rel_o  # temporary naming
        self.adr_rel_o = self.ad.rel_o  # request address (from mem)
        self.sto_rel_o = self.st.rel_o  # request store (to mem)

        self.issue_i = cu.issue_i
        self.shadown_i = cu.shadown_i
        self.go_die_i = cu.go_die_i

        self.oper_i = cu.oper_i
        self.src_i = cu._src_i

        self.data_o = Data(self.data_wid, name="o")  # Dest1 out: RT
        self.addr_o = Data(self.data_wid, name="ea")  # Addr out: Update => RA
        self.exc_o = cu.exc_o
        self.done_o = cu.done_o
        self.busy_o = cu.busy_o

        self.ld_o = cu.ld_o
        self.st_o = cu.st_o

        self.load_mem_o = cu.load_mem_o
        self.stwd_mem_o = cu.stwd_mem_o

    def elaborate(self, platform):
        m = Module()

        # temp/convenience
        comb = m.d.comb
        sync = m.d.sync
        issue_i = self.issue_i

        #####################
        # latches for the FSM.
        m.submodules.opc_l = opc_l = SRLatch(sync=False, name="opc")
        m.submodules.src_l = src_l = SRLatch(False, self.n_src, name="src")
        m.submodules.alu_l = alu_l = SRLatch(sync=False, name="alu")
        m.submodules.adr_l = adr_l = SRLatch(sync=False, name="adr")
        m.submodules.lod_l = lod_l = SRLatch(sync=False, name="lod")
        m.submodules.sto_l = sto_l = SRLatch(sync=False, name="sto")
        m.submodules.wri_l = wri_l = SRLatch(sync=False, name="wri")
        m.submodules.upd_l = upd_l = SRLatch(sync=False, name="upd")
        m.submodules.rst_l = rst_l = SRLatch(sync=False, name="rst")
        m.submodules.lsd_l = lsd_l = SRLatch(sync=False, name="lsd") # done

        ####################
        # signals

        # opcode decode
        op_is_ld = Signal(reset_less=True)
        op_is_st = Signal(reset_less=True)

        # ALU/LD data output control
        alu_valid = Signal(reset_less=True)  # ALU operands are valid
        alu_ok = Signal(reset_less=True)    # ALU out ok (1 clock delay valid)
        addr_ok = Signal(reset_less=True)   # addr ok (from PortInterface)
        ld_ok = Signal(reset_less=True)     # LD out ok from PortInterface
        wr_any = Signal(reset_less=True)    # any write (incl. store)
        rda_any = Signal(reset_less=True)   # any read for address ops
        rd_done = Signal(reset_less=True)   # all *necessary* operands read
        wr_reset = Signal(reset_less=True)  # final reset condition

        # LD and ALU out
        alu_o = Signal(self.data_wid, reset_less=True)
        ldd_o = Signal(self.data_wid, reset_less=True)

        ##############################
        # reset conditions for latches

        # temporaries (also convenient when debugging)
        reset_o = Signal(reset_less=True)             # reset opcode
        reset_w = Signal(reset_less=True)             # reset write
        reset_u = Signal(reset_less=True)             # reset update
        reset_a = Signal(reset_less=True)             # reset adr latch
        reset_i = Signal(reset_less=True)             # issue|die (use a lot)
        reset_r = Signal(self.n_src, reset_less=True)  # reset src
        reset_s = Signal(reset_less=True)             # reset store

        comb += reset_i.eq(issue_i | self.go_die_i)       # various
        comb += reset_o.eq(self.done_o | self.go_die_i)      # opcode reset
        comb += reset_w.eq(self.wr.go_i[0] | self.go_die_i)  # write reg 1
        comb += reset_u.eq(self.wr.go_i[1] | self.go_die_i)  # update (reg 2)
        comb += reset_s.eq(self.go_st_i | self.go_die_i)  # store reset
        comb += reset_r.eq(self.rd.go_i | Repl(self.go_die_i, self.n_src))
        comb += reset_a.eq(self.go_ad_i | self.go_die_i)

        p_st_go = Signal(reset_less=True)
        sync += p_st_go.eq(self.st.go_i)

        # decode bits of operand (latched)
        oper_r = CompLDSTOpSubset(name="oper_r")  # Dest register
        comb += op_is_st.eq(oper_r.insn_type == MicrOp.OP_STORE)  # ST
        comb += op_is_ld.eq(oper_r.insn_type == MicrOp.OP_LOAD)  # LD
        op_is_update = oper_r.ldst_mode == LDSTMode.update           # UPDATE
        op_is_cix = oper_r.ldst_mode == LDSTMode.cix           # cache-inhibit
        comb += self.load_mem_o.eq(op_is_ld & self.go_ad_i)
        comb += self.stwd_mem_o.eq(op_is_st & self.go_st_i)
        comb += self.ld_o.eq(op_is_ld)
        comb += self.st_o.eq(op_is_st)

        ##########################
        # FSM implemented through sequence of latches.  approximately this:
        # - opc_l       : opcode
        #    - src_l[0] : operands
        #    - src_l[1]
        #       - alu_l : looks after add of src1/2/imm (EA)
        #       - adr_l : waits for add (EA)
        #       - upd_l : waits for adr and Regfile (port 2)
        #    - src_l[2] : ST
        # - lod_l       : waits for adr (EA) and for LD Data
        # - wri_l       : waits for LD Data and Regfile (port 1)
        # - st_l        : waits for alu and operand2
        # - rst_l       : waits for all FSM paths to converge.
        # NOTE: use sync to stop combinatorial loops.

        # opcode latch - inverted so that busy resets to 0
        # note this MUST be sync so as to avoid a combinatorial loop
        # between busy_o and issue_i on the reset latch (rst_l)
        sync += opc_l.s.eq(issue_i)  # XXX NOTE: INVERTED FROM book!
        sync += opc_l.r.eq(reset_o)  # XXX NOTE: INVERTED FROM book!

        # src operand latch
        sync += src_l.s.eq(Repl(issue_i, self.n_src))
        sync += src_l.r.eq(reset_r)

        # alu latch.  use sync-delay between alu_ok and valid to generate pulse
        comb += alu_l.s.eq(reset_i)
        comb += alu_l.r.eq(alu_ok & ~alu_valid & ~rda_any)

        # addr latch
        comb += adr_l.s.eq(reset_i)
        sync += adr_l.r.eq(reset_a)

        # ld latch
        comb += lod_l.s.eq(reset_i)
        comb += lod_l.r.eq(ld_ok)

        # dest operand latch
        comb += wri_l.s.eq(issue_i)
        sync += wri_l.r.eq(reset_w | Repl(wr_reset |
                                          (~self.pi.busy_o & op_is_update),
                                          #(self.pi.busy_o & op_is_update),
                            #self.done_o | (self.pi.busy_o & op_is_update),
                                          self.n_dst))

        # update-mode operand latch (EA written to reg 2)
        sync += upd_l.s.eq(reset_i)
        sync += upd_l.r.eq(reset_u)

        # store latch
        comb += sto_l.s.eq(addr_ok & op_is_st)
        sync += sto_l.r.eq(reset_s | p_st_go)

        # ld/st done.  needed to stop LD/ST from activating repeatedly
        comb += lsd_l.s.eq(issue_i)
        sync += lsd_l.r.eq(reset_s | p_st_go | ld_ok)

        # reset latch
        comb += rst_l.s.eq(addr_ok)  # start when address is ready
        comb += rst_l.r.eq(issue_i)

        # create a latch/register for the operand
        with m.If(self.issue_i):
            sync += oper_r.eq(self.oper_i)
        with m.If(self.done_o):
            sync += oper_r.eq(0)

        # and for LD
        ldd_r = Signal(self.data_wid, reset_less=True)  # Dest register
        latchregister(m, ldd_o, ldd_r, ld_ok, name="ldo_r")

        # and for each input from the incoming src operands
        srl = []
        for i in range(self.n_src):
            name = "src_r%d" % i
            src_r = Signal(self.data_wid, name=name, reset_less=True)
            with m.If(self.rd.go_i[i]):
                sync += src_r.eq(self.src_i[i])
            with m.If(self.issue_i):
                sync += src_r.eq(0)
            srl.append(src_r)

        # and one for the output from the ADD (for the EA)
        addr_r = Signal(self.data_wid, reset_less=True)  # Effective Address
        latchregister(m, alu_o, addr_r, alu_l.q, "ea_r")

        # select either zero or src1 if opcode says so
        op_is_z = oper_r.zero_a
        src1_or_z = Signal(self.data_wid, reset_less=True)
        m.d.comb += src1_or_z.eq(Mux(op_is_z, 0, srl[0]))

        # select either immediate or src2 if opcode says so
        op_is_imm = oper_r.imm_data.ok
        src2_or_imm = Signal(self.data_wid, reset_less=True)
        m.d.comb += src2_or_imm.eq(Mux(op_is_imm, oper_r.imm_data.data, srl[1]))

        # now do the ALU addr add: one cycle, and say "ready" (next cycle, too)
        comb += alu_o.eq(src1_or_z + src2_or_imm)  # actual EA
        m.d.sync += alu_ok.eq(alu_valid)             # keep ack in sync with EA

        ############################
        # Control Signal calculation

        # busy signal
        busy_o = self.busy_o
        comb += self.busy_o.eq(opc_l.q)  # | self.pi.busy_o)  # busy out

        # 1st operand read-request only when zero not active
        # 2nd operand only needed when immediate is not active
        slg = Cat(op_is_z, op_is_imm)
        bro = Repl(self.busy_o, self.n_src)
        comb += self.rd.rel_o.eq(src_l.q & bro & ~slg & ~self.rdmaskn)

        # note when the address-related read "go" signals are active
        comb += rda_any.eq(self.rd.go_i[0] | self.rd.go_i[1])

        # alu input valid when 1st and 2nd ops done (or imm not active)
        comb += alu_valid.eq(busy_o & ~(self.rd.rel_o[0] | self.rd.rel_o[1]))

        # 3rd operand only needed when operation is a store
        comb += self.rd.rel_o[2].eq(src_l.q[2] & busy_o & op_is_st)

        # all reads done when alu is valid and 3rd operand needed
        comb += rd_done.eq(alu_valid & ~self.rd.rel_o[2])

        # address release only if addr ready, but Port must be idle
        comb += self.adr_rel_o.eq(alu_valid & adr_l.q & busy_o)

        # the write/store (etc) all must be cancelled if an exception occurs
        cancel = Signal(reset_less=True)
        comb += cancel.eq(self.exc_o.happened | self.shadown_i)

        # store release when st ready *and* all operands read (and no shadow)
        comb += self.st.rel_o.eq(sto_l.q & busy_o & rd_done & op_is_st &
                               cancel)

        # request write of LD result.  waits until shadow is dropped.
        comb += self.wr.rel_o[0].eq(rd_done & wri_l.q & busy_o & lod_l.qn &
                                  op_is_ld & cancel)

        # request write of EA result only in update mode
        comb += self.wr.rel_o[1].eq(upd_l.q & busy_o & op_is_update &
                                  alu_valid & cancel)

        # provide "done" signal: select req_rel for non-LD/ST, adr_rel for LD/ST
        comb += wr_any.eq(self.st.go_i | p_st_go |
                          self.wr.go_i[0] | self.wr.go_i[1])
        comb += wr_reset.eq(rst_l.q & busy_o & cancel &
                            ~(self.st.rel_o | self.wr.rel_o[0] |
                              self.wr.rel_o[1]) &
                            (lod_l.qn | op_is_st)
                            )
        comb += self.done_o.eq(wr_reset & (~self.pi.busy_o | op_is_ld))

        ######################
        # Data/Address outputs

        # put the LD-output register directly onto the output bus on a go_write
        comb += self.data_o.data.eq(self.dest[0])
        with m.If(self.wr.go_i[0]):
            comb += self.dest[0].eq(ldd_r)

        # "update" mode, put address out on 2nd go-write
        comb += self.addr_o.data.eq(self.dest[1])
        with m.If(op_is_update & self.wr.go_i[1]):
            comb += self.dest[1].eq(addr_r)

        # need to look like MultiCompUnit: put wrmask out.
        # XXX may need to make this enable only when write active
        comb += self.wrmask.eq(bro & Cat(op_is_ld, op_is_update))

        ###########################
        # PortInterface connections
        pi = self.pi

        # connect to LD/ST PortInterface.
        comb += pi.is_ld_i.eq(op_is_ld & busy_o)  # decoded-LD
        comb += pi.is_st_i.eq(op_is_st & busy_o)  # decoded-ST
        comb += pi.data_len.eq(oper_r.data_len)  # data_len
        # address: use sync to avoid long latency
        sync += pi.addr.data.eq(addr_r)           # EA from adder
        sync += pi.addr.ok.eq(alu_ok & lsd_l.q)  # "do address stuff" (once)
        comb += self.exc_o.eq(pi.exc_o)  # exception occurred
        comb += addr_ok.eq(self.pi.addr_ok_o)  # no exc, address fine

        # byte-reverse on LD
        revnorev = Signal(64, reset_less=True)
        with m.If(oper_r.byte_reverse):
            # byte-reverse the data based on ld/st width (turn it to LE)
            data_len = oper_r.data_len
            lddata_r = byte_reverse(m, 'lddata_r', pi.ld.data, data_len)
            comb += revnorev.eq(lddata_r)  # put reversed- data out
        with m.Else():
            comb += revnorev.eq(pi.ld.data)  # put data out, straight (as BE)

        # then check sign-extend
        with m.If(oper_r.sign_extend):
            # okok really should "if data_len == 4" and so on here
            with m.If(oper_r.data_len == 2):
                comb += ldd_o.eq(exts(revnorev, 16, 64))  # sign-extend hword
            with m.Else():
                comb += ldd_o.eq(exts(revnorev, 32, 64))  # sign-extend dword
        with m.Else():
            comb += ldd_o.eq(revnorev)

        # ld - ld gets latched in via lod_l
        comb += ld_ok.eq(pi.ld.ok)  # ld.ok *closes* (freezes) ld data

        # byte-reverse on ST
        op3 = srl[2] # 3rd operand latch
        with m.If(oper_r.byte_reverse):
            # byte-reverse the data based on width
            data_len = oper_r.data_len
            stdata_r = byte_reverse(m, 'stdata_r', op3, data_len)
            comb += pi.st.data.eq(stdata_r)
        with m.Else():
            comb += pi.st.data.eq(op3)
        # store - data goes in based on go_st
        comb += pi.st.ok.eq(self.st.go_i)  # go store signals st data valid

        return m

    def get_out(self, i):
        """make LDSTCompUnit look like RegSpecALUAPI.  these correspond
        to LDSTOutputData o and o1 respectively.
        """
        if i == 0:
            return self.data_o # LDSTOutputData.regspec o
        if i == 1:
            return self.addr_o # LDSTOutputData.regspec o1
        # return self.dest[i]

    def get_fu_out(self, i):
        return self.get_out(i)

    def __iter__(self):
        yield self.rd.go_i
        yield self.go_ad_i
        yield self.wr.go_i
        yield self.go_st_i
        yield self.issue_i
        yield self.shadown_i
        yield self.go_die_i
        yield from self.oper_i.ports()
        yield from self.src_i
        yield self.busy_o
        yield self.rd.rel_o
        yield self.adr_rel_o
        yield self.sto_rel_o
        yield self.wr.rel_o
        yield from self.data_o.ports()
        yield from self.addr_o.ports()
        yield self.load_mem_o
        yield self.stwd_mem_o

    def ports(self):
        return list(self)


def wait_for(sig, wait=True, test1st=False):
    v = (yield sig)
    print("wait for", sig, v, wait, test1st)
    if test1st and bool(v) == wait:
        return
    while True:
        yield
        v = (yield sig)
        #print("...wait for", sig, v)
        if bool(v) == wait:
            break


def store(dut, src1, src2, src3, imm, imm_ok=True, update=False,
          byterev=True):
    print("ST", src1, src2, src3, imm, imm_ok, update)
    yield dut.oper_i.insn_type.eq(MicrOp.OP_STORE)
    yield dut.oper_i.data_len.eq(2)  # half-word
    yield dut.oper_i.byte_reverse.eq(byterev)
    yield dut.src1_i.eq(src1)
    yield dut.src2_i.eq(src2)
    yield dut.src3_i.eq(src3)
    yield dut.oper_i.imm_data.imm.eq(imm)
    yield dut.oper_i.imm_data.ok.eq(imm_ok)
    yield dut.oper_i.update.eq(update)
    yield dut.issue_i.eq(1)
    yield
    yield dut.issue_i.eq(0)

    if imm_ok:
        active_rel = 0b101
    else:
        active_rel = 0b111
    # wait for all active rel signals to come up
    while True:
        rel = yield dut.rd.rel_o
        if rel == active_rel:
            break
        yield
    yield dut.rd.go.eq(active_rel)
    yield
    yield dut.rd.go.eq(0)

    yield from wait_for(dut.adr_rel_o, False, test1st=True)
    # yield from wait_for(dut.adr_rel_o)
    # yield dut.ad.go.eq(1)
    # yield
    # yield dut.ad.go.eq(0)

    if update:
        yield from wait_for(dut.wr.rel_o[1])
        yield dut.wr.go.eq(0b10)
        yield
        addr = yield dut.addr_o
        print("addr", addr)
        yield dut.wr.go.eq(0)
    else:
        addr = None

    yield from wait_for(dut.sto_rel_o)
    yield dut.go_st_i.eq(1)
    yield
    yield dut.go_st_i.eq(0)
    yield from wait_for(dut.busy_o, False)
    # wait_for(dut.stwd_mem_o)
    yield
    return addr


def load(dut, src1, src2, imm, imm_ok=True, update=False, zero_a=False,
         byterev=True):
    print("LD", src1, src2, imm, imm_ok, update)
    yield dut.oper_i.insn_type.eq(MicrOp.OP_LOAD)
    yield dut.oper_i.data_len.eq(2)  # half-word
    yield dut.oper_i.byte_reverse.eq(byterev)
    yield dut.src1_i.eq(src1)
    yield dut.src2_i.eq(src2)
    yield dut.oper_i.zero_a.eq(zero_a)
    yield dut.oper_i.imm_data.imm.eq(imm)
    yield dut.oper_i.imm_data.ok.eq(imm_ok)
    yield dut.issue_i.eq(1)
    yield
    yield dut.issue_i.eq(0)
    yield

    # set up read-operand flags
    rd = 0b00
    if not imm_ok:  # no immediate means RB register needs to be read
        rd |= 0b10
    if not zero_a:  # no zero-a means RA needs to be read
        rd |= 0b01

    # wait for the operands (RA, RB, or both)
    if rd:
        yield dut.rd.go.eq(rd)
        yield from wait_for(dut.rd.rel_o)
        yield dut.rd.go.eq(0)

    yield from wait_for(dut.adr_rel_o, False, test1st=True)
    # yield dut.ad.go.eq(1)
    # yield
    # yield dut.ad.go.eq(0)

    if update:
        yield from wait_for(dut.wr.rel_o[1])
        yield dut.wr.go.eq(0b10)
        yield
        addr = yield dut.addr_o
        print("addr", addr)
        yield dut.wr.go.eq(0)
    else:
        addr = None

    yield from wait_for(dut.wr.rel_o[0], test1st=True)
    yield dut.wr.go.eq(1)
    yield
    data = yield dut.data_o
    print(data)
    yield dut.wr.go.eq(0)
    yield from wait_for(dut.busy_o)
    yield
    # wait_for(dut.stwd_mem_o)
    return data, addr


def ldst_sim(dut):

    ###################
    # immediate version

    # two STs (different addresses)
    yield from store(dut, 4, 0, 3, 2)  # ST reg4 into addr rfile[reg3]+2
    yield from store(dut, 2, 0, 9, 2)  # ST reg4 into addr rfile[reg9]+2
    yield
    # two LDs (deliberately LD from the 1st address then 2nd)
    data, addr = yield from load(dut, 4, 0, 2)
    assert data == 0x0003, "returned %x" % data
    data, addr = yield from load(dut, 2, 0, 2)
    assert data == 0x0009, "returned %x" % data
    yield

    # indexed version
    yield from store(dut, 9, 5, 3, 0, imm_ok=False)
    data, addr = yield from load(dut, 9, 5, 0, imm_ok=False)
    assert data == 0x0003, "returned %x" % data

    # update-immediate version
    addr = yield from store(dut, 9, 6, 3, 2, update=True)
    assert addr == 0x000b, "returned %x" % addr

    # update-indexed version
    data, addr = yield from load(dut, 9, 5, 0, imm_ok=False, update=True)
    assert data == 0x0003, "returned %x" % data
    assert addr == 0x000e, "returned %x" % addr

    # immediate *and* zero version
    data, addr = yield from load(dut, 1, 4, 8, imm_ok=True, zero_a=True)
    assert data == 0x0008, "returned %x" % data


class TestLDSTCompUnit(LDSTCompUnit):

    def __init__(self, rwid):
        from soc.experiment.l0_cache import TstL0CacheBuffer
        self.l0 = l0 = TstL0CacheBuffer()
        pi = l0.l0.dports[0].pi
        LDSTCompUnit.__init__(self, pi, rwid, 4)

    def elaborate(self, platform):
        m = LDSTCompUnit.elaborate(self, platform)
        m.submodules.l0 = self.l0
        m.d.comb += self.ad.go.eq(self.ad.rel)  # link addr-go direct to rel
        return m


def test_scoreboard():

    dut = TestLDSTCompUnit(16)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_ldst_comp.il", "w") as f:
        f.write(vl)

    run_simulation(dut, ldst_sim(dut), vcd_name='test_ldst_comp.vcd')


class TestLDSTCompUnitRegSpec(LDSTCompUnit):

    def __init__(self):
        from soc.experiment.l0_cache import TstL0CacheBuffer
        from soc.fu.ldst.pipe_data import LDSTPipeSpec
        regspec = LDSTPipeSpec.regspec
        self.l0 = l0 = TstL0CacheBuffer()
        pi = l0.l0.dports[0].pi
        LDSTCompUnit.__init__(self, pi, regspec, 4)

    def elaborate(self, platform):
        m = LDSTCompUnit.elaborate(self, platform)
        m.submodules.l0 = self.l0
        m.d.comb += self.ad.go.eq(self.ad.rel)  # link addr-go direct to rel
        return m


def test_scoreboard_regspec():

    dut = TestLDSTCompUnitRegSpec()
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_ldst_comp.il", "w") as f:
        f.write(vl)

    run_simulation(dut, ldst_sim(dut), vcd_name='test_ldst_regspec.vcd')


if __name__ == '__main__':
    test_scoreboard_regspec()
    test_scoreboard()
