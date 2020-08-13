"""mem_types

based on Anton Blanchard microwatt common.vhdl

"""
from nmigen.iocontrol import RecordObject


# type Loadstore1ToMmuType is record
#     valid : std_ulogic;
#     tlbie : std_ulogic;
#     slbia : std_ulogic;
#     mtspr : std_ulogic;
#     iside : std_ulogic;
#     load  : std_ulogic;
#     priv  : std_ulogic;
#     sprn  : std_ulogic_vector(9 downto 0);
#     addr  : std_ulogic_vector(63 downto 0);
#     rs    : std_ulogic_vector(63 downto 0);
#  end record;
class LoadStore1ToMmuType(RecordObject):
    def __init__(self):
        super().__init__()
        self.valid = Signal()
        self.tlbie = Signal()
        self.slbia = Signal()
        self.mtspr = Signal()
        self.iside = Signal()
        self.load  = Signal()
        self.priv  = Signal()
        self.sprn  = Signal(10)
        self.addr  = Signal(64)
        self.rs    = Signal(64)

# type MmuToLoadstore1Type is record
#     done       : std_ulogic;
#     err        : std_ulogic;
#     invalid    : std_ulogic;
#     badtree    : std_ulogic;
#     segerr     : std_ulogic;
#     perm_error : std_ulogic;
#     rc_error   : std_ulogic;
#     sprval     : std_ulogic_vector(63 downto 0);
# end record;
class MmuToLoadStore1Type(RecordObject):
    def __init__(self):
        super().__init__()
        self.done       = Signal()
        self.err        = Signal()
        self.invalid    = Signal()
        self.badtree    = Signal()
        self.segerr     = Signal()
        self.perm_error = Signal()
        self.rc_error   = Signal()
        self.sprval     = Signal(64)

# type MmuToDcacheType is record
#     valid : std_ulogic;
#     tlbie : std_ulogic;
#     doall : std_ulogic;
#     tlbld : std_ulogic;
#     addr  : std_ulogic_vector(63 downto 0);
#     pte   : std_ulogic_vector(63 downto 0);
# end record;
class MmuToDcacheType(RecordObject):
    def __init__(self):
        super().__init__()
        self.valid = Signal()
        self.tlbie = Signal()
        self.doall = Signal()
        self.tlbld = Signal()
        self.addr  = Signal(64)
        self.pte   = Signal(64)

# type DcacheToMmuType is record
#     stall : std_ulogic;
#     done  : std_ulogic;
#     err   : std_ulogic;
#     data  : std_ulogic_vector(63 downto 0);
# end record;
class DcacheToMmuType(RecordObject):
    def __init__(self):
        super().__init__()
        self.stall = Signal()
        self.done  = Signal()
        self.err   = Signal()
        self.data  = Signal(64)


# type MmuToIcacheType is record
#    tlbld : std_ulogic;
#    tlbie : std_ulogic;
#    doall : std_ulogic;
#    addr  : std_ulogic_vector(63 downto 0);
#    pte   : std_ulogic_vector(63 downto 0);
# end record;
class MmuToIcacheType(RecordObject):
    def __init__(self):
        self.tlbld = Signal()
        self.tlbie = Signal()
        self.doall = Signal()
        self.addr  = Signal(64)
        self.pte   = Signal(64)
