from nmutil.iocontrol import RecordObject
from nmigen import Signal
from soc.sv.svstate import SVSTATERec


class CoreState(RecordObject):
    def __init__(self, name):
        super().__init__(name=name)
        self.pc = Signal(64)      # Program Counter (CIA, NIA)
        self.msr = Signal(64)     # Machine Status Register (MSR)
        self.eint = Signal()      # External Interrupt
        self.dec = Signal(64)     # DEC SPR (again, for interrupt generation)
        self.svstate = SVSTATERec(name) # Simple-V SVSTATE
