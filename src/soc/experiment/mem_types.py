"""mem_types

based on Anton Blanchard microwatt common.vhdl

"""
from nmutil.iocontrol import RecordObject
from nmigen import Signal

from openpower.exceptions import LDSTException


class DCacheToLoadStore1Type(RecordObject):
    def __init__(self, name=None):
        super().__init__(name=name)
        self.valid         = Signal()
        self.data          = Signal(64)
        self.store_done    = Signal()
        self.error         = Signal()
        self.cache_paradox = Signal()


class DCacheToMMUType(RecordObject):
    def __init__(self, name=None):
        super().__init__(name=name)
        self.stall         = Signal()
        self.done          = Signal()
        self.err           = Signal()
        self.data          = Signal(64)


class Fetch1ToICacheType(RecordObject):
    def __init__(self, name=None):
        super().__init__(name=name)
        self.req           = Signal()
        self.virt_mode     = Signal()
        self.priv_mode     = Signal()
        self.stop_mark     = Signal()
        self.sequential    = Signal()
        self.nia           = Signal(64)


class ICacheToDecode1Type(RecordObject):
    def __init__(self, name=None):
        super().__init__(name=name)
        self.valid         = Signal()
        self.stop_mark     = Signal()
        self.fetch_failed  = Signal()
        self.nia           = Signal(64)
        self.insn          = Signal(32)


class LoadStore1ToDCacheType(RecordObject):
    def __init__(self, name=None):
        super().__init__(name=name)
        self.valid         = Signal()
        self.hold          = Signal()
        self.load          = Signal() # this is a load
        self.dcbz          = Signal()
        self.nc            = Signal()
        self.reserve       = Signal()
        self.atomic        = Signal() # part of a multi-transfer atomic op
        self.atomic_last   = Signal()
        self.virt_mode     = Signal()
        self.priv_mode     = Signal()
        self.addr          = Signal(64)
        self.data          = Signal(64) # valid the cycle after valid=1
        self.byte_sel      = Signal(8)


class LoadStore1ToMMUType(RecordObject):
    def __init__(self, name=None):
        super().__init__(name=name)
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


class MMUToLoadStore1Type(RecordObject):
    def __init__(self, name=None):
        super().__init__(name=name)
        self.done          = Signal()
        self.err           = Signal()
        self.invalid       = Signal()
        self.badtree       = Signal()
        self.segerr        = Signal()
        self.perm_error    = Signal()
        self.rc_error      = Signal()
        self.sprval        = Signal(64)


class MMUToDCacheType(RecordObject):
    def __init__(self, name=None):
        super().__init__(name=name)
        self.valid         = Signal()
        self.tlbie         = Signal()
        self.doall         = Signal()
        self.tlbld         = Signal()
        self.addr          = Signal(64)
        self.pte           = Signal(64)


class MMUToICacheType(RecordObject):
    def __init__(self, name=None):
        super().__init__(name=name)
        self.tlbld         = Signal()
        self.tlbie         = Signal()
        self.doall         = Signal()
        self.addr          = Signal(64)
        self.pte           = Signal(64)

