# TODO: replace with Memory at some point
from nmigen import Elaboratable, Signal, Array, Module

class CacheRam(Elaboratable):

    def __init__(self, ROW_BITS=16, WIDTH = 64, TRACE=False, ADD_BUF=False):
        self.ROW_BITS = ROW_BITS
        self.WIDTH = WIDTH
        self.TRACE = TRACE
        self.ADD_BUF = ADD_BUF
        self.rd_en     = Signal()
        self.rd_addr   = Signal(ROW_BITS)
        self.rd_data_o = Signal(WIDTH)
        self.wr_sel    = Signal(WIDTH//8)
        self.wr_addr   = Signal(ROW_BITS)
        self.wr_data   = Signal(WIDTH)
 
    def elaborate(self, platform):
        m = Module()
        comb, sync = m.d.comb, m.d.sync

        ROW_BITS = self.ROW_BITS
        WIDTH = self.WIDTH
        TRACE = self.TRACE
        ADD_BUF = self.ADD_BUF
        SIZE = 2**ROW_BITS
     
        ram = Array(Signal(WIDTH) for i in range(SIZE))
        #attribute ram_style of ram : signal is "block";
     
        rd_data0 = Signal(WIDTH)
     
        sel0 = Signal(WIDTH//8) # defaults to zero

        with m.If(TRACE):
            with m.If(self.wr_sel != sel0):
                #Display( "write a:" & to_hstring(wr_addr) &
                #    " sel:" & to_hstring(wr_sel) &
                #    " dat:" & to_hstring(wr_data))
               pass
        for i in range(WIDTH//8):
            lbit = i * 8;
            mbit = lbit + 8;
            with m.If(self.wr_sel[i]):
                sync += ram[self.wr_addr][lbit:mbit].eq(self.wr_data[lbit:mbit])
        with m.If(self.rd_en):
            if ADD_BUF:
                sync += self.rd_data_o.eq(ram[self.rd_addr])
            else:
                comb += self.rd_data_o.eq(ram[self.rd_addr])

        if TRACE:
            # Display( "read a:" & to_hstring(rd_addr) &
            #" dat:" & to_hstring(ram(to_integer(unsigned(rd_addr))));
            pass

        return m
