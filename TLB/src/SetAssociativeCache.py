from nmigen import Array, Memory, Module, Signal
from nmigen.compat.genlib import fsm
from nmigen.cli import main

from AddressEncoder import AddressEncoder

SA_NA = "00" # no action (none)
SA_RD = "01" # read
SA_WR = "10" # write


class SetAssociativeCache():
    """ Set Associative Cache Memory

        The purpose of this module is to generate a memory cache given the
        constraints passed in. This will create a n-way set associative cache.
        It is expected for the SV TLB that the VMA will provide the set number
        while the ASID provides the tag (still to be decided).

    """
    def __init__(self, tag_size, data_size, set_count, way_count):
        """ Arguments
            * tag_size (bits): The bit count of the tag
            * data_size (bits): The bit count of the data to be stored
            * set_count (number): The number of sets/entries in the cache
            * way_count (number): The number of slots a data can be stored
                                  in one set
        """
        # Internals
        self.active = 0
        self.lru_start = self.active + 1
        self.lru_end = self.lru_start + way_count.bit_length()
        self.data_start = self.lru_end
        self.data_end = self.data_start + data_size
        self.tag_start = self.data_end
        self.tag_end = self.tag_start + tag_size
        cache_data = way_count + 1 # Bits required to represent LRU and active
        input_size = tag_size + data_size # Size of the input data
        memory_width = input_size + cache_data # The width of the cache memory
        memory_array = Array(Memory(memory_width, entry_count)) # Memory Array
        self.read_port_array = Array()  # Read port array from Memory Array
        self.write_port_array = Array() # Write port array from Memory Array
        # Populate read/write port arrays
        for i in range(way_count):
            mem = memory_array[i] # Memory being parsed
            self.read_port_array.append(mem.read_port()) # Store read port
            self.write_port_array.append(mem.write_port()) # Store write port

        self.way_count = way_count # The number of slots in one set
        self.tag_size = tag_size  # The bit count of the tag
        self.data_size = data_size  # The bit count of the data to be stored

        self.encoder = AddressEncoder(max=way_count) # Finds valid entries

        # Input
        self.enable = Signal(1) # Whether the cache is enabled
        self.command = Signal(2)  # 00=None, 01=Read, 10=Write (see SA_XX)
        self.cset = Signal(max=set_count) # The set to be checked
        self.tag = Signal(tag_size) # The tag to find
        self.data_i = Signal(data_size + tag_size) # The input data

        # Output
        self.ready = Signal(1) # 0 => Processing 1 => Ready for commands
        self.hit = Signal(1) # Tag matched one way in the given set
        self.multiple_hit = Signal(1) # Tag matched many ways in the given set
        self.data_o = Signal(data_size) # The data linked to the matched tag

    def check_tags(self, m):
        """
        Validate the tags in the selected set. If one and only one tag matches
        set its state to zero and increment all others by one. We only advance
        to the next state if a single hit is found.
        """
        # Vector to store way valid results
        # A zero denotes a way is invalid
        valid_vector = []
        # Loop through memory to prep read/write ports and set valid_vector
        # value
        for i in range(self.way_count):
            m.d.comb += [
                self.write_port_array[i].addr.eq(self.cset),
                self.read_port_array[i].addr.eq(self.cset)
            ]
            # Pull out active bit from data
            data = self.read_port_array[i].data;
            active_bit = data[self.active];
            # Validate given tag vs stored tag
            tag = data[self.tag_start:self.tag_end]
            tag_valid = self.tag == tag
            # An entry is only valid if the tags match AND
            # is marked as a valid entry
            valid_vector.append(tag_valid & valid_bit)

        # Pass encoder the valid vector
        self.encoder.i.eq(Cat(*valid_vector))
        # Only one entry should be marked
        # This is due to already verifying the tags
        # matched and the valid bit is high
        with m.If(self.encoder.single_match):
            m.next = "FINISHED"
            # Pull out data from the read port
            read_port = self.read_port_array[self.encoder.o]
            data = read_port.data[self.data_start:self.data_end]
            m.d.comb += [
                self.hit.eq(1),
                self.multiple_hit.eq(0),
                self.data_o.eq(data)
            ]
            self.update_set(m)
        # Oh no! Seal the gates! Multiple tags matched?!? kasd;ljkafdsj;k
        with m.Elif(self.encoder.multiple_match):
            m.d.comb += [
                self.hit.eq(0),
                self.multiple_hit.eq(1),
                self.data_o.eq(0)
            ]
        # No tag matches means no data
        with m.Else():
            m.d.comb += [
                self.hit.eq(0),
                self.multiple_hit.eq(0),
                self.data_o.eq(0)
            ]

    def update_set(self, m):
        """
        Update the LRU values for each way in the given set if the entry is
        active.
        """
        # Go through all ways in the set
        for i in range(self.way_count):
            # Pull out read port for readability
            read_port = self.read_port_array[i]
            with m.If(read_port.data[0]):
                # Pull out lru state for readability
                lru_state = read_port.data[self.data_start:self.data_end]
                # Pull out write port for readability
                write_port = self.write_port_array[i]
                # Enable write for the memory block
                m.d.comb += write_port.en.eq(1)
                with m.If(i == self.encoder.o):
                    m.d.comb += write_port.data.eq(0)
                with m.Elif(state < self.way_count):
                    m.d.comb += write_port.data.eq(state + 1)
                with m.Else():
                    m.d.comb += write_port.data.eq(state)

    def read(self, m):
        """
        Go through the read process of the cache.
        This takes two cycles to complete. First it checks for a valid tag
        and secondly it updates the LRU values.
        """
        with m.FSM() as fsm:
            with m.State("SEARCH"):
                m.d.comb += self.ready.eq(0)
                # check_tags will set the state if the conditions are met
                self.check_tags(m)
            with m.State("FINISHED"):
                m.next = "SEARCH"
                m.d.comb += self.ready.eq(1)

    def elaborate(self, platform=None):
        m = Module()
        m.submodules += self.read_port_array
        m.submodules += self.write_port_array

        with m.If(self.enable):
            with m.Switch(self.command):
                # Search all sets at a particular tag
                with m.Case(SA_RD):
                    self.read(m)
                # TODO
                # Write to a given tag
                # with m.Case(SA_WR):
                    # Search for available space
                    # What to do when there is no space
                    # Maybe catch multiple tags write here?
                    # TODO
        return m
