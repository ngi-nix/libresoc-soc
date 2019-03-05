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

def check_single_match(dut, dh, op):
    out_sm = yield dut.single_match
    if op == 0:
        assert_eq("Single Match", out_sm, dh)
    else:
        assert_ne("Single Match", out_sm, dh)

def check_match_address(dut, ma, op):
    out_ma = yield dut.match_address
    if op == 0:
        assert_eq("Match Address", out_ma, ma)
    else:
        assert_ne("Match Address", out_ma, ma)

def check_all(dut, single_match, match_address, sm_op, ma_op):
    yield from check_single_match(dut, single_match, sm_op)
    yield from check_match_address(dut, match_address, ma_op)


def testbench(dut):
    # NA
    enable = 1
    write_enable = 0
    address = 0
    data = 0
    single_match = 0
    yield from set_cam(dut, enable, write_enable, address, data)
    yield from check_single_match(dut, single_match, 0)

    # Read Miss
    # Note that the default starting entry data bits are all 0
    enable = 1
    write_enable = 0
    address = 0
    data = 1
    single_match = 0
    yield from set_cam(dut, enable, write_enable, address, data)
    yield
    yield from check_single_match(dut, single_match, 0)

    # Write Entry 0
    enable = 1
    write_enable = 1
    address = 0
    data = 4
    single_match = 0
    yield from set_cam(dut, enable, write_enable, address, data)
    yield
    yield from check_single_match(dut, single_match, 0)

    # Read Hit Entry 0
    enable = 1
    write_enable = 0
    address = 0
    data = 4
    single_match = 1
    yield from set_cam(dut, enable, write_enable, address, data)
    yield
    yield from check_all(dut, single_match, address, 0, 0)

    # Search Hit
    enable = 1
    write_enable = 0
    address = 0
    data = 4
    single_match = 1
    yield from set_cam(dut, enable, write_enable, address, data)
    yield
    yield from check_all(dut, single_match, address, 0, 0)

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
