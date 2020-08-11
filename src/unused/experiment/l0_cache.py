class DualPortSplitter(Elaboratable):
    """DualPortSplitter

    * one incoming PortInterface
    * two *OUTGOING* PortInterfaces
    * uses LDSTSplitter to do it

    (actually, thinking about it LDSTSplitter could simply be
     modified to conform to PortInterface: one in, two out)

    once that is done each pair of ports may be wired directly
    to the dual ports of L0CacheBuffer

    The split is carried out so that, regardless of alignment or
    mis-alignment, outgoing PortInterface[0] takes bit 4 == 0
    of the address, whilst outgoing PortInterface[1] takes
    bit 4 == 1.

    PortInterface *may* need to be changed so that the length is
    a binary number (accepting values 1-16).
    """

    def __init__(self,inp):
        self.outp = [PortInterface(name="outp_0"),
                     PortInterface(name="outp_1")]
        print(self.outp)

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        m.submodules.splitter = splitter = LDSTSplitter(64, 48, 4)
        self.inp = splitter.pi
        comb += splitter.addr_i.eq(self.inp.addr)  # XXX
        #comb += splitter.len_i.eq()
        #comb += splitter.valid_i.eq()
        comb += splitter.is_ld_i.eq(self.inp.is_ld_i)
        comb += splitter.is_st_i.eq(self.inp.is_st_i)
        #comb += splitter.st_data_i.eq()
        #comb += splitter.sld_valid_i.eq()
        #comb += splitter.sld_data_i.eq()
        #comb += splitter.sst_valid_i.eq()
        return m
