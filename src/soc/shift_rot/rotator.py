# Manual translation and adaptation of rotator.vhdl from microwatt into nmigen
#

from nmigen import (Elaboratable, Signal, Module, Const, Cat,
                    unsigned, signed)
from soc.shift_rot.rotl import ROTL

# note BE bit numbering
def right_mask(m, mask_begin):
    ret = Signal(64, name="right_mask", reset_less=True)
    with m.If(mask_begin <= 64):
        m.d.comb += ret.eq((1<<(64-mask_begin)) - 1)
    return ret

def left_mask(m, mask_end):
    ret = Signal(64, name="left_mask", reset_less=True)
    m.d.comb += ret.eq(~((1<<(63-mask_end)) - 1))
    return ret


class Rotator(Elaboratable):
    """Rotator: covers multiple POWER9 rotate functions

        supported modes:

        * sl[wd]
        * rlw*, rldic, rldicr, rldimi
        * rldicl, sr[wd]
        * sra[wd][i]

        use as follows:

        * shift = RB[0:7]
        * arith = 1 when is_signed
        * right_shift = 1 when insn_type is OP_SHR
        * clear_left = 1 when insn_type is OP_RLC or OP_RLCL
        * clear_right = 1 when insn_type is OP_RLC or OP_RLCR
    """
    def __init__(self):
        # input
        self.rs = Signal(64, reset_less=True)       # RS
        self.ra = Signal(64, reset_less=True)       # RA
        self.shift = Signal(7, reset_less=True)     # RB[0:7]
        self.insn = Signal(32, reset_less=True)     # for mb and me fields
        self.is_32bit = Signal(reset_less=True)
        self.right_shift = Signal(reset_less=True)
        self.arith = Signal(reset_less=True)
        self.clear_left = Signal(reset_less=True)
        self.clear_right = Signal(reset_less=True)
        # output
        self.result_o = Signal(64, reset_less=True)
        self.carry_out_o = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        ra, rs = self.ra, self.rs

        # temporaries
        rot_in = Signal(64, reset_less=True)
        rot_count = Signal(6, reset_less=True)
        rot = Signal(64, reset_less=True)
        sh = Signal(7, reset_less=True)
        mb = Signal(7, reset_less=True)
        me = Signal(7, reset_less=True)
        mr = Signal(64, reset_less=True)
        ml = Signal(64, reset_less=True)
        output_mode = Signal(2, reset_less=True)

        # First replicate bottom 32 bits to both halves if 32-bit
        comb += rot_in[0:32].eq(rs[0:32])
        with m.If(self.is_32bit):
            comb += rot_in[32:64].eq(rs[0:32])
        with m.Else():
            comb += rot_in[32:64].eq(rs[32:64])

        shift_signed = Signal(signed(6))
        comb += shift_signed.eq(self.shift[0:6])

        # Negate shift count for right shifts
        with m.If(self.right_shift):
            comb += rot_count.eq(-shift_signed)
        with m.Else():
            comb += rot_count.eq(self.shift[0:6])

        # ROTL submodule
        m.submodules.rotl = rotl = ROTL(64)
        comb += rotl.a.eq(rot_in)
        comb += rotl.b.eq(rot_count)
        comb += rot.eq(rotl.o)

        # Trim shift count to 6 bits for 32-bit shifts
        comb += sh.eq(Cat(self.shift[0:6], self.shift[6] & ~self.is_32bit))

        # XXX errr... we should already have these, in Fields?  oh well
        # Work out mask begin/end indexes (caution, big-endian bit numbering)

        # mask-begin (mb)
        with m.If(self.clear_left):
            with m.If(self.is_32bit):
                comb += mb.eq(Cat(self.insn[6:11], Const(0b01, 2)))
            with m.Else():
                comb += mb.eq(Cat(self.insn[6:11], self.insn[5], Const(0b0, 1)))
        with m.Elif(self.right_shift):
            # this is basically mb = sh + (is_32bit? 32: 0);
            with m.If(self.is_32bit):
                comb += mb.eq(Cat(sh[0:5], ~sh[5], sh[5]))
            with m.Else():
                comb += mb.eq(sh)
        with m.Else():
            comb += mb.eq(Cat(Const(0b0, 5), self.is_32bit, Const(0b0, 1)))

        # mask-end (me)
        with m.If(self.clear_right & self.is_32bit):
            comb += me.eq(Cat(self.insn[1:6], Const(0b01, 2)))
        with m.Elif(self.clear_right & ~self.clear_left):
            comb += me.eq(Cat(self.insn[6:11], self.insn[5], Const(0b0, 1)))
        with m.Else():
            # effectively, 63 - sh
            comb += me.eq(Cat(~self.shift[0:6], self.shift[6]))

        # Calculate left and right masks
        comb += mr.eq(right_mask(m, mb))
        comb += ml.eq(left_mask(m, me))

        # Work out output mode
        # 00 for sl[wd]
        # 0w for rlw*, rldic, rldicr, rldimi, where w = 1 iff mb > me
        # 10 for rldicl, sr[wd]
        # 1z for sra[wd][i], z = 1 if rs is negative
        with m.If((self.clear_left & ~self.clear_right) | self.right_shift):
            comb += output_mode.eq(Cat(self.arith & rot_in[63], Const(1, 1)))
        with m.Else():
            mbgt = self.clear_right & (mb[0:6] > me[0:6])
            comb += output_mode.eq(Cat(mbgt, Const(0, 1)))

        # Generate output from rotated input and masks
        with m.Switch(output_mode):
            with m.Case(0b00):
                comb += self.result_o.eq((rot & (mr & ml)) | (ra & ~(mr & ml)))
            with m.Case(0b01):
                comb += self.result_o.eq((rot & (mr | ml)) | (ra & ~(mr | ml)))
            with m.Case(0b10):
                comb += self.result_o.eq(rot & mr)
            with m.Case(0b11):
                comb += self.result_o.eq(rot | ~mr)
                # Generate carry output for arithmetic shift right of -ve value
                comb += self.carry_out_o.eq(rs & ~ml)

        return m

