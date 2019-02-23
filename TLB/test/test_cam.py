import sys
sys.path.append("../src")
sys.path.append("../../TestUtil")

from nmigen.compat.sim import run_simulation

from Cam import Cam

from test_helper import check

def set_cam(dut, c, a, k, d):
    yield dut.command.eq(c)
    yield dut.address.eq(a)
    yield dut.key_in.eq(k)
    yield dut.data_in.eq(d)
    yield
    
def check_data_hit(dut, data_hit, op):
    out_dh = yield dut.data_hit
    yield from check("Data Hit", out_dh, data_hit, op)
    
def check_data(dut, data, op):
    out_d = yield dut.data
    yield from check("Data", out_d, data, op)  
    
def check_all(dut, data_hit, data, dh_op, d_op):
    yield from check_data_hit(dut, data_hit, dh_op)
    yield from check_data(dut, data, d_op)
    

def testbench(dut):
    # NA
    command = 0
    address = 0
    key = 0
    data = 0
    data_hit = 0
    yield from set_cam(dut, command, address, key, data)
    yield from check_data_hit(dut, data_hit, 0)
    
    # Search
    command = 3
    address = 0
    key = 0
    data = 0
    data_hit = 0
    yield from set_cam(dut, command, address, key, data)
    yield from check_data_hit(dut, data_hit, 0)    
    
    # Write Entry 0
    command = 1
    address = 0
    key = 5
    data = 4
    data_hit = 1
    yield from set_cam(dut, command, address, key, data)
    yield from check_data_hit(dut, data_hit, 0)     

if __name__ == "__main__":
    dut = Cam(4, 4, 4)
    run_simulation(dut, testbench(dut), vcd_name="Waveforms/cam_test.vcd")
    print("Cam Unit Test Success")