# Proof of correctness for bit permute module
# Copyright (C) 2020 Michael Nolan <mtnolan2640@gmail.com>

from nmigen import (Module, Signal, Elaboratable, Mux, Cat, Repl,
                    signed)
from nmigen.asserts import Assert, AnyConst, Assume, Cover
from nmutil.formaltest import FHDLTestCase
from nmigen.cli import rtlil

from soc.fu.logical.bpermd import Bpermd

import unittest


# So formal verification is a little different than writing a test
# case, as you're actually generating logic around your module to
# check that it behaves a certain way. So here, I'm going to create a
# module to put my formal assertions in
class Driver(Elaboratable):
    def __init__(self):
        # We don't need any inputs and outputs here, so I won't
        # declare any
        pass

    def elaborate(self, platform):
        # standard stuff
        m = Module()
        comb = m.d.comb

        # instantiate the device under test as a submodule
        m.submodules.bperm = bperm = Bpermd(64)

        # Grab the inputs and outputs of the DUT to make them more
        # convenient to access
        rs = bperm.rs
        rb = bperm.rb
        ra = bperm.ra

        # Before we prove any properties about the DUT, we need to set
        # up its inputs. There's a couple ways to do this, you could
        # define some inputs and outputs for the driver module and
        # wire them up to the DUT, but that's kind of a pain. The
        # other option is to use AnyConst/AnySeq, which tells yosys
        # that those inputs can take on any value.

        # AnyConst should be used when the input should take on a
        # random value, but that value should be constant throughout
        # the test.
        # AnySeq should be used when the input can change on every
        # cycle

        # Since this is a combinatorial circuit, it really doesn't
        # matter which one you choose, so I chose AnyConst. If this
        # was a sequential circuit, (especially a state machine) you'd
        # want to use AnySeq
        comb += [rs.eq(AnyConst(64)),
                 rb.eq(AnyConst(64))]

        # The pseudocode in the Power ISA manual (v3.1) is as follows:
        # do i = 0 to 7
        #    index <- RS[8*i:8*i+8]
        #    if index < 64:
        #        perm[i] <- RB[index]
        #    else:
        #        perm[i] <- 0
        # RA <- 56'b0 || perm[0:8]  # big endian though

        # Looking at this, I can identify 3 properties that the bperm
        # module should keep:
        #   1. RA[8:64] should always equal 0
        #   2. If RB[i*8:i*8+8] >= 64 then RA[i] should equal 0
        #   3. If RB[i*8:i*8+8] < 64 then RA[i] should RS[index]

        # Now we need to Assert that the properties above hold:

        # Property 1: RA[8:64] should always equal 0
        comb += Assert(ra[8:] == 0)
        # Notice how we're adding Assert to comb like it's a circuit?
        # That's because it kind of is. If you run this proof and have
        # yosys graph the ilang, you'll be able to see an equals
        # comparison cell feeding into an assert cell

        # Now we need to prove property #2. I'm going to leave this to
        # you Cole. I'd start by writing a for loop and extracting the
        # 8 indices into signals. Then I'd write an if statement
        # checking if the index is >= 64 (it's hardware, so use an
        # m.If()). Finally, I'd add an assert that checks whether
        # ra[i] is equal to 0
        for i in range(8):
            index = rs[i*8:i*8+8]
            with m.If(index >= 64):
                comb += Assert(ra[i] == 0)
            with m.Else():
                # to avoid having to create an Array of rb,
                # cycle through from 0-63 on the index *whistle nonchalantly*
                for j in range(64):
                    with m.If(index == j):
                        comb += Assert(ra[i] == rb[63-j])

        return m


class TestCase(FHDLTestCase):
    # This bit here is actually in charge of running the formal
    # proof. It has nmigen spit out the ilang, and feeds it to
    # SymbiYosys to run the proof. If the proof fails, yosys will
    # generate a .vcd file showing how it was able to violate your
    # assertions in proof_bperm_formal/engine_0/trace.vcd. From that
    # you should be able to figure out what went wrong, and either
    # correct the assertion or fix the DUT
    def test_formal(self):
        module = Driver()
        # This runs a Bounded Model Check on the driver module
        # above. What that does is it starts at some initial state,
        # and steps it through `depth` cycles, checking that the
        # assertions hold at every cycle. Since this is a
        # combinatorial module, it only needs 1 cycle to prove
        # everything.
        self.assertFormal(module, mode="bmc", depth=2)
        self.assertFormal(module, mode="cover", depth=2)

    # As mentioned above, you can look at the graph in yosys and see
    # all the assertion cells
    def test_ilang(self):
        dut = Driver()
        vl = rtlil.convert(dut, ports=[])
        with open("bpermd.il", "w") as f:
            f.write(vl)


if __name__ == '__main__':
    unittest.main()
