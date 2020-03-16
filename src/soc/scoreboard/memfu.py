from nmigen.compat.sim import run_simulation
from nmigen.cli import verilog, rtlil
from nmigen import Module, Signal, Array, Elaboratable

from soc.scoreboard.fu_fu_matrix import FUFUDepMatrix
from soc.scoreboard.mdm import FUMemMatchMatrix


class MemFunctionUnits(Elaboratable):

    def __init__(self, n_ldsts, addrbitwid):
        self.n_ldsts = n_ldsts
        self.bitwid = addrbitwid

        self.st_i = Signal(n_ldsts, reset_less=True) # Dest R# in
        self.ld_i = Signal(n_ldsts, reset_less=True) # oper1 R# in

        self.g_int_ld_pend_o = Signal(n_ldsts, reset_less=True)
        self.g_int_st_pend_o = Signal(n_ldsts, reset_less=True)

        self.st_rsel_o = Signal(n_ldsts, reset_less=True) # dest reg (bot)
        self.ld_rsel_o = Signal(n_ldsts, reset_less=True) # src1 reg (bot)

        self.loadable_o = Signal(n_ldsts, reset_less=True)
        self.storable_o = Signal(n_ldsts, reset_less=True)
        self.addr_nomatch_o = Signal(n_ldsts, reset_less=True)

        self.go_ld_i = Signal(n_ldsts, reset_less=True)
        self.go_st_i = Signal(n_ldsts, reset_less=True)
        self.go_die_i = Signal(n_ldsts, reset_less=True)
        self.fn_issue_i = Signal(n_ldsts, reset_less=True)

        # address matching
        self.addrs_i = Array(Signal(self.bitwid, name="addrs_i%d" % i) \
                             for i in range(n_ldsts))
        #self.addr_we_i = Signal(n_ldsts) # write-enable for incoming address
        self.addr_en_i = Signal(n_ldsts) # address latched in
        self.addr_rs_i = Signal(n_ldsts) # address deactivated

        # Note: FURegs st_pend_o is also outputted from here, for use in WaWGrid

    def elaborate(self, platform):
        m = Module()
        comb = m.d.comb
        sync = m.d.sync

        n_fus = self.n_ldsts

        # Integer FU-FU Dep Matrix
        intfudeps = FUFUDepMatrix(n_fus, n_fus)
        m.submodules.intfudeps = intfudeps
        # Integer FU-Reg Dep Matrix
        intregdeps = FUMemMatchMatrix(n_fus, self.bitwid)
        m.submodules.intregdeps = intregdeps

        # ok, because we do not know in advance what the AGEN (address gen)
        # is, we have to make a transitive dependency set.  i.e. the LD
        # (or ST) being requested now must depend on ALL prior LDs *AND* STs.
        # these get dropped very rapidly once AGEN is carried out.
        # XXX TODO

        # connect fureg matrix as a mem system
        comb += self.g_int_ld_pend_o.eq(intregdeps.v_rd_rsel_o)
        comb += self.g_int_st_pend_o.eq(intregdeps.v_wr_rsel_o)

        comb += intregdeps.rd_pend_i.eq(intregdeps.v_rd_rsel_o)
        comb += intregdeps.wr_pend_i.eq(intregdeps.v_wr_rsel_o)

        comb += intfudeps.rd_pend_i.eq(intregdeps.rd_pend_o)
        comb += intfudeps.wr_pend_i.eq(intregdeps.wr_pend_o)
        self.st_pend_o = intregdeps.wr_pend_o # also output for use in WaWGrid

        comb += intfudeps.issue_i.eq(self.fn_issue_i)
        comb += intfudeps.go_rd_i.eq(self.go_ld_i)
        comb += intfudeps.go_wr_i.eq(self.go_st_i)
        comb += intfudeps.go_die_i.eq(self.go_die_i)
        comb += self.loadable_o.eq(intfudeps.readable_o)
        comb += self.storable_o.eq(intfudeps.writable_o)
        comb += self.addr_nomatch_o.eq(intregdeps.addr_nomatch_o)

        # Connect function issue / arrays, and dest/src1/src2
        comb += intregdeps.dest_i.eq(self.st_i)
        comb += intregdeps.src_i[0].eq(self.ld_i)

        comb += intregdeps.go_rd_i.eq(self.go_ld_i)
        comb += intregdeps.go_wr_i.eq(self.go_st_i)
        comb += intregdeps.go_die_i.eq(self.go_die_i)
        comb += intregdeps.issue_i.eq(self.fn_issue_i)

        comb += self.st_rsel_o.eq(intregdeps.dest_rsel_o)
        comb += self.ld_rsel_o.eq(intregdeps.src_rsel_o[0])

        # connect address matching: these get connected to the Addr CUs
        for i in range(self.n_ldsts):
            comb += intregdeps.addrs_i[i].eq(self.addrs_i[i])
        #comb += intregdeps.addr_we_i.eq(self.addr_we_i)
        comb += intregdeps.addr_en_i.eq(self.addr_en_i)
        comb += intregdeps.addr_rs_i.eq(self.addr_rs_i)

        return m

    def __iter__(self):
        yield self.ld_i
        yield self.st_i
        yield self.g_int_st_pend_o
        yield self.g_int_ld_pend_o
        yield self.ld_rsel_o
        yield self.st_rsel_o
        yield self.loadable_o
        yield self.storable_o
        yield self.go_st_i
        yield self.go_ld_i
        yield self.go_die_i
        yield self.fn_issue_i
        yield from self.addrs_i
        #yield self.addr_we_i
        yield self.addr_en_i

    def ports(self):
        return list(self)
