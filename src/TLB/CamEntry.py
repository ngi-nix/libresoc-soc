from nmigen import Module, Signal, Elaboratable


class CamEntry(Elaboratable):
    """ Content Addressable Memory (CAM) Entry

        The purpose of this module is to represent an entry within a CAM.
        This module when given a read command will compare  the given data
        and output whether a match was found or not. When given a write
        command it will write the given data into internal registers.
    """

    def __init__(self, data_size):
        """ Arguments:
            * data_size: (bit count) The size of the data
        """
        # Input
        self.command = Signal(2) # 00 => NA 01 => Read 10 => Write 11 => Reset
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
                with m.If(self.data == self.data_in):
                    m.d.sync += self.match.eq(1)
                with m.Else():
                    m.d.sync += self.match.eq(0)
            with m.Case("10"):
                m.d.sync += [
                    self.data.eq(self.data_in),
                    self.match.eq(0)
                ]
            with m.Case():
                m.d.sync += [
                    self.match.eq(0),
                    self.data.eq(0)
                ]

        return m
