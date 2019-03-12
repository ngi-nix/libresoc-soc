import sys
sys.path.append("../src")
sys.path.append("../../TestUtil")

from nmigen.compat.sim import run_simulation

from RegisterFile import RegisterFile

from test_helper import assert_eq, assert_ne, assert_op

def setRegisterFile(dut, e, we, a, di):
    yield dut.enable.eq(e)
    yield dut.write_enable.eq(we)
    yield dut.address.eq(a)
    yield dut.data_i.eq(di)
    yield
 
# Checks the address output of the Cam
# Arguments:
#   dut: The Cam being tested
#   v (Valid): If the output is valid or not
#   op (Operation): (0 => ==), (1 => !=)   
def check_valid(dut, v, op):
    out_v = yield dut.valid
    assert_op("Valid", out_v, v, op)
 
# Checks the address output of the Cam
# Arguments:
#   dut: The Cam being tested
#   do (Data Out): The current output data
#   op (Operation): (0 => ==), (1 => !=)   
def check_data(dut, do, op):
    out_do = yield dut.data_o
    assert_op("Data Out", out_do, do, op)

# Checks the address output of the Cam
# Arguments:
#   dut: The Cam being tested
#   v (Valid): If the output is valid or not
#   do (Data Out): The current output data
#   v_op (Operation): Operation for the valid assertion (0 => ==), (1 => !=)
#   do_op (Operation): Operation for the data assertion (0 => ==), (1 => !=)
def check_all(dut, v, do, v_op, do_op):
    yield from check_valid(dut, v, v_op)
    yield from check_data(dut, do, do_op)

def testbench(dut):
    # Test write 0
    enable = 1
    write_enable = 1
    address = 0
    data = 1
    valid = 0
    yield from setRegisterFile(dut, enable, write_enable, address, data)
    yield
    yield from check_all(dut, valid, 0, 0, 0)
    
    # Test read 0 
    enable = 1
    write_enable = 0
    address = 0
    data = 1
    valid = 1
    yield from setRegisterFile(dut, enable, write_enable, address, data)
    yield
    yield from check_all(dut, valid, data, 0, 0) 
    
    # Test write 3
    enable = 1
    write_enable = 1
    address = 3
    data = 5
    valid = 0
    yield from setRegisterFile(dut, enable, write_enable, address, data)
    yield
    yield from check_all(dut, valid, 0, 0, 0)
    
    # Test read 3  
    enable = 1
    write_enable = 0
    address = 3
    data = 5
    valid = 1
    yield from setRegisterFile(dut, enable, write_enable, address, data)
    yield
    yield from check_all(dut, valid, data, 0, 0)    
    
    # Test read 0 
    enable = 1
    write_enable = 0
    address = 0
    data = 1
    valid = 1
    yield from setRegisterFile(dut, enable, write_enable, address, data)
    yield
    yield from check_all(dut, valid, data, 0, 0)   
    
    # Test overwrite 0
    enable = 1
    write_enable = 1
    address = 0
    data = 6
    valid = 0
    yield from setRegisterFile(dut, enable, write_enable, address, data)
    yield
    yield from check_all(dut, valid, 0, 0, 0)  
    
    # Test read 0 
    enable = 1
    write_enable = 0
    address = 0
    data = 6
    valid = 1
    yield from setRegisterFile(dut, enable, write_enable, address, data)
    yield
    yield from check_all(dut, valid, data, 0, 0)     
    

if __name__ == "__main__":
    dut = RegisterFile(4, 4)
    run_simulation(dut, testbench(dut), vcd_name="Waveforms/test_register_file.vcd")
    print("RegisterFile Unit Test Success")