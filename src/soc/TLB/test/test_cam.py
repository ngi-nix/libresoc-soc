from nmigen.compat.sim import run_simulation

from soc.TLB.Cam import Cam

from soc.TestUtil.test_helper import assert_eq, assert_ne, assert_op

# This function allows for the easy setting of values to the Cam
# Arguments:
#   dut: The Cam being tested
#   e (Enable): Whether the block is going to be enabled
#   we (Write Enable): Whether the Cam will write on the next cycle
#   a (Address): Where the data will be written if write enable is high
#   d (Data): Either what we are looking for or will write to the address


def set_cam(dut, e, we, a, d):
    yield dut.enable.eq(e)
    yield dut.write_enable.eq(we)
    yield dut.address_in.eq(a)
    yield dut.data_in.eq(d)
    yield

# Checks the multiple match of the Cam
# Arguments:
#   dut: The Cam being tested
#   mm (Multiple Match): The expected match result
#   op (Operation): (0 => ==), (1 => !=)


def check_multiple_match(dut, mm, op):
    out_mm = yield dut.multiple_match
    assert_op("Multiple Match", out_mm, mm, op)

# Checks the single match of the Cam
# Arguments:
#   dut: The Cam being tested
#   sm (Single Match): The expected match result
#   op (Operation): (0 => ==), (1 => !=)


def check_single_match(dut, sm, op):
    out_sm = yield dut.single_match
    assert_op("Single Match", out_sm, sm, op)

# Checks the address output of the Cam
# Arguments:
#   dut: The Cam being tested
#   ma (Match Address): The expected match result
#   op (Operation): (0 => ==), (1 => !=)


def check_match_address(dut, ma, op):
    out_ma = yield dut.match_address
    assert_op("Match Address", out_ma, ma, op)

# Checks the state of the Cam
# Arguments:
#   dut: The Cam being tested
#   sm (Single Match): The expected match result
#   mm (Multiple Match): The expected match result
#   ma: (Match Address): The expected address output
#   ss_op (Operation): Operation for the match assertion (0 => ==), (1 => !=)
#   mm_op (Operation): Operation for the match assertion (0 => ==), (1 => !=)
#   ma_op (Operation): Operation for the address assertion (0 => ==), (1 => !=)


def check_all(dut, mm, sm, ma, mm_op, sm_op, ma_op):
    yield from check_multiple_match(dut, mm, mm_op)
    yield from check_single_match(dut, sm, sm_op)
    yield from check_match_address(dut, ma, ma_op)


def tbench(dut):
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

    # Multiple Match test
    # Write Entry 1
    enable = 1
    write_enable = 1
    address = 1
    data = 5
    multiple_match = 0
    single_match = 0
    yield from set_cam(dut, enable, write_enable, address, data)
    yield
    yield from check_single_match(dut, single_match, 0)

    # Write Entry 2
    # Same data as Entry 1
    enable = 1
    write_enable = 1
    address = 2
    data = 5
    multiple_match = 0
    single_match = 0
    yield from set_cam(dut, enable, write_enable, address, data)
    yield
    yield from check_single_match(dut, single_match, 0)

    # Read Hit Data 5
    enable = 1
    write_enable = 0
    address = 1
    data = 5
    multiple_match = 1
    single_match = 0
    yield from set_cam(dut, enable, write_enable, address, data)
    yield
    yield from check_all(dut, multiple_match, single_match, address, 0, 0, 0)

    # Verify read_warning is not caused
    # Write Entry 0
    enable = 1
    write_enable = 1
    address = 0
    data = 7
    multiple_match = 0
    single_match = 0
    yield from set_cam(dut, enable, write_enable, address, data)
    # Note there is no yield we immediately attempt to read in the next cycle

    # Read Hit Data 7
    enable = 1
    write_enable = 0
    address = 0
    data = 7
    multiple_match = 0
    single_match = 1
    yield from set_cam(dut, enable, write_enable, address, data)
    yield
    yield from check_single_match(dut, single_match, 0)

    yield


def test_cam():
    dut = Cam(4, 4)
    run_simulation(dut, tbench(dut), vcd_name="Waveforms/test_cam.vcd")
    print("Cam Unit Test Success")


if __name__ == "__main__":
    test_cam()
