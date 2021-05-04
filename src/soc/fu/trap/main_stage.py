"""Trap Pipeline

Deals with td/tw/tdi/twi as well as mfmsr/mtmsr, sc and rfid. addpcis TODO.
Also used generally for interrupts (as a micro-coding mechanism) by
actually modifying the decoded instruction in PowerDecode2.

* https://bugs.libre-soc.org/show_bug.cgi?id=325
* https://bugs.libre-soc.org/show_bug.cgi?id=344
* https://libre-soc.org/openpower/isa/fixedtrap/
"""

from nmigen import (Module, Signal, Cat, Mux, Const, signed)
from nmutil.pipemodbase import PipeModBase
from nmutil.extend import exts
from soc.fu.trap.pipe_data import TrapInputData, TrapOutputData
from soc.fu.branch.main_stage import br_ext
from openpower.decoder.power_enums import MicrOp
from soc.experiment.mem_types import LDSTException

from openpower.decoder.power_fields import DecodeFields
from openpower.decoder.power_fieldsn import SignalBitRange

from openpower.consts import MSR, PI, TT, field, field_slice


def msr_copy(msr_o, msr_i, zero_me=True):
    """msr_copy
    ISA says this:
    Defined MSR bits are classified as either full func tion or partial
    function. Full function MSR bits are saved in SRR1 or HSRR1 when
    an interrupt other than a System Call Vectored interrupt occurs and
    restored by rfscv, rfid, or hrfid, while partial function MSR bits
    are not saved or restored.  Full function MSR bits lie in the range
    0:32, 37:41, and 48:63, and partial function MSR bits lie in the
    range 33:36 and 42:47. (Note this is IBM bit numbering).
    """
    l = []
    if zero_me:
        l.append(msr_o.eq(0))
    for stt, end in [(0,16), (22, 27), (31, 64)]:
        l.append(msr_o[stt:end].eq(msr_i[stt:end]))
    return l


def msr_check_pr(m, msr):
    """msr_check_pr: checks "problem state"
    """
    comb = m.d.comb
    with m.If(msr[MSR.PR]):
        comb += msr[MSR.EE].eq(1) # set external interrupt bit
        comb += msr[MSR.IR].eq(1) # set instruction relocation bit
        comb += msr[MSR.DR].eq(1) # set data relocation bit


