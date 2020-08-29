"""mem_types

based on Anton Blanchard microwatt common.vhdl

"""
from nmutil.iocontrol import RecordObject
from nmigen import Signal


class DcacheToLoadStore1Type(RecordObject):
    def __init__(self):
        super().__init__()
        self.valid         = Signal()
        self.data          = Signal()
        self.store_done    = Signal()
        self.error         = Signal()
        self.cache_paradox = Signal()


class DcacheToMmuType(RecordObject):
    def __init__(self):
        super().__init__()
        self.stall         = Signal()
        self.done          = Signal()
        self.err           = Signal()
        self.data          = Signal(64)

class LoadStore1ToDcacheType(RecordObject):
    def __init__(self):
        super().__init__()
        self.valid         = Signal()
        self.load          = Signal() # this is a load
        self.dcbz          = Signal()
        self.nc            = Signal()
        self.nc            = Signal()
        self.reserve       = Signal()
        self.virt_mode     = Signal()
        self.priv_mode     = Signal()
        self.addr          = Signal()
        self.data          = Signal()
        self.byte_sel      = Signal()

class LoadStore1ToMmuType(RecordObject):
    def __init__(self):
        super().__init__()
        self.valid         = Signal()
        self.tlbie         = Signal()
        self.slbia         = Signal()
        self.mtspr         = Signal()
        self.iside         = Signal()
        self.load          = Signal()
        self.priv          = Signal()
        self.sprn          = Signal(10)
        self.addr          = Signal(64)
        self.rs            = Signal(64)

class MmuToLoadStore1Type(RecordObject):
    def __init__(self):
        super().__init__()
        self.done          = Signal()
        self.err           = Signal()
        self.invalid       = Signal()
        self.badtree       = Signal()
        self.segerr        = Signal()
        self.perm_error    = Signal()
        self.rc_error      = Signal()
        self.sprval        = Signal(64)

class MmuToDcacheType(RecordObject):
    def __init__(self):
        super().__init__()
        self.valid         = Signal()
        self.tlbie         = Signal()
        self.doall         = Signal()
        self.tlbld         = Signal()
        self.addr          = Signal(64)
        self.pte           = Signal(64)

class MmuToIcacheType(RecordObject):
    def __init__(self):
        super().__init__()
        self.tlbld         = Signal()
        self.tlbie         = Signal()
        self.doall         = Signal()
        self.addr          = Signal(64)
        self.pte           = Signal(64)

