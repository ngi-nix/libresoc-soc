import sys
sys.path.append("../src")
sys.path.append("../../TestUtil")

from nmigen.compat.sim import run_simulation

from AddressEncoder import AddressEncoder

from test_helper import assert_eq, assert_ne, assert_op

def set_encoder(dut, i):
    yield dut.i.eq(i)
    yield
    
def check_single_match(dut, sm, op):
    out_sm = yield dut.single_match
    assert_op("Single Match", out_sm, sm, op)
    
def check_multiple_match(dut, mm, op):
    out_mm = yield dut.multiple_match
    assert_op("Multiple Match", out_mm, mm, op)
    
def check_output(dut, o, op):
    out_o = yield dut.o
    assert_op("Output", out_o, o, op)
    
def check_all(dut, sm, mm, o, sm_op, mm_op, o_op):
    yield from check_single_match(dut, sm, sm_op)
    yield from check_multiple_match(dut, mm, mm_op)
    yield from check_output(dut, o, o_op)

def testbench(dut):
    # Check invalid input
    input = 0
    single_match = 0
    multiple_match = 0
    output = 0
    yield from set_encoder(dut, input)
    yield from check_all(dut, single_match, multiple_match, output, 0, 0, 0)
    
    # Check single bit
    input = 1
    single_match = 1
    multiple_match = 0
    output = 0
    yield from set_encoder(dut, input)
    yield from check_all(dut, single_match, multiple_match, output, 0, 0, 0)   
    
    # Check another single bit
    input = 4
    single_match = 1
    multiple_match = 0
    output = 2
    yield from set_encoder(dut, input)
    yield from check_all(dut, single_match, multiple_match, output, 0, 0, 0)  
    
    # Check multiple match
    # We expected the lowest bit to be returned which is address 0
    input = 5
    single_match = 0
    multiple_match = 1
    output = 0
    yield from set_encoder(dut, input)
    yield from check_all(dut, single_match, multiple_match, output, 0, 0, 0)  
    
    # Check another multiple match
    # We expected the lowest bit to be returned which is address 1
    input = 6
    single_match = 0
    multiple_match = 1
    output = 1
    yield from set_encoder(dut, input)
    yield from check_all(dut, single_match, multiple_match, output, 0, 0, 0)      
    
    

if __name__ == "__main__":
    dut = AddressEncoder(4)
    run_simulation(dut, testbench(dut), vcd_name="Waveforms/test_address_encoder.vcd")
    print("AddressEncoder Unit Test Success")