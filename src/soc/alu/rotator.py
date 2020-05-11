from soc.alu.rotl import ROTL

#note BE bit numbering
def right_mask(m, mask_begin):
    ret = Signal(64, name="right_mask", reset_less=True)
    m.d.comb += ret.eq(0)
    for i in range(64):
        with m.If(i >= unsigned(mask_begin)): # set from i upwards
            m.d.comb += ret[63 - i].eq(1)
    return ret;

def left_mask(m, mask_end):
    ret = Signal(64, name="left_mask", reset_less=True)
    m.d.comb += ret.eq(0)
    with m.If(mask_end[6] != 0):
        return ret
    for i in range(64):
        with m.If(i <= unsigned(mask_end)): # set from i downwards
            m.d.comb += ret[63 - i].eq(1)
    return ret;


class Rotator(Elaboratable):
    def __init__(self):
        # input
        self.rs = Signal(64, reset_less=True)
        self.ra = Signal(64, reset_less=True)
        self.shift = Signal(7, reset_less=True)
        self.insn = Signal(32, reset_less=True)
        self.is_32bit = Signal(reset_less=True)
        self.right_shift = Signal(reset_less=True)
        self.arith = Signal(reset_less=True)
        self.clear_left = Signal(reset_less=True)
        self.clear_right = Signal(reset_less=True)
        # output
        self.result = Signal(64, reset_less=True)
        self.carry_out = Signal(reset_less=True)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb

        # temporaries
        repl32 = Signal(64, reset_less=True)
        rot_count = Signal(6, reset_less=True)
        rot = Signal(64, reset_less=True)
        sh = Signal(7, reset_less=True)
        mb = Signal(7, reset_less=True)
        me = Signal(7, reset_less=True)
        mr = Signal(64, reset_less=True)
        ml = Signal(64, reset_less=True)
        output_mode = Signal(2, reset_less=True)

        # First replicate bottom 32 bits to both halves if 32-bit
        comb += repl32[0:32].eq(rs[0:32])
        with m.If(is_32bit):
            comb += repl32[32:64].eq(rs[:32])

        # Negate shift count for right shifts
        with m.If(right_shift):
            comb += rot_count.eq(-signed(shift[0:6]))
        with m.Else():
            comb += rot_count.eq(shift[0:6])

        # ROTL submodule
        m.submodules.rotl = rotl = ROTL(64)
        comb += rotl.a.eq(repl32)
        comb += rotl.b.eq(rot_count)
        comb += rot.eq(rotl.o)

        # Trim shift count to 6 bits for 32-bit shifts
        comb += sh.eq(Cat(shift[0:6], shift[6] & ~is_32bit))

        # XXX errr... we should already have these, in Fields?  oh well
        # Work out mask begin/end indexes (caution, big-endian bit numbering)

        # mask-begin (mb)
        with m.If(clear_left):
            with m.If(is_32bit):
                comb += mb.eq(Cat(insn[6:11], Const(0b01, 2)))
            with m.Else():
                comb += mb.eq(Cat(insn[6:11], insn[5], Const(0b0, 1)))
        with m.Elif(right_shift):
            # this is basically mb <= sh + (is_32bit? 32: 0);
            with m.If(is_32bit):
                comb += mb.eq(Cat(sh[0:5], ~sh[5], sh[5]))
            with m.Else():
                comb += mb.eq(sh)
        with m.Else():
            comb += mb.eq(Cat(Const(0b0, 5), is_32bit, Const(0b0, 1)))

        # mask-end (me)
        with m.If(clear_right & is_32bit):
            comb += me.eq(Cat(insn[1:6], Const(0b01, 2)))
        with m.Elif(clear_right & ~clear_left):
            comb += me.eq(Cat(insn[6:11], insn[5], Const(0b0, 1)))
        with m.Else():
            # effectively, 63 - sh
            comb += me.eq(Cat(~shift[0:6], shift[6]))

        # Calculate left and right masks
        comb += mr.eq(right_mask(m, mb))
        comb += ml.eq(left_mask(m, me))

        # Work out output mode
        # 00 for sl[wd]
        # 0w for rlw*, rldic, rldicr, rldimi, where w = 1 iff mb > me
        # 10 for rldicl, sr[wd]
        # 1z for sra[wd][i], z = 1 if rs is negative
        with m.If((clear_left & ~clear_right) | right_shift):
            comb += output_mode[1].eq(1)
            comb += output_mode[0].eq(arith & repl32[63])
        with m.Else():
            comb += output_mode[1].eq(0)
            mbgt = clear_right & unsigned(mb[0:6]) > unsigned(me[0:6])
            comb += output_mode[0].eq(mbgt)

        # Generate output from rotated input and masks
        with m.Switch(output_mode):
            with m.Case(0b00):
                comb += result.eq((rot & (mr & ml)) | (ra & ~(mr & ml)))
            with m.Case(0b01):
                comb += result.eq((rot & (mr | ml)) | (ra & ~(mr or ml)))
            with m.Case(0b10):
                comb += result.eq(rot & mr)
            with m.Case(0b11):
                comb += result.eq(rot | ~mr)

        # Generate carry output for arithmetic shift right of negative value
        with m.If(output_mode = 0b11):
            comb += carry_out.eq(rs & ~ml)

