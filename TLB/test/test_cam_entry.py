import sys
sys.path.append("../src")
sys.path.append("../../TestUtil")

from nmigen.compat.sim import run_simulation

from test_helper import assert_eq, assert_ne
from CamEntry import CamEntry

# This function allows for the easy setting of values to the Cam Entry
# unless the key is incorrect
# Arguments:
#   dut: The CamEntry being tested
#   c (command): NA (0), Read (1), Write (2), Reserve (3)
#   d (data): The data to be set
def set_cam_entry(dut, c, d):
    # Write desired values
    yield dut.command.eq(c)
    yield dut.data_in.eq(d)
    yield
    # Reset all lines
    yield dut.command.eq(0)
    yield dut.data_in.eq(0)
    yield

# Checks the data state of the CAM entry
# Arguments:
#   dut: The CamEntry being tested
#   d (Data): The expected data
#   op (Operation): (0 => ==), (1 => !=)
def check_data(dut, d, op):
    out_d = yield dut.data
    if op == 0:
        assert_eq("Data", out_d, d)
    else:
        assert_ne("Data", out_d, d)

# Checks the match state of the CAM entry
# Arguments:
#   dut: The CamEntry being tested
#   m (Match): The expected match
#   op (Operation): (0 => ==), (1 => !=)
def check_match(dut, m, op):
    out_m = yield dut.match
    if op == 0:
        assert_eq("Match", out_m, m)
    else:
        assert_ne("Match", out_m, m)

# Checks the state of the CAM entry
# Arguments:
#   dut: The CamEntry being tested
#   d (data): The expected data
#   m (match): The expected match
#   d_op (Operation): The operation for the data assertion (0 => ==), (1 => !=)
#   m_op (Operation): The operation for the match assertion (0 => ==), (1 => !=)
def check_all(dut, d, m, d_op, m_op):
    yield from check_data(dut, d, d_op)
    yield from check_match(dut, m, m_op)

# This testbench goes through the paces of testing the CamEntry module
# It is done by writing and then reading various combinations of key/data pairs
# and reading the results with varying keys to verify the resulting stored
# data is correct.
def testbench(dut):
    # Check write
    command = 2
    data = 1
    match = 0
    yield from set_cam_entry(dut, command, data)
    yield from check_all(dut, data, match, 0, 0)

    # Check read miss
    command = 1
    data = 2
    match = 0
    yield from set_cam_entry(dut, command, data)
    yield from check_all(dut, data, match, 1, 0)

    # Check read hit
    command = 1
    data = 1
    match = 1
    yield from set_cam_entry(dut, command, data)
    yield from check_all(dut, data, match, 0, 0)

    # Check overwrite
    command = 2
    data = 5
    match = 0
    yield from set_cam_entry(dut, command, data)
    yield
    yield from check_all(dut, data, match, 0, 0)

    # Check read hit
    command = 1
    data = 5
    match = 1
    yield from set_cam_entry(dut, command, data)
    yield from check_all(dut, data, match, 0, 0)

    # Check reset
    command = 3
    data = 0
    match = 0
    yield from set_cam_entry(dut, command, data)
    yield from check_all(dut, data, match, 0, 0)

    # Extra clock cycle for waveform
    yield

if __name__ == "__main__":
    dut = CamEntry(4)
    run_simulation(dut, testbench(dut), vcd_name="Waveforms/cam_entry_test.vcd")
    print("CamEntry Unit Test Success")
