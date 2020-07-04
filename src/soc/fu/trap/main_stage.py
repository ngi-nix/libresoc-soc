"""Trap Pipeline

* https://bugs.libre-soc.org/show_bug.cgi?id=325
* https://bugs.libre-soc.org/show_bug.cgi?id=344
* https://libre-soc.org/openpower/isa/fixedtrap/
"""

from nmigen import (Module, Signal, Cat, Mux, Const, signed)
from nmutil.pipemodbase import PipeModBase
from nmutil.extend import exts
from soc.fu.trap.pipe_data import TrapInputData, TrapOutputData
from soc.fu.branch.main_stage import br_ext
from soc.decoder.power_enums import InternalOp

from soc.decoder.power_fields import DecodeFields
from soc.decoder.power_fieldsn import SignalBitRange

from soc.decoder.power_decoder2 import (TT_FP, TT_PRIV, TT_TRAP, TT_ADDR)
from soc.consts import MSR, PI

def msr_copy(msr_o, msr_i, zero_me=True):
    """
    -- ISA says this:
    --  Defined MSR bits are classified as either full func-
    --  tion or partial function. Full function MSR bits are
    --  saved in SRR1 or HSRR1 when an interrupt other
    --  than a System Call Vectored interrupt occurs and
    --  restored by rfscv, rfid, or hrfid, while partial func-
    --  tion MSR bits are not saved or restored.
    --  Full function MSR bits lie in the range 0:32, 37:41, and
    --  48:63, and partial function MSR bits lie in the range
    --  33:36 and 42:47. (Note this is IBM bit numbering).
    msr_out := (others => '0');
    msr_out(63 downto 31) := msr(63 downto 31);
    msr_out(26 downto 22) := msr(26 downto 22);
    msr_out(15 downto 0)  := msr(15 downto 0);
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
        """trap """ # TODO add descriptive docstring
        comb  = m.d.comb
        msr_i = self.i.msr
        nia_o, srr0_o, srr1_o = self.o.nia, self.o.srr0, self.o.srr1

        # trap address
        comb += nia_o.data.eq(trap_addr)
        comb += nia_o.ok.eq(1)

        # addr to begin from on return
        comb += srr0_o.data.eq(return_addr)
        comb += srr0_o.ok.eq(1)

        # take a copy of the current MSR in SRR1
        comb += msr_copy(srr1_o.data, msr_i) # old MSR
        comb += srr1_o.ok.eq(1)

    def ispec(self):
        return TrapInputData(self.pspec)

    def ospec(self):
        return TrapOutputData(self.pspec)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        op = self.i.ctx.op

        # convenience variables
        a_i, b_i, cia_i, msr_i = self.i.a, self.i.b, self.i.cia, self.i.msr
        srr0_i, srr1_i = self.i.srr0, self.i.srr1
        o, msr_o, nia_o = self.o.o, self.o.msr, self.o.nia
        srr0_o, srr1_o = self.o.srr0, self.o.srr1
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
            #### trap ####
            with m.Case(InternalOp.OP_TRAP):
                # trap instructions (tw, twi, td, tdi)
                with m.If(should_trap):
                    # generate trap-type program interrupt
                    self.trap(m, trapaddr<<4, cia_i)
                    with m.If(traptype == 0):
                        # say trap occurred (see 3.0B Book III 7.5.9)
                        comb += srr1_o.data[PI.TRAP].eq(1)
                    with m.If(traptype & TT_PRIV):
                        comb += srr1_o.data[PI.PRIV].eq(1)
                    with m.If(traptype & TT_FP):
                        comb += srr1_o.data[PI.FP].eq(1)
                    with m.If(traptype & TT_ADDR):
                        comb += srr1_o.data[PI.ADR].eq(1)

            # move to MSR
            with m.Case(InternalOp.OP_MTMSRD):
                L = self.fields.FormX.L[0:-1] # X-Form field L
                with m.If(L):
                    # just update EE and RI
                    comb += msr_o.data[MSR.EE].eq(a_i[MSR.EE])
                    comb += msr_o.data[MSR.RI].eq(a_i[MSR.RI])
                with m.Else():
                    # Architecture says to leave out bits 3 (HV), 51 (ME)
                    # and 63 (LE) (IBM bit numbering)
                    for stt, end in [(1,12), (13, 60), (61, 64)]:
                        comb += msr_o.data[stt:end].eq(a_i[stt:end])
                    msr_check_pr(m, msr_o.data)
                comb += msr_o.ok.eq(1)

            # move from MSR
            with m.Case(InternalOp.OP_MFMSR):
                # TODO: some of the bits need zeroing?  apparently not
                comb += o.data.eq(msr_i)
                comb += o.ok.eq(1)

            with m.Case(InternalOp.OP_RFID):
                # XXX f_out.virt_mode <= b_in(MSR.IR) or b_in(MSR.PR);
                # XXX f_out.priv_mode <= not b_in(MSR.PR);

                # return addr was in srr0
                comb += nia_o.data.eq(br_ext(srr0_i[2:]))
                comb += nia_o.ok.eq(1)
                # MSR was in srr1
                comb += msr_copy(msr_o.data, srr1_i, zero_me=False) # don't zero
                msr_check_pr(m, msr_o.data)
                comb += msr_o.ok.eq(1)

            # TODO (later) - add OP_SC
            #with m.Case(InternalOp.OP_SC):
            #    # TODO: scv must generate illegal instruction.  this is
            #    # the decoder's job, not ours, here.
            #
            #    # jump to the trap address, return at cia+4
            #    self.trap(m, 0xc00, cia_i+4)

            # TODO (later)
            #with m.Case(InternalOp.OP_ADDPCIS):
            #    pass

        comb += self.o.ctx.eq(self.i.ctx)

        return m
