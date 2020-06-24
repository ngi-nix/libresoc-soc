from nmigen import Signal

class LoadStoreUnitInterface:
    def __init__(self):

        #self.dbus = Record(wishbone_layout)

        self.x_addr = Signal(32)    # The address used for loads/stores
        self.x_mask = Signal(4)     # Mask of which bytes to write
        self.x_load = Signal()      # set to do a memory load
        self.x_store = Signal()     # set to do a memory store
        self.x_store_data = Signal(32) # The data to write when storing
        self.x_stall = Signal()        # input - do nothing until low
        self.x_valid = Signal()
        self.m_stall = Signal() # input - do nothing until low
        self.m_valid = Signal() # when this is high and m_busy is
        # low, the data for the memory load can be read from m_load_data

        self.x_busy = Signal()  # set when the memory is busy
        self.m_busy = Signal()  # set when the memory is busy
        self.m_load_data = Signal(32)  # Data returned from a memory read
        self.m_load_error = Signal()   # Whether there was an error when loading
        self.m_store_error = Signal()  # Whether there was an error when storing
        self.m_badaddr = Signal(30)    # The address of the load/store error
