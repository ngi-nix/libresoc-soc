"""Trap Pipeline

* https://bugs.libre-soc.org/show_bug.cgi?id=325
* https://bugs.libre-soc.org/show_bug.cgi?id=344
* https://libre-soc.org/openpower/isa/fixedtrap/
"""

from nmigen import (Module, Signal, Cat, Mux, Const, signed)
from nmutil.pipemodbase import PipeModBase
from nmutil.extend import exts
from soc.fu.trap.pipe_data import TrapInputData, TrapOutputData
from soc.decoder.power_enums import InternalOp

from soc.decoder.power_fields import DecodeFields
from soc.decoder.power_fieldsn import SignalBitRange

# TODO at some point move these to their own module (for use elsewhere)
"""
    -- MSR bit numbers
    constant MSR_SF  : integer := (63 - 0);     -- Sixty-Four bit mode
    constant MSR_EE  : integer := (63 - 48);    -- External interrupt Enable
    constant MSR_PR  : integer := (63 - 49);    -- PRoblem state
    constant MSR_IR  : integer := (63 - 58);    -- Instruction Relocation
    constant MSR_DR  : integer := (63 - 59);    -- Data Relocation
    constant MSR_RI  : integer := (63 - 62);    -- Recoverable Interrupt
    constant MSR_LE  : integer := (63 - 63);    -- Little Endian
"""

class TrapMainStage(PipeModBase):
    def __init__(self, pspec):
        super().__init__(pspec, "main")
        self.fields = DecodeFields(SignalBitRange, [self.i.ctx.op.insn])
        self.fields.create_specs()

    def ispec(self):
        return TrapInputData(self.pspec)

    def ospec(self):
        return TrapOutputData(self.pspec)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        op = self.i.ctx.op
        a_i, b_i = self.i.a, self.i.b

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
        trap_bits = Signal(5)
        comb += trap_bits.eq(Cat(gt_u, lt_u, equal, gt_s, lt_s))

        # establish if the trap should go ahead (any tests requested in TO)
        should_trap = Signal()
        comb += should_trap.eq((trap_bits & to).any())

        # TODO: some #defines for the bits n stuff.
        with m.Switch(op):
            #### trap ####
            with m.Case(InternalOp.OP_TRAP):
                """
                -- trap instructions (tw, twi, td, tdi)
                if or (trapval and insn_to(e_in.insn)) = '1' then
                    -- generate trap-type program interrupt
                    exception := '1';
                    ctrl_tmp.irq_nia <= std_logic_vector(to_unsigned(16#700#, 64));
                    ctrl_tmp.srr1 <= msr_copy(ctrl.msr);
                    -- set bit 46 to say trap occurred
                    ctrl_tmp.srr1(63 - 46) <= '1';
                """
                with m.If(should_trap):
                    comb += self.o.nia.data.eq(0x700)         # trap address
                    comb += self.o.nia.ok.eq(1)
                    comb += self.o.srr1.data.eq(self.i.msr)   # old MSR
                    comb += self.o.srr1.data[63-46].eq(1)     # XXX which bit?
                    comb += self.o.srr1.ok.eq(1)
                    comb += self.o.srr0.data.eq(self.i.cia)   # old PC
                    comb += self.o.srr0.ok.eq(1)

            # move to SPR
            with m.Case(InternalOp.OP_MTMSR):
                # TODO: some of the bits need zeroing?
                """
                if e_in.insn(16) = '1' then
                    -- just update EE and RI
                    ctrl_tmp.msr(MSR_EE) <= c_in(MSR_EE);
                    ctrl_tmp.msr(MSR_RI) <= c_in(MSR_RI);
                else
                    -- Architecture says to leave out bits 3 (HV), 51 (ME)
                    -- and 63 (LE) (IBM bit numbering)
                    ctrl_tmp.msr(63 downto 61) <= c_in(63 downto 61);
                    ctrl_tmp.msr(59 downto 13) <= c_in(59 downto 13);
                    ctrl_tmp.msr(11 downto 1)  <= c_in(11 downto 1);
                    if c_in(MSR_PR) = '1' then
                        ctrl_tmp.msr(MSR_EE) <= '1';
                        ctrl_tmp.msr(MSR_IR) <= '1';
                        ctrl_tmp.msr(MSR_DR) <= '1';
                """
                comb += self.o.msr.data.eq(a)
                comb += self.o.msr.ok.eq(1)

            # move from SPR
            with m.Case(InternalOp.OP_MFMSR):
                # TODO: some of the bits need zeroing?  apparently not
                """
                    when OP_MFMSR =>
                        result := ctrl.msr;
                        result_en := '1';
                """
                comb += self.o.o.data.eq(self.i.msr)
                comb += self.o.o.ok.eq(1)

            # TODO
            with m.Case(InternalOp.OP_RFID):
                """
                # XXX f_out.virt_mode <= b_in(MSR_IR) or b_in(MSR_PR);
                # XXX f_out.priv_mode <= not b_in(MSR_PR);
                f_out.redirect_nia <= a_in(63 downto 2) & "00"; -- srr0
                -- Can't use msr_copy here because the partial function MSR
                -- bits should be left unchanged, not zeroed.
                ctrl_tmp.msr(63 downto 31) <= b_in(63 downto 31);
                ctrl_tmp.msr(26 downto 22) <= b_in(26 downto 22);
                ctrl_tmp.msr(15 downto 0)  <= b_in(15 downto 0);
                if b_in(MSR_PR) = '1' then
                    ctrl_tmp.msr(MSR_EE) <= '1';
                    ctrl_tmp.msr(MSR_IR) <= '1';
                    ctrl_tmp.msr(MSR_DR) <= '1';
                end if;
                """
                pass

            # TODO
            with m.Case(InternalOp.OP_SC):
                """
                # TODO: scv must generate illegal instruction.  this is
                # the decoder's job, not ours, here.
                ctrl_tmp.irq_nia <= std_logic_vector(to_unsigned(16#C00#, 64));
                ctrl_tmp.srr1 <= msr_copy(ctrl.msr);
                """
                pass

            #with m.Case(InternalOp.OP_ADDPCIS):
            #    pass

        comb += self.o.ctx.eq(self.i.ctx)

        return m
