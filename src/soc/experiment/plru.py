# based on microwatt plru.vhdl

from nmigen import Elaboratable, Signal, Array, Module

class PLRU(Elaboratable):

    def __init__(self, BITS=2):
        self.BITS = BITS
        self.acc = Signal(BITS)
        self.acc_en = Signal()
        self.lru_o = Signal(BITS)

    def elaborate(self, platform):
        m = Module()

        tree = Array(Signal() for i in range(self.BITS))

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
            if i != BITS-1:
                comb += node2.eq(node << 1)
            else:
                comb += node2.eq(node)
            with m.If(tree[node]):
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
                abit = self.acc[self.BITS-1-i]
                sync += tree[node].eq(~abit)
                if i != BITS-1:
                    comb += node2.eq(node << 1)
                else:
                    comb += node2.eq(node)
                with m.If(abit):
                    comb += node_next.eq(node2 + 2)
                with m.Else():
                    comb += node_next.eq(node2 + 1)
                node = node_next

        return m
