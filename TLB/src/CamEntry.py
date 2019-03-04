from nmigen import Module, Signal

class CamEntry:
    """ Content Addressable Memory (CAM) Entry

        The purpose of this module is to represent an entry within a CAM.
        This module when given a read command will compare  the given key
        and output whether a match was found or not. When given a write
        command it will write the given key and data into internal registers.
    """

    def __init__(self, key_size, data_size):
        """ Arguments:
            * key_size: (bit count) The size of the key
            * data_size: (bit count) The size of the data
        """
        # Internal
        self.key = Signal(key_size)

        # Input
        self.command = Signal(2) # 00 => NA 01 => Read 10 => Write 11 => Reset
        self.key_in = Signal(key_size) # Reference key for the CAM
        self.data_in = Signal(data_size) # Data input when writing

        # Output
        self.match = Signal(1) # Result of the internal/input key comparison
        self.data = Signal(data_size)

    def elaborate(self, platform=None):
        m = Module()
        with m.Switch(self.command):
            with m.Case("00"):
                m.d.sync += self.match.eq(0)
            with m.Case("01"):
                with m.If(self.key_in == self.key):
                    m.d.sync += self.match.eq(1)
                with m.Else():
                    m.d.sync += self.match.eq(0)
            with m.Case("10"):
                m.d.sync += [
                    self.key.eq(self.key_in),
                    self.data.eq(self.data_in),
                    self.match.eq(0)
                ]
            with m.Case():
                m.d.sync += [
                    self.match.eq(0),
                    self.data.eq(0),
                    self.key.eq(0)
                ]

        return m
