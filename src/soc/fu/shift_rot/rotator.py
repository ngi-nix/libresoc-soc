# Manual translation and adaptation of rotator.vhdl from microwatt into nmigen
#
from nmigen.compat.sim import run_simulation

from nmigen import (Elaboratable, Signal, Module, Const, Cat, Repl,
                    unsigned, signed)
from soc.fu.shift_rot.rotl import ROTL
from nmigen.back.pysim import Settle
from nmutil.extend import exts
from nmutil.mask import Mask


# note BE bit numbering
def right_mask(m, mask_begin):
    ret = Signal(64, name="right_mask", reset_less=True)
    with m.If(mask_begin <= 64):
        m.d.comb += ret.eq((1 << (64-mask_begin)) - 1)
    with m.Else():
        m.d.comb += ret.eq(0)
    return ret


def left_mask(m, mask_end):
    ret = Signal(64, name="left_mask", reset_less=True)
    m.d.comb += ret.eq(~((1 << (63-mask_end)) - 1))
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
        self.me = Signal(5, reset_less=True)        # ME field
        self.mb = Signal(5, reset_less=True)        # MB field
        # extra bit of mb in MD-form
        self.mb_extra = Signal(1, reset_less=True)
        self.ra = Signal(64, reset_less=True)       # RA
        self.rs = Signal(64, reset_less=True)       # RS
        self.shift = Signal(7, reset_less=True)     # RB[0:7]
        self.is_32bit = Signal(reset_less=True)
        self.right_shift = Signal(reset_less=True)
        self.arith = Signal(reset_less=True)
        self.clear_left = Signal(reset_less=True)
        self.clear_right = Signal(reset_less=True)
        self.sign_ext_rs = Signal(reset_less=True)
        # output
        self.result_o = Signal(64, reset_less=True)
        self.carry_out_o = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        ra, rs = self.ra, self.rs

        # temporaries
        rot_count = Signal(6, reset_less=True)
        rot = Signal(64, reset_less=True)
        sh = Signal(7, reset_less=True)
        mb = Signal(7, reset_less=True)
        me = Signal(7, reset_less=True)
        mr = Signal(64, reset_less=True)
        ml = Signal(64, reset_less=True)
        output_mode = Signal(2, reset_less=True)
        hi32 = Signal(32, reset_less=True)
        repl32 = Signal(64, reset_less=True)

        # First replicate bottom 32 bits to both halves if 32-bit
        with m.If(self.is_32bit):
            comb += hi32.eq(rs[0:32])
        with m.Elif(self.sign_ext_rs):
            # sign-extend bottom 32 bits
            comb += hi32.eq(Repl(rs[31], 32))
        with m.Else():
            comb += hi32.eq(rs[32:64])
        comb += repl32.eq(Cat(rs[0:32], hi32))

        shift_signed = Signal(signed(6))
        comb += shift_signed.eq(self.shift[0:6])

        # Negate shift count for right shifts
        with m.If(self.right_shift):
            comb += rot_count.eq(-shift_signed)
        with m.Else():
            comb += rot_count.eq(self.shift[0:6])

        # ROTL submodule
        m.submodules.rotl = rotl = ROTL(64)
        comb += rotl.a.eq(repl32)
        comb += rotl.b.eq(rot_count)
        comb += rot.eq(rotl.o)

        # Trim shift count to 6 bits for 32-bit shifts
        comb += sh.eq(Cat(self.shift[0:6], self.shift[6] & ~self.is_32bit))

        # XXX errr... we should already have these, in Fields?  oh well
        # Work out mask begin/end indexes (caution, big-endian bit numbering)

        # mask-begin (mb)
        with m.If(self.clear_left):
            comb += mb.eq(self.mb)
            with m.If(self.is_32bit):
                comb += mb[5:7].eq(Const(0b01, 2))
            with m.Else():
                comb += mb[5:7].eq(Cat(self.mb_extra, Const(0b0, 1)))
        with m.Elif(self.right_shift):
            # this is basically mb = sh + (is_32bit? 32: 0);
            comb += mb.eq(sh)
            with m.If(self.is_32bit):
                comb += mb[5:7].eq(Cat(~sh[5], sh[5]))
        with m.Else():
            comb += mb.eq(Cat(Const(0b0, 5), self.is_32bit, Const(0b0, 1)))

        # mask-end (me)
        with m.If(self.clear_right & self.is_32bit):
            # TODO: track down where this is.  have to use fields.
            comb += me.eq(Cat(self.me, Const(0b01, 2)))
        with m.Elif(self.clear_right & ~self.clear_left):
            # this is me, have to use fields
            comb += me.eq(Cat(self.mb, self.mb_extra, Const(0b0, 1)))
        with m.Else():
            # effectively, 63 - sh
            comb += me.eq(Cat(~sh[0:6], sh[6]))

        # Calculate left and right masks
        m.submodules.right_mask = right_mask = Mask(64)
        with m.If(mb <= 64):
            comb += right_mask.shift.eq(64-mb)
            comb += mr.eq(right_mask.mask)
        with m.Else():
            comb += mr.eq(0)
        #comb += mr.eq(right_mask(m, mb))

        m.submodules.left_mask = left_mask = Mask(64)
        comb += left_mask.shift.eq(63-me)
        comb += ml.eq(~left_mask.mask)
        #comb += ml.eq(left_mask(m, me))


        # Work out output mode
        # 00 for sl[wd]
        # 0w for rlw*, rldic, rldicr, rldimi, where w = 1 iff mb > me
        # 10 for rldicl, sr[wd]
        # 1z for sra[wd][i], z = 1 if rs is negative
        with m.If((self.clear_left & ~self.clear_right) | self.right_shift):
            comb += output_mode.eq(Cat(self.arith & repl32[63], Const(1, 1)))
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
                comb += self.carry_out_o.eq((rs & ~ml).bool())

        return m


if __name__ == '__main__':

    m = Module()
    comb = m.d.comb
    mr = Signal(64)
    mb = Signal(6)
    comb += mr.eq(left_mask(m, mb))

    def loop():
        for i in range(64):
            yield mb.eq(63-i)
            yield Settle()
            res = yield mr
            print(i, hex(res))

    run_simulation(m, [loop()],
                   vcd_name="test_mask.vcd")
