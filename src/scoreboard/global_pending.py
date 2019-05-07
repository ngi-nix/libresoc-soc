from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Cat, Elaboratable
from nmutil.latch import SRLatch
from nmigen.lib.coding import Decoder


class GlobalPending(Elaboratable):
    """ implements Global Pending Vector, basically ORs all incoming Function
        Unit vectors together.  Can be used for creating Read or Write Global
        Pending.  Can be used for INT or FP Global Pending.

        Inputs:
        * :wid:       register file width
        * :fu_vecs:   a python list of function unit "pending" vectors, each
                      vector being a Signal of width equal to the reg file.

        Notes:

        * the regfile may be Int or FP, this code doesn't care which.
          obviously do not try to put in a mixture of regfiles into fu_vecs.
        * this code also doesn't care if it's used for Read Pending or Write
          pending, it can be used for both: again, obviously, do not try to
          put in a mixture of read *and* write pending vectors in.
        * if some Function Units happen not to be uniform (don't operate
          on a particular register (extremely unusual), they must set a Const
          zero bit in the vector.
    """
    def __init__(self, wid, fu_vecs):
        self.reg_width = wid
        # inputs
        self.fu_vecs = fu_vecs
        for v in fu_vecs:
            assert len(v) == wid, "FU Vector must be same width as regfile"

        self.g_pend_o = Signal(wid, reset_less=True)  # global pending vector

    def elaborate(self, platform):
        m = Module()

        pend_l = []
        for i in range(self.reg_width): # per-register
            vec_bit_l = []
            for v in self.fu_vecs:
                vec_bit_l.append(v[i])             # fu bit for same register
            pend_l.append(Cat(*vec_bit_l).bool())  # OR all bits for same reg
        m.d.comb += self.g_pend_o.eq(Cat(*pend_l)) # merge all OR'd bits

        return m

    def __iter__(self):
        yield from self.fu_vecs
        yield self.g_pend_o

    def ports(self):
        return list(self)


def g_vec_sim(dut):
    yield dut.dest_i.eq(1)
    yield dut.issue_i.eq(1)
    yield
    yield dut.issue_i.eq(0)
    yield
    yield dut.src1_i.eq(1)
    yield dut.issue_i.eq(1)
    yield
    yield
    yield
    yield dut.issue_i.eq(0)
    yield
    yield dut.go_read_i.eq(1)
    yield
    yield dut.go_read_i.eq(0)
    yield
    yield dut.go_write_i.eq(1)
    yield
    yield dut.go_write_i.eq(0)
    yield

def test_g_vec():
    vecs = []
    for i in range(3):
        vecs.append(Signal(32, name="fu%d" % i))
    dut = GlobalPending(32, vecs)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_global_pending.il", "w") as f:
        f.write(vl)

    run_simulation(dut, g_vec_sim(dut), vcd_name='test_global_pending.vcd')

if __name__ == '__main__':
    test_g_vec()
