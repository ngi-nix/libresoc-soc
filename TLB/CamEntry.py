from nmigen import Module, Signal
from nmigen.compat.fhdl.structure import If
from nmigen.compat.sim import run_simulation

class CamEntry:
    def __init__(self, key_size, data_size):
        # Internal
        self.key = Signal(key_size)
        
        # Input
        self.write = Signal(1) # Read => 0 Write => 1
        self.key_in = Signal(key_size) # Reference key for the CAM
        self.data_in = Signal(data_size) # Data input when writing
        
        # Output
        self.match = Signal(1) # Result of the internal/input key comparison
        self.data = Signal(data_size)
        
        
    def get_fragment(self, platform=None):
        m = Module()
        with m.If(self.write == 1):
            m.d.sync += [
                self.key.eq(self.key_in),
                self.data.eq(self.data_in),
                self.match.eq(1)
            ]
        with m.Else():
            with m.If(self.key_in == self.key):
                m.d.sync += self.match.eq(0)
            with m.Else():
                m.d.sync += self.match.eq(1)
        
        return m
    
#########    
# TESTING
########
 
# This function allows for the easy setting of values to the Cam Entry
# unless the key is incorrect
# Arguments:
#   dut: The CamEntry being tested
#   w (write): Read (0) or Write (1)
#   k (key): The key to be set
#   d (data): The data to be set  
def set_cam(dut, w, k, d):
    yield dut.write.eq(w)
    yield dut.key_in.eq(k)
    yield dut.data_in.eq(d)
    yield
    
# Verifies the given values via the requested operation
# Arguments:
#   pre (Prefix): Appended to the front of the assert statement
#   e (Expected): The expected value
#   out (Output): The output result
#   op (Operation): (0 => ==), (1 => !=)
def check(pre, e, out, op):
    if(op == 0):
        yield
        assert out == e, pre + " Output " + str(out) + " Expected " + str(e)
    else:
        yield
        assert out != e, pre + " Output " + str(out) + " Expected " + str(e) 

# Checks the key state of the CAM entry
# Arguments:
#   dut: The CamEntry being tested
#   k (Key): The expected key
#   op (Operation): (0 => ==), (1 => !=)
def check_key(dut, k, op):
    out_k = yield dut.key
    check("K", out_k, k, op)   
   
# Checks the data state of the CAM entry
# Arguments:
#   dut: The CamEntry being tested
#   d (Data): The expected data
#   op (Operation): (0 => ==), (1 => !=)
def check_data(dut, d, op):
    out_d = yield dut.data
    check("D", out_d, d, op)   
  
# Checks the match state of the CAM entry
# Arguments:
#   dut: The CamEntry being tested
#   m (Match): The expected match  
#   op (Operation): (0 => ==), (1 => !=)
def check_match(dut, m, op):
    out_m = yield dut.match
    check("M", out_m, m, op)  
  
# Checks the state of the CAM entry
# Arguments:
#   dut: The CamEntry being tested
#   k (key): The expected key  
#   d (data): The expected data
#   m (match): The expected match  
#   kop (Operation): The operation for the key assertion (0 => ==), (1 => !=)
#   dop (Operation): The operation for the data assertion (0 => ==), (1 => !=)
#   mop (Operation): The operation for the match assertion (0 => ==), (1 => !=)
def check_all(dut, k, d, m, kop, dop, mop):
    yield from check_key(dut, k, kop)
    yield from check_data(dut, d, dop)
    yield from check_match(dut, m, mop)
    
# This testbench goes through the paces of testing the CamEntry module
# It is done by writing and then reading various combinations of key/data pairs
# and reading the results with varying keys to verify the resulting stored
# data is correct.
def testbench(dut):
    # Check write
    write = 1
    key = 1
    data = 1
    match = 1
    yield from set_cam(dut, write, key, data)
    yield from check_all(dut, key, data, match, 0, 0, 0)
    
    # Check read miss
    write = 0
    key = 2
    data = 1
    match = 0 
    yield from set_cam(dut, write, key, data)
    yield from check_all(dut, key, data, match, 1, 0, 0) 
    
    # Check read hit
    write = 0
    key = 1
    data = 1
    match = 1
    yield from set_cam(dut, write, key, data)
    yield from check_all(dut, key, data, match, 0, 0, 0) 
    
    # Check write
    write = 1
    key = 2
    data = 5
    match = 1
    yield from set_cam(dut, write, key, data)
    yield from check_all(dut, key, data, match, 0, 0, 0) 
    
    yield
    
if __name__ == "__main__":
    dut = CamEntry(4, 4)
    run_simulation(dut, testbench(dut), vcd_name="Waveforms/cam_entry_test.vcd")