"""wb_types

based on Anton Blanchard microwatt wishbone_types.vhdl

"""

from nmigen import Signal
from nmutil.iocontrol import RecordObject


# library ieee;
# use ieee.std_logic_1164.all;
#
# package wishbone_types is
#     --
#     -- Main CPU bus. 32-bit address, 64-bit data
#     --
#     constant wishbone_addr_bits : integer := 32;
#     constant wishbone_data_bits : integer := 64;
#     constant wishbone_sel_bits : integer := wishbone_data_bits/8;

# Main CPU bus. 32-bit address, 64-bit data
WB_ADDR_BITS = 32
WB_DATA_BITS = 64
WB_SEL_BITS  = WB_DATA_BITS // 8

# subtype wishbone_addr_type is
#  std_ulogic_vector(wishbone_addr_bits-1 downto 0);
# subtype wishbone_data_type is
#  std_ulogic_vector(wishbone_data_bits-1 downto 0);
# subtype wishbone_sel_type is
#  std_ulogic_vector(wishbone_sel_bits-1  downto 0);

def WBAddrType():
    return Signal(WB_ADDR_BITS, name="adr")

def WBDataType():
    return Signal(WB_DATA_BITS, name="dat")

def WBSelType():
    return Signal(WB_SEL_BITS, name="sel", reset=0b11111111)

# type wishbone_master_out is record
#     adr : wishbone_addr_type;
#     dat : wishbone_data_type;
#     cyc : std_ulogic;
#     stb : std_ulogic;
#     sel : wishbone_sel_type;
#     we  : std_ulogic;
# end record;
class WBMasterOut(RecordObject):
    def __init__(self, name=None):
        super().__init__(name=name)
        self.adr = WBAddrType()
        self.dat = WBDataType()
        self.cyc = Signal()
        self.stb = Signal()
        self.sel = WBSelType()
        self.we  = Signal()

# constant wishbone_master_out_init : wishbone_master_out := (
#  adr => (others => '0'), dat => (others => '0'), cyc => '0',
#  stb => '0', sel => (others => '0'), we => '0'
# );
def WBMasterOutInit():
    return WBMasterOut()

# type wishbone_slave_out is record
#     dat   : wishbone_data_type;
#     ack   : std_ulogic;
#     stall : std_ulogic;
# end record;
class WBSlaveOut(RecordObject):
    def __init__(self, name=None):
        super().__init__(name=name)
        self.dat   = WBDataType()
        self.ack   = Signal()
        self.stall = Signal()

# constant wishbone_slave_out_init : wishbone_slave_out := (
#  ack => '0', stall => '0', others => (others => '0')
# );
def WBSlaveOutInit():
    return WBSlaveOut()

# type wishbone_master_out_vector is array (natural range <>) of
#  wishbone_master_out;
def WBMasterOutVector():
    return Array(WBMasterOut())

# type wishbone_slave_out_vector is array (natural range <>) of
#  wishbone_slave_out;
def WBSlaveOutVector():
    return Array(WBSlaveOut())

# -- IO Bus to a device, 30-bit address, 32-bits data
# type wb_io_master_out is record
#     adr : std_ulogic_vector(29 downto 0);
#     dat : std_ulogic_vector(31 downto 0);
#     sel : std_ulogic_vector(3 downto 0);
#     cyc : std_ulogic;
#     stb : std_ulogic;
#     we  : std_ulogic;
# end record;
# IO Bus to a device, 30-bit address, 32-bits data
class WBIOMasterOut(RecordObject):
    def __init__(self, name=None):
        super().__init__(name=name)
        self.adr = Signal(30)
        self.dat = Signal(32)
        self.sel = Signal(4)
        self.cyc = Signal()
        self.stb = Signal()
        self.we  = Signal()

# type wb_io_slave_out is record
#     dat   : std_ulogic_vector(31 downto 0);
#     ack   : std_ulogic;
#     stall : std_ulogic;
# end record;
class WBIOSlaveOut(RecordObject):
    def __init__(self, name=None):
        super().__init__(name=name)
        self.data  = Signal(32)
        self.ack   = Signal()
        self.stall = Signal()

# constant wb_io_slave_out_init : wb_io_slave_out := (
#  ack => '0', stall => '0', others => (others => '0')
# );
def WBIOSlaveOutInit():
    return WBIOSlaveOut()

# end package wishbone_types;
