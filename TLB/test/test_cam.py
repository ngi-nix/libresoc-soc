import sys
sys.path.append("../src")
sys.path.append("../../TestUtil")

from nmigen.compat.sim import run_simulation

from Cam import Cam

from test_helper import assert_eq, assert_ne

def set_cam(dut, e, we, a, d):
    yield dut.enable.eq(e)
    yield dut.write_enable.eq(we)
    yield dut.address_in.eq(a)
    yield dut.data_in.eq(d)
    yield   
    
def check_data_hit(dut, dh, op):
    out_dh = yield dut.single_match
    if op == 0:
        assert_eq("Data Hit", out_dh, dh)
    else:
        assert_ne("Data Hit", out_dh, dh)
    
def check_data(dut, d, op):
    out_d = yield dut.data_out
    if op == 0:
        assert_eq("Data", out_d, d)
    else:
        assert_ne("Data", out_d, d)  
    
def check_all(dut, data_hit, data, dh_op, d_op):
    yield from check_data_hit(dut, data_hit, dh_op)
    yield from check_data(dut, data, d_op)
    

def testbench(dut):
    # NA
    enable = 1
    write_enable = 0
    address = 0
    data = 0
    data_hit = 0
    yield from set_cam(dut, enable, write_enable, address, data)
    yield from check_data_hit(dut, data_hit, 0)
    
    # Search Miss
    # Note that the default starting entry data bits are all 0
    enable = 1
    write_enable = 0
    address = 0
    data = 1
    data_hit = 0
    yield from set_cam(dut, enable, write_enable, address, data)
    yield
    yield from check_data_hit(dut, data_hit, 0)    
    
    # Write Entry 0
    enable = 1
    write_enable = 1
    address = 0
    data = 4
    data_hit = 0
    yield from set_cam(dut, enable, write_enable, address, data)
    yield
    yield from check_data_hit(dut, data_hit, 0) 
    
    # Read Entry 0
    enable = 1
    write_enable = 0
    address = 0
    data = 4
    data_hit = 1
    yield from set_cam(dut, enable, write_enable, address, data)
    yield
    #yield from check_all(dut, data_hit, data, 0, 0) 
    
    # Search Hit
    enable = 1
    write_enable = 0
    address = 0
    data = 4
    data_hit = 1
    yield from set_cam(dut, enable, write_enable, address, data)
    yield
    #yield from check_all(dut, data_hit, data, 0, 0)
    
    # Search Miss
    enable = 1
    write_enable = 0
    address = 0
    data = 5
    data_hit = 0
    yield from set_cam(dut, enable, write_enable, address, data)
    yield
    #yield from check_all(dut, data_hit, data, 0, 1)     
    
    yield 
    

if __name__ == "__main__":
    dut = Cam(4, 4)
    run_simulation(dut, testbench(dut), vcd_name="Waveforms/cam_test.vcd")
    print("Cam Unit Test Success")