class TrapMainStage(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "main")
        self.fields = DecodeFields(SignalBitRange, [self.i.ctx.op.insn])
        self.fields.create_specs()

    def trap(self, m, trap_addr, return_addr):
        """trap.  sets new PC, stores MSR and old PC in SRR1 and SRR0
        """
        comb  = m.d.comb
        op = self.i.ctx.op
        msr_i = op.msr
        svstate_i = op.svstate
        nia_o = self.o.nia
        svsrr0_o, srr0_o, srr1_o = self.o.svsrr0, self.o.srr0, self.o.srr1

        # trap address
        comb += nia_o.data.eq(trap_addr)
        comb += nia_o.ok.eq(1)

        # addr to begin from on return
        comb += srr0_o.data.eq(return_addr)
        comb += srr0_o.ok.eq(1)

        # take a copy of the current MSR into SRR1
        comb += msr_copy(srr1_o.data, msr_i) # old MSR
        comb += srr1_o.ok.eq(1)

        # take a copy of the current SVSTATE into SVSRR0
        comb += svsrr0_o.data.eq(svstate_i) # old SVSTATE
        comb += svsrr0_o.ok.eq(1)

    def msr_exception(self, m, trap_addr, msr_hv=None):
        """msr_exception - sets bits in MSR specific to an exception.
        the full list of what needs to be done is given in V3.0B
        Book III Section 6.5 p1063 however it turns out that for the
        majority of cases (microwatt showing the way, here), all these
        bits are all set by all (implemented) interrupt types.  this
        may change in the future, hence the (unused) trap_addr argument
        """
        comb  = m.d.comb
        op = self.i.ctx.op
        msr_i, msr_o = op.msr, self.o.msr
        comb += msr_o.data.eq(msr_i) # copy msr, first, then modify
        comb += msr_o.data[MSR.SF].eq(1)
        comb += msr_o.data[MSR.EE].eq(0)
        comb += msr_o.data[MSR.PR].eq(0)
        comb += msr_o.data[MSR.IR].eq(0)
        comb += msr_o.data[MSR.DR].eq(0)
        comb += msr_o.data[MSR.RI].eq(0)
        comb += msr_o.data[MSR.LE].eq(1)
        comb += msr_o.data[MSR.FE0].eq(0)
        comb += msr_o.data[MSR.FE1].eq(0)
        comb += msr_o.data[MSR.VSX].eq(0)
        comb += msr_o.data[MSR.TM].eq(0)
        comb += msr_o.data[MSR.VEC].eq(0)
        comb += msr_o.data[MSR.FP].eq(0)
        comb += msr_o.data[MSR.PMM].eq(0)
        comb += msr_o.data[MSR.TEs].eq(0) # this is only 2 bits
        comb += msr_o.data[MSR.TEe].eq(0) # so just zero them both
        comb += msr_o.data[MSR.UND].eq(0)
        if msr_hv is not None:
            comb += msr_o.data[MSR.HV].eq(msr_hv)
        comb += msr_o.ok.eq(1)

    def ispec(self):
        return TrapInputData(self.pspec)

    def ospec(self):
        return TrapOutputData(self.pspec)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        op = self.i.ctx.op

        # convenience variables
        a_i, b_i = self.i.a, self.i.b
        cia_i, msr_i, svstate_i = op.cia, op.msr, op.svstate
        srr0_i, srr1_i, svsrr0_i = self.i.srr0, self.i.srr1, self.i.svsrr0
        o = self.o.o
        msr_o, nia_o, svstate_o = self.o.msr, self.o.nia, self.o.svstate
        srr0_o, srr1_o, svsrr0_o = self.o.srr0, self.o.srr1, self.o.svsrr0
        traptype, trapaddr = op.traptype, op.trapaddr

        # take copy of D-Form TO field
        i_fields = self.fields.FormD
        to = Signal(i_fields.TO[0:-1].shape())
        comb += to.eq(i_fields.TO[0:-1])

        # signed/unsigned temporaries for RA and RB
        a_s = Signal(signed(64), reset_less=True)
        b_s = Signal(signed(64), reset_less=True)

        a = Signal(64, reset_less=True)
        b = Signal(64, reset_less=True)

        # set up A and B comparison (truncate/sign-extend if 32 bit)
        with m.If(op.is_32bit):
            comb += a_s.eq(exts(a_i, 32, 64))
            comb += b_s.eq(exts(b_i, 32, 64))
            comb += a.eq(a_i[0:32])
            comb += b.eq(b_i[0:32])
        with m.Else():
            comb += a_s.eq(a_i)
            comb += b_s.eq(b_i)
            comb += a.eq(a_i)
            comb += b.eq(b_i)

        # establish comparison bits
        lt_s = Signal(reset_less=True)
        gt_s = Signal(reset_less=True)
        lt_u = Signal(reset_less=True)
        gt_u = Signal(reset_less=True)
        equal = Signal(reset_less=True)

        comb += lt_s.eq(a_s < b_s)
        comb += gt_s.eq(a_s > b_s)
        comb += lt_u.eq(a < b)
        comb += gt_u.eq(a > b)
        comb += equal.eq(a == b)

        # They're in reverse bit order because POWER.
        # Check V3.0B Book 1, Appendix C.6 for chart
        trap_bits = Signal(5, reset_less=True)
        comb += trap_bits.eq(Cat(gt_u, lt_u, equal, gt_s, lt_s))

        # establish if the trap should go ahead (any tests requested in TO)
        # or if traptype is set already
        should_trap = Signal(reset_less=True)
        comb += should_trap.eq((trap_bits & to).any() | traptype.any())

        # TODO: some #defines for the bits n stuff.
        with m.Switch(op.insn_type):

            ###############
            # TDI/TWI/TD/TW.  v3.0B p90-91

            with m.Case(MicrOp.OP_TRAP):
                # trap instructions (tw, twi, td, tdi)
                with m.If(should_trap):
                    # generate trap-type program interrupt
                    self.trap(m, trapaddr<<4, cia_i)
                    with m.If(traptype == 0):
                        # say trap occurred (see 3.0B Book III 6.5.9 p1074-6)
                        comb += srr1_o.data[PI.TRAP].eq(1)
                    with m.If(traptype & TT.PRIV):
                        comb += srr1_o.data[PI.PRIV].eq(1)
                    with m.If(traptype & TT.FP):
                        comb += srr1_o.data[PI.FP].eq(1)
                    with m.If(traptype & TT.ADDR):
                        comb += srr1_o.data[PI.ADR].eq(1)
                    with m.If(traptype & TT.MEMEXC):
                        # decode exception bits, store in SRR1
                        exc = LDSTException("trapexc")
                        comb += exc.eq(op.ldst_exc)
                        comb += srr1_o.data[PI.INVALID].eq(exc.invalid)
                        comb += srr1_o.data[PI.PERMERR].eq(exc.perm_error)
                        comb += srr1_o.data[PI.ILLEG].eq(exc.badtree)
                        comb += srr1_o.data[PI.PRIV].eq(exc.rc_error)
                    with m.If(traptype & TT.EINT):
                        # do nothing unusual? see 3.0B Book III 6.5.7 p1073
                        pass
                    with m.If(traptype & TT.DEC):
                        # do nothing unusual?
                        pass
                    with m.If(traptype & TT.ILLEG):
                        comb += srr1_o.data[PI.ILLEG].eq(1)
                    comb += srr1_o.ok.eq(1)

                    # when SRR1 is written to, update MSR bits
                    self.msr_exception(m, trapaddr)

                    # and store SVSTATE in SVSRR0
                    comb += svsrr0_o.data.eq(svstate_i)
                    comb += svsrr0_o.ok.eq(1)

            ###################
            # MTMSR/D.  v3.0B p TODO - move to MSR

            with m.Case(MicrOp.OP_MTMSRD, MicrOp.OP_MTMSR):
                L = self.fields.FormX.L[0:-1] # X-Form field L
                # start with copy of msr
                comb += msr_o.eq(msr_i)
                with m.If(L):
                    # just update RI..EE
                    comb += msr_o.data[MSR.RI].eq(a_i[MSR.RI])
                    comb += msr_o.data[MSR.EE].eq(a_i[MSR.EE])
                with m.Else():
                    # Architecture says to leave out bits 3 (HV), 51 (ME)
                    # and 63 (LE) (IBM bit numbering)
                    with m.If(op.insn_type == MicrOp.OP_MTMSRD):
                        # not MSB0 notation here!
                        for stt, end in [(1,12), (13, 60), (61, 64)]:
                            comb += msr_o.data[stt:end].eq(a_i[stt:end])
                        # put *back* bits 29-31 (MSB0 notation)
                        bits = field_slice(29, 31)
                        with m.If((msr_i[bits] == Const(0b010, 3)) &
                                  (a_i[bits] == Const(0b000, 3))):
                            comb += msr_o.data[bits].eq(msr_i[bits])

                    with m.Else():
                        # mtmsr - 32-bit, only room for bottom 32 LSB flags
                        for stt, end in [(1,12), (13, 32)]:
                            comb += msr_o.data[stt:end].eq(a_i[stt:end])
                    msr_check_pr(m, msr_o.data)

                # Per https://bugs.libre-soc.org/show_bug.cgi?id=325#c123,
                # this actually *is* in the microwatt code now.
                #
                # hypervisor stuff.  here: bits 3 (HV) and 51 (ME) were
                # copied over by msr_copy but if HV was not set we need
                # the *original* (msr_i) bits
                with m.If(~msr_i[MSR.HV]):
                    comb += msr_o.data[MSR.HV].eq(msr_i[MSR.HV])
                    comb += msr_o.data[MSR.ME].eq(msr_i[MSR.ME])

                comb += msr_o.ok.eq(1)

            ###################
            # MFMSR.  v3.0B p TODO - move from MSR

            with m.Case(MicrOp.OP_MFMSR):
                # some of the bits need zeroing?  apparently not
                comb += o.data.eq(msr_i)
                comb += o.ok.eq(1)

            ###################
            # RFID.  v3.0B p955

            with m.Case(MicrOp.OP_RFID):

                # return addr was in srr0
                comb += nia_o.data.eq(br_ext(srr0_i[2:]))
                comb += nia_o.ok.eq(1)

                # svstate was in svsrr0
                comb += svstate_o.data.eq(svstate_i)
                comb += svstate_o.ok.eq(1)

                # MSR was in srr1: copy it over, however *caveats below*
                comb += msr_copy(msr_o.data, srr1_i, zero_me=False) # don't zero

                with m.If(~self.i.ctx.op.insn[9]): # XXX BAD HACK! (hrfid)
                    with m.If(field(msr_i, 3)): # HV
                        comb += field(msr_o, 51).eq(field(srr1_i, 51)) # ME
                    with m.Else():
                        comb += field(msr_o, 51).eq(field(msr_i, 51)) # ME

                # check problem state
                msr_check_pr(m, msr_o.data)

                # don't understand but it's in the spec.  again: bits 32-34
                # are copied from srr1_i and need *restoring* to msr_i

                bits = field_slice(29, 31)  # bits 29, 30, 31 (Power notation)
                with m.If((msr_i[bits] == Const(0b010, 3)) &
                          (srr1_i[bits] == Const(0b000, 3))):
                    comb += msr_o.data[bits].eq(msr_i[bits])

                comb += msr_o.ok.eq(1)

            #################
            # SC.  v3.0B p952

            with m.Case(MicrOp.OP_SC):
                # scv is not covered here. currently an illegal instruction.
                # raising "illegal" is the decoder's job, not ours, here.

                # According to V3.0B, Book II, section 3.3.1, the System Call
                # instruction allows you to trap directly into the hypervisor
                # if the opcode's LEV sub-field is equal to 1.
                # however we are following *microwatt* - which has
                # not implemented hypervisor.

                # jump to the trap address, return at cia+4
                self.trap(m, 0xc00, cia_i+4)
                self.msr_exception(m, 0xc00)

            # TODO (later)
            #with m.Case(MicrOp.OP_ADDPCIS):
            #    pass

        comb += self.o.ctx.eq(self.i.ctx)

        return m
