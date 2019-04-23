# SPDX-License-Identifier: LGPL-2.1-or-later
# See Notices.txt for copyright information
from nmigen import Signal, Module, Const, Cat, Elaboratable
from nmigen.cli import verilog, rtlil


class LFSRPolynomial(set):
    """ implements a polynomial for use in LFSR
    """
    def __init__(self, exponents=()):
        for e in exponents:
            assert isinstance(e, int), TypeError("%s must be an int" % repr(e))
            assert (e >= 0), ValueError("%d must not be negative" % e)
        set.__init__(self, set(exponents).union({0})) # must contain zero

    @property
    def max_exponent(self):
        return max(self) # derived from set, so this returns the max exponent

    @property
    def exponents(self):
        exponents = list(self) # get elements of set as a list
        exponents.sort(reverse=True)
        return exponents

    def __str__(self):
        expd = {0: "1", 1: 'x', 2: "x^{}"} # case 2 isn't 2, it's min(i,2)
        retval = map(lambda i: expd[min(i,2)].format(i), self.exponents)
        return " + ".join(retval)

    def __repr__(self):
        return "LFSRPolynomial(%s)" % self.exponents


# list of selected polynomials from https://web.archive.org/web/20190418121923/https://en.wikipedia.org/wiki/Linear-feedback_shift_register#Some_polynomials_for_maximal_LFSRs  # noqa
LFSR_POLY_2 = LFSRPolynomial([2, 1, 0])
LFSR_POLY_3 = LFSRPolynomial([3, 2, 0])
LFSR_POLY_4 = LFSRPolynomial([4, 3, 0])
LFSR_POLY_5 = LFSRPolynomial([5, 3, 0])
LFSR_POLY_6 = LFSRPolynomial([6, 5, 0])
LFSR_POLY_7 = LFSRPolynomial([7, 6, 0])
LFSR_POLY_8 = LFSRPolynomial([8, 6, 5, 4, 0])
LFSR_POLY_9 = LFSRPolynomial([9, 5, 0])
LFSR_POLY_10 = LFSRPolynomial([10, 7, 0])
LFSR_POLY_11 = LFSRPolynomial([11, 9, 0])
LFSR_POLY_12 = LFSRPolynomial([12, 11, 10, 4, 0])
LFSR_POLY_13 = LFSRPolynomial([13, 12, 11, 8, 0])
LFSR_POLY_14 = LFSRPolynomial([14, 13, 12, 2, 0])
LFSR_POLY_15 = LFSRPolynomial([15, 14, 0])
LFSR_POLY_16 = LFSRPolynomial([16, 15, 13, 4, 0])
LFSR_POLY_17 = LFSRPolynomial([17, 14, 0])
LFSR_POLY_18 = LFSRPolynomial([18, 11, 0])
LFSR_POLY_19 = LFSRPolynomial([19, 18, 17, 14, 0])
LFSR_POLY_20 = LFSRPolynomial([20, 17, 0])
LFSR_POLY_21 = LFSRPolynomial([21, 19, 0])
LFSR_POLY_22 = LFSRPolynomial([22, 21, 0])
LFSR_POLY_23 = LFSRPolynomial([23, 18, 0])
LFSR_POLY_24 = LFSRPolynomial([24, 23, 22, 17, 0])


class LFSR(LFSRPolynomial, Elaboratable):
    """ implements a Linear Feedback Shift Register
    """
    def __init__(self, polynomial):
        """ Inputs:
            ------
            :polynomial: the polynomial to feedback on.  may be a LFSRPolynomial
                         instance or an iterable of ints (list/tuple/generator)
            :enable:     enable (set LO to disable.  NOTE: defaults to HI)

            Outputs:
            -------
            :state: the LFSR state.  bitwidth is taken from the polynomial
                    maximum exponent.

            Note: if an LFSRPolynomial is passed in as the input, because
            LFSRPolynomial is derived from set() it's ok:
            LFSRPolynomial(LFSRPolynomial(p)) == LFSRPolynomial(p)
        """
        LFSRPolynomial.__init__(self, polynomial)
        self.state = Signal(self.max_exponent, reset=1)
        self.enable = Signal(reset=1)

    def elaborate(self, platform):
        m = Module()
        # do absolutely nothing if the polynomial is empty (always has a zero)
        if self.max_exponent <= 1:
            return m

        # create XOR-bunch, select bits from state based on exponent
        feedback = Const(0) # doesn't do any harm starting from 0b0 (xor chain)
        for exponent in self:
            if exponent > 0: # don't have to skip, saves CPU cycles though
                feedback ^= self.state[exponent - 1]

        # if enabled, shift-and-feedback
        with m.If(self.enable):
            # shift up lower bits by Cat'ing in a new bit zero (feedback)
            newstate = Cat(feedback, self.state[:-1])
            m.d.sync += self.state.eq(newstate)

        return m


# example: Poly24
if __name__ == '__main__':
    p24 = rtlil.convert(LFSR(LFSR_POLY_24))
    with open("lfsr2_p24.il", "w") as f:
        f.write(p24)
