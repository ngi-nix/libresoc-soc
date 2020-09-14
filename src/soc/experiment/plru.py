# based on microwatt plru.vhdl

from nmigen import Elaboratable, Signal, Array, Module
from nmigen.cli import rtlil


class PLRU(Elaboratable):

    def __init__(self, BITS=2):
        self.BITS = BITS
        self.acc_i = Signal(BITS)
        self.acc_en = Signal()
        self.lru_o = Signal(BITS)

    def elaborate(self, platform):
        m = Module()
        comb, sync = m.d.comb, m.d.sync

        tree = Array(Signal(name="tree%d" % i) for i in range(self.BITS))

        # XXX Check if we can turn that into a little ROM instead that
        # takes the tree bit vector and returns the LRU. See if it's better
        # in term of FPGA resouces usage...
        node = Signal(self.BITS)
        for i in range(self.BITS):
            node_next = Signal(self.BITS)
            node2 = Signal(self.BITS)
            # report "GET: i:" & integer'image(i) & " node:" & 
            # integer'image(node) & " val:" & Signal()'image(tree(node))
            comb += self.lru_o[self.BITS-1-i].eq(tree[node])
            if i != self.BITS-1:
                comb += node2.eq(node << 1)
                with m.If(tree[node2]):
                    comb += node_next.eq(node2 + 2)
                with m.Else():
                    comb += node_next.eq(node2 + 1)
                node = node_next

        with m.If(self.acc_en):
            node = Signal(self.BITS)
            for i in range(self.BITS):
                node_next = Signal(self.BITS)
                node2 = Signal(self.BITS)
                # report "GET: i:" & integer'image(i) & " node:" & 
                # integer'image(node) & " val:" & Signal()'image(tree(node))
                abit = self.acc_i[self.BITS-1-i]
                sync += tree[node].eq(~abit)
                if i != self.BITS-1:
                    comb += node2.eq(node << 1)
                    with m.If(abit):
                        comb += node_next.eq(node2 + 2)
                    with m.Else():
                        comb += node_next.eq(node2 + 1)
                    node = node_next

        return m

    def ports(self):
        return [self.acc_en, self.lru_o, self.acc_i]

if __name__ == '__main__':
    dut = PLRU(3)
    vl = rtlil.convert(dut, ports=dut.ports())
    with open("test_plru.il", "w") as f:
        f.write(vl)


