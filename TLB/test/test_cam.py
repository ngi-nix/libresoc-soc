import sys
sys.path.append("../src")
sys.path.append("../../TestUtil")

from nmigen.compat.sim import run_simulation

from Cam import Cam

from test_helper import assert_eq, assert_ne, assert_op

def set_cam(dut, e, we, a, d):
    yield dut.enable.eq(e)
    yield dut.write_enable.eq(we)
    yield dut.address_in.eq(a)
    yield dut.data_in.eq(d)
    yield
    
def check_multiple_match(dut, mm, op):
    out_mm = yield dut.multiple_match
    assert_op("Multiple Match", out_mm, mm, op)

def check_single_match(dut, sm, op):
    out_sm = yield dut.single_match
    assert_op("Single Match", out_sm, sm, op)

def check_match_address(dut, ma, op):
    out_ma = yield dut.match_address
    assert_op("Match Address", out_ma, ma, op)

def check_all(dut, multiple_match, single_match, match_address, mm_op, sm_op, ma_op):
    yield from check_multiple_match(dut, multiple_match, mm_op)
    yield from check_single_match(dut, single_match, sm_op)
    yield from check_match_address(dut, match_address, ma_op)



def testbench(dut):
    # NA
    enable = 0
    write_enable = 0
    address = 0
    data = 0
    single_match = 0
    yield from set_cam(dut, enable, write_enable, address, data)
    yield
    yield from check_single_match(dut, single_match, 0)

    # Read Miss Multiple
    # Note that the default starting entry data bits are all 0
    enable = 1
    write_enable = 0
    address = 0
    data = 0
    multiple_match = 1
    single_match = 0
    yield from set_cam(dut, enable, write_enable, address, data)
    yield
    yield from check_multiple_match(dut, multiple_match, 0)

    # Read Miss
    # Note that the default starting entry data bits are all 0
    enable = 1
    write_enable = 0
    address = 0
    data = 1
    multiple_match = 0
    single_match = 0
    yield from set_cam(dut, enable, write_enable, address, data)
    yield
    yield from check_single_match(dut, single_match, 0)

    # Write Entry 0
    enable = 1
    write_enable = 1
    address = 0
    data = 4
    multiple_match = 0
    single_match = 0
    yield from set_cam(dut, enable, write_enable, address, data)
    yield
    yield from check_single_match(dut, single_match, 0)

    # Read Hit Entry 0
    enable = 1
    write_enable = 0
    address = 0
    data = 4
    multiple_match = 0
    single_match = 1
    yield from set_cam(dut, enable, write_enable, address, data)
    yield
    yield from check_all(dut, multiple_match, single_match, address, 0, 0, 0)

    # Search Hit
    enable = 1
    write_enable = 0
    address = 0
    data = 4
    multiple_match = 0
    single_match = 1
    yield from set_cam(dut, enable, write_enable, address, data)
    yield
    yield from check_all(dut, multiple_match, single_match, address, 0, 0, 0)

    # Search Miss
    enable = 1
    write_enable = 0
    address = 0
    data = 5
    single_match = 0
    yield from set_cam(dut, enable, write_enable, address, data)
    yield
    yield from check_single_match(dut, single_match, 0)

    yield


if __name__ == "__main__":
    dut = Cam(4, 4)
    run_simulation(dut, testbench(dut), vcd_name="Waveforms/cam_test.vcd")
    print("Cam Unit Test Success")
