from nmutil.iocontrol import RecordObject
from nmigen import Signal
from soc.sv.svstate import SVSTATERec


class CoreState(RecordObject):
    """contains "Core State Information" which says exactly where things are

    example: eint says to PowerDecoder that it should fire an exception
    rather than let the current decoded instruction proceed.  likewise
    if dec goes negative.  MSR contains LE/BE and Priv state.  PC contains
    the Program Counter, and SVSTATE is the Sub-Program-Counter.
    """
    def __init__(self, name):
        super().__init__(name=name)
        self.pc = Signal(64)      # Program Counter (CIA, NIA)
        self.msr = Signal(64)     # Machine Status Register (MSR)
        self.eint = Signal()      # External Interrupt
        self.dec = Signal(64)     # DEC SPR (again, for interrupt generation)
        self.svstate = SVSTATERec(name) # Simple-V SVSTATE
