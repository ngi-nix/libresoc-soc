"""

Online simulator of 4-way set-associative cache:
http://www.ntu.edu.sg/home/smitha/ParaCache/Paracache/sa4.html

Python simulator of a N-way set-associative cache:
https://github.com/vaskevich/CacheSim/blob/master/cachesim.py
"""

from nmigen import Array, Cat, Memory, Module, Signal, Mux, Elaboratable
from nmigen.compat.genlib import fsm
from nmigen.cli import main
from nmigen.cli import verilog, rtlil

from .AddressEncoder import AddressEncoder
from .MemorySet import MemorySet

# TODO: use a LFSR that advances continuously and picking the bottom
# few bits from it to select which cache line to replace, instead of PLRU
# http://bugs.libre-riscv.org/show_bug.cgi?id=71
from .ariane.plru import PLRU
from .LFSR import LFSR, LFSR_POLY_24

SA_NA = "00"  # no action (none)
SA_RD = "01"  # read
SA_WR = "10"  # write


class SetAssociativeCache(Elaboratable):
    """ Set Associative Cache Memory

        The purpose of this module is to generate a memory cache given the
        constraints passed in. This will create a n-way set associative cache.
        It is expected for the SV TLB that the VMA will provide the set number
        while the ASID provides the tag (still to be decided).

    """

    def __init__(self, tag_size, data_size, set_count, way_count, lfsr=False):
        """ Arguments
            * tag_size (bits): The bit count of the tag
            * data_size (bits): The bit count of the data to be stored
            * set_count (number): The number of sets/entries in the cache
            * way_count (number): The number of slots a data can be stored
                                  in one set
            * lfsr: if set, use an LFSR for (pseudo-randomly) selecting
                    set/entry to write to.  otherwise, use a PLRU
        """
        # Internals
        self.lfsr_mode = lfsr
        self.way_count = way_count  # The number of slots in one set
        self.tag_size = tag_size    # The bit count of the tag
        self.data_size = data_size  # The bit count of the data to be stored

        # set up Memory array
        self.mem_array = Array()  # memory array
        for i in range(way_count):
            ms = MemorySet(data_size, tag_size, set_count, active=0)
            self.mem_array.append(ms)

        # Finds valid entries
        self.encoder = AddressEncoder(way_count)

        # setup PLRU or LFSR
        if lfsr:
            # LFSR mode
            self.lfsr = LFSR(LFSR_POLY_24)
        else:
            # PLRU mode
            # One block to handle plru calculations
            self.plru = PLRU(way_count)
            self.plru_array = Array()  # PLRU data on each set
            for i in range(set_count):
                name = "plru%d" % i
                self.plru_array.append(Signal(self.plru.TLBSZ, name=name))

        # Input
        self.enable = Signal(1)   # Whether the cache is enabled
        self.command = Signal(2)  # 00=None, 01=Read, 10=Write (see SA_XX)
        self.cset = Signal(range(set_count))  # The set to be checked
        self.tag = Signal(tag_size)        # The tag to find
        self.data_i = Signal(data_size)    # The input data

        # Output
        self.ready = Signal(1)  # 0 => Processing 1 => Ready for commands
        self.hit = Signal(1)            # Tag matched one way in the given set
        # Tag matched many ways in the given set
        self.multiple_hit = Signal(1)
        self.data_o = Signal(data_size)  # The data linked to the matched tag

    def check_tags(self, m):
        """ Validate the tags in the selected set. If one and only one
            tag matches set its state to zero and increment all others
            by one. We only advance to next state if a single hit is found.
        """
        # Vector to store way valid results
        # A zero denotes a way is invalid
        valid_vector = []
        # Loop through memory to prep read/write ports and set valid_vector
        for i in range(self.way_count):
            valid_vector.append(self.mem_array[i].valid)

        # Pass encoder the valid vector
        m.d.comb += self.encoder.i.eq(Cat(*valid_vector))

        # Only one entry should be marked
        # This is due to already verifying the tags
        # matched and the valid bit is high
        with m.If(self.hit):
            m.next = "FINISHED_READ"
            # Pull out data from the read port
            data = self.mem_array[self.encoder.o].data_o
            m.d.comb += self.data_o.eq(data)
            if not self.lfsr_mode:
                self.access_plru(m)

        # Oh no! Seal the gates! Multiple tags matched?!? kasd;ljkafdsj;k
        with m.Elif(self.multiple_hit):
            # XXX TODO, m.next = "FINISHED_READ" ? otherwise stuck
            m.d.comb += self.data_o.eq(0)

        # No tag matches means no data
        with m.Else():
            # XXX TODO, m.next = "FINISHED_READ" ? otherwise stuck
            m.d.comb += self.data_o.eq(0)

    def access_plru(self, m):
        """ An entry was accessed and the plru tree must now be updated
        """
        # Pull out the set's entry being edited
        plru_entry = self.plru_array[self.cset]
        m.d.comb += [
            # Set the plru data to the current state
            self.plru.plru_tree.eq(plru_entry),
            # Set that the cache was accessed
            self.plru.lu_access_i.eq(1)
        ]

    def read(self, m):
        """ Go through the read process of the cache.
            This takes two cycles to complete. First it checks for a valid tag
            and secondly it updates the LRU values.
        """
        with m.FSM() as fsm_read:
            with m.State("READY"):
                m.d.comb += self.ready.eq(0)
                # check_tags will set the state if the conditions are met
                self.check_tags(m)
            with m.State("FINISHED_READ"):
                m.next = "READY"
                m.d.comb += self.ready.eq(1)
                if not self.lfsr_mode:
                    plru_tree_o = self.plru.plru_tree_o
                    m.d.sync += self.plru_array[self.cset].eq(plru_tree_o)

    def write_entry(self, m):
        if not self.lfsr_mode:
            m.d.comb += [  # set cset (mem address) into PLRU
                self.plru.plru_tree.eq(self.plru_array[self.cset]),
                # and connect plru to encoder for write
                self.encoder.i.eq(self.plru.replace_en_o)
            ]
            write_port = self.mem_array[self.encoder.o].w
        else:
            # use the LFSR to generate a random(ish) one of the mem array
            lfsr_output = Signal(range(self.way_count))
            lfsr_random = Signal(range(self.way_count))
            m.d.comb += lfsr_output.eq(self.lfsr.state)  # lose some bits
            # address too big, limit to range of array
            m.d.comb += lfsr_random.eq(Mux(lfsr_output > self.way_count,
                                           lfsr_output - self.way_count,
                                           lfsr_output))
            write_port = self.mem_array[lfsr_random].w

        # then if there is a match from the encoder, enable the selected write
        with m.If(self.encoder.single_match):
            m.d.comb += write_port.en.eq(1)

    def write(self, m):
        """ Go through the write process of the cache.
            This takes two cycles to complete. First it writes the entry,
            and secondly it updates the PLRU (in plru mode)
        """
        with m.FSM() as fsm_write:
            with m.State("READY"):
                m.d.comb += self.ready.eq(0)
                self.write_entry(m)
                m.next = "FINISHED_WRITE"
            with m.State("FINISHED_WRITE"):
                m.d.comb += self.ready.eq(1)
                if not self.lfsr_mode:
                    plru_entry = self.plru_array[self.cset]
                    m.d.sync += plru_entry.eq(self.plru.plru_tree_o)
                m.next = "READY"

    def elaborate(self, platform=None):
        m = Module()

        # ----
        # set up Modules: AddressEncoder, LFSR/PLRU, Mem Array
        # ----

        m.submodules.AddressEncoder = self.encoder
        if self.lfsr_mode:
            m.submodules.LFSR = self.lfsr
        else:
            m.submodules.PLRU = self.plru

        for i, mem in enumerate(self.mem_array):
            setattr(m.submodules, "mem%d" % i, mem)

        # ----
        # select mode: PLRU connect to encoder, LFSR do... something
        # ----

        if not self.lfsr_mode:
            # Set what entry was hit
            m.d.comb += self.plru.lu_hit.eq(self.encoder.o)
        else:
            # enable LFSR
            m.d.comb += self.lfsr.enable.eq(self.enable)

        # ----
        # connect hit/multiple hit to encoder output
        # ----

        m.d.comb += [
            self.hit.eq(self.encoder.single_match),
            self.multiple_hit.eq(self.encoder.multiple_match),
        ]

        # ----
        # connect incoming data/tag/cset(addr) to mem_array
        # ----

        for mem in self.mem_array:
            write_port = mem.w
            m.d.comb += [mem.cset.eq(self.cset),
                         mem.tag.eq(self.tag),
                         mem.data_i.eq(self.data_i),
                         write_port.en.eq(0),  # default: disable write
                         ]
        # ----
        # Commands: READ/WRITE/TODO
        # ----

        with m.If(self.enable):
            with m.Switch(self.command):
                # Search all sets at a particular tag
                with m.Case(SA_RD):
                    self.read(m)
                with m.Case(SA_WR):
                    self.write(m)
                    # Maybe catch multiple tags write here?
                    # TODO
                # TODO: invalidate/flush, flush-all?

        return m

    def ports(self):
        return [self.enable, self.command, self.cset, self.tag, self.data_i,
                self.ready, self.hit, self.multiple_hit, self.data_o]


if __name__ == '__main__':
    sac = SetAssociativeCache(4, 8, 4, 6)
    vl = rtlil.convert(sac, ports=sac.ports())
    with open("SetAssociativeCache.il", "w") as f:
        f.write(vl)

    sac_lfsr = SetAssociativeCache(4, 8, 4, 6, True)
    vl = rtlil.convert(sac_lfsr, ports=sac_lfsr.ports())
    with open("SetAssociativeCacheLFSR.il", "w") as f:
        f.write(vl)
