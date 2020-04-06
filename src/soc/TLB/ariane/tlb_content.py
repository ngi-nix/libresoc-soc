from nmigen import Signal, Module, Cat, Const, Elaboratable

from soc.TLB.ariane.ptw import TLBUpdate, PTE


class TLBEntry:
    def __init__(self, asid_width):
        self.asid = Signal(asid_width, name="ent_asid")
        # SV48 defines four levels of page tables
        self.vpn0 = Signal(9, name="ent_vpn0")
        self.vpn1 = Signal(9, name="ent_vpn1")
        self.vpn2 = Signal(9, name="ent_vpn2")
        self.vpn3 = Signal(9, name="ent_vpn3")
        self.is_2M = Signal(name="ent_is_2M")
        self.is_1G = Signal(name="ent_is_1G")
        self.is_512G = Signal(name="ent_is_512G")
        self.valid = Signal(name="ent_valid")

    def flatten(self):
        return Cat(*self.ports())

    def eq(self, x):
        return self.flatten().eq(x.flatten())

    def ports(self):
        return [self.asid, self.vpn0, self.vpn1, self.vpn2,
                self.is_2M, self.is_1G, self.valid]


class TLBContent(Elaboratable):
    def __init__(self, pte_width, asid_width):
        self.asid_width = asid_width
        self.pte_width = pte_width
        self.flush_i = Signal()  # Flush signal
        # Update TLB
        self.update_i = TLBUpdate(asid_width)
        self.vpn3 = Signal(9)
        self.vpn2 = Signal(9)
        self.vpn1 = Signal(9)
        self.vpn0 = Signal(9)
        self.replace_en_i = Signal()  # replace the following entry,
        # set by replacement strategy
        # Lookup signals
        self.lu_asid_i = Signal(asid_width)
        self.lu_content_o = Signal(pte_width)
        self.lu_is_512G_o = Signal()
        self.lu_is_2M_o = Signal()
        self.lu_is_1G_o = Signal()
        self.lu_hit_o = Signal()

    def elaborate(self, platform):
        m = Module()

        tags = TLBEntry(self.asid_width)

        content = Signal(self.pte_width)

        m.d.comb += [self.lu_hit_o.eq(0),
                     self.lu_is_512G_o.eq(0),
                     self.lu_is_2M_o.eq(0),
                     self.lu_is_1G_o.eq(0)]

        # temporaries for lookup
        asid_ok = Signal(reset_less=True)
        # tags_ok = Signal(reset_less=True)

        vpn3_ok = Signal(reset_less=True)
        vpn2_ok = Signal(reset_less=True)
        vpn1_ok = Signal(reset_less=True)
        vpn0_ok = Signal(reset_less=True)

        #tags_2M = Signal(reset_less=True)
        vpn0_or_2M = Signal(reset_less=True)

        m.d.comb += [
            # compare asid and vpn*
            asid_ok.eq(tags.asid == self.lu_asid_i),
            vpn3_ok.eq(tags.vpn3 == self.vpn3),
            vpn2_ok.eq(tags.vpn2 == self.vpn2),
            vpn1_ok.eq(tags.vpn1 == self.vpn1),
            vpn0_ok.eq(tags.vpn0 == self.vpn0),
            vpn0_or_2M.eq(tags.is_2M | vpn0_ok)
        ]

        with m.If(asid_ok & tags.valid):
            # first level, only vpn3 needs to match
            with m.If(tags.is_512G & vpn3_ok):
                m.d.comb += [self.lu_content_o.eq(content),
                             self.lu_is_512G_o.eq(1),
                             self.lu_hit_o.eq(1),
                             ]
            # second level , second level vpn2 and vpn3 need to match
            with m.Elif(tags.is_1G & vpn2_ok & vpn3_ok):
                m.d.comb += [self.lu_content_o.eq(content),
                             self.lu_is_1G_o.eq(1),
                             self.lu_hit_o.eq(1),
                             ]
            # not a giga page hit nor a tera page hit so check further
            with m.Elif(vpn1_ok):
                # this could be a 2 mega page hit or a 4 kB hit
                # output accordingly
                with m.If(vpn0_or_2M):
                    m.d.comb += [self.lu_content_o.eq(content),
                                 self.lu_is_2M_o.eq(tags.is_2M),
                                 self.lu_hit_o.eq(1),
                                 ]
        # ------------------
        # Update or Flush
        # ------------------

        # temporaries
        replace_valid = Signal(reset_less=True)
        m.d.comb += replace_valid.eq(self.update_i.valid & self.replace_en_i)

        # flush
        with m.If(self.flush_i):
            # invalidate (flush) conditions: all if zero or just this ASID
            with m.If(self.lu_asid_i == Const(0, self.asid_width) |
                      (self.lu_asid_i == tags.asid)):
                m.d.sync += tags.valid.eq(0)

        # normal replacement
        with m.Elif(replace_valid):
            m.d.sync += [  # update tag array
                tags.asid.eq(self.update_i.asid),
                tags.vpn3.eq(self.update_i.vpn[27:36]),
                tags.vpn2.eq(self.update_i.vpn[18:27]),
                tags.vpn1.eq(self.update_i.vpn[9:18]),
                tags.vpn0.eq(self.update_i.vpn[0:9]),
                tags.is_512G.eq(self.update_i.is_512G),
                tags.is_1G.eq(self.update_i.is_1G),
                tags.is_2M.eq(self.update_i.is_2M),
                tags.valid.eq(1),
                # and content as well
                content.eq(self.update_i.content.flatten())
            ]
        return m

    def ports(self):
        return [self.flush_i,
                self.lu_asid_i,
                self.lu_is_2M_o, self.lu_is_1G_o, self.lu_is_512G_o, self.lu_hit_o,
                ] + self.update_i.content.ports() + self.update_i.ports()
