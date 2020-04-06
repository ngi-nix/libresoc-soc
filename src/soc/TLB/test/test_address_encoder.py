from nmigen.compat.sim import run_simulation
from soc.TLB.AddressEncoder import AddressEncoder
from soc.TestUtil.test_helper import assert_eq, assert_ne, assert_op


# This function allows for the easy setting of values to the AddressEncoder
# Arguments:
#   dut: The AddressEncoder being tested
#   i (Input): The array of single bits to be written
def set_encoder(dut, i):
    yield dut.i.eq(i)
    yield

# Checks the single match of the AddressEncoder
# Arguments:
#   dut: The AddressEncoder being tested
#   sm (Single Match): The expected match result
#   op (Operation): (0 => ==), (1 => !=)


def check_single_match(dut, sm, op):
    out_sm = yield dut.single_match
    assert_op("Single Match", out_sm, sm, op)

# Checks the multiple match of the AddressEncoder
# Arguments:
#   dut: The AddressEncoder being tested
#   mm (Multiple Match): The expected match result
#   op (Operation): (0 => ==), (1 => !=)


def check_multiple_match(dut, mm, op):
    out_mm = yield dut.multiple_match
    assert_op("Multiple Match", out_mm, mm, op)

# Checks the output of the AddressEncoder
# Arguments:
#   dut: The AddressEncoder being tested
#   o (Output): The expected output
#   op (Operation): (0 => ==), (1 => !=)


def check_output(dut, o, op):
    out_o = yield dut.o
    assert_op("Output", out_o, o, op)

# Checks the state of the AddressEncoder
# Arguments:
#   dut: The AddressEncoder being tested
#   sm (Single Match): The expected match result
#   mm (Multiple Match): The expected match result
#   o (Output): The expected output
#   ss_op (Operation): Operation for the match assertion (0 => ==), (1 => !=)
#   mm_op (Operation): Operation for the match assertion (0 => ==), (1 => !=)
#   o_op (Operation): Operation for the match assertion (0 => ==), (1 => !=)


def check_all(dut, sm, mm, o, sm_op, mm_op, o_op):
    yield from check_single_match(dut, sm, sm_op)
    yield from check_multiple_match(dut, mm, mm_op)
    yield from check_output(dut, o, o_op)


def tbench(dut):
    # Check invalid input
    in_val = 0b000
    single_match = 0
    multiple_match = 0
    output = 0
    yield from set_encoder(dut, in_val)
    yield from check_all(dut, single_match, multiple_match, output, 0, 0, 0)

    # Check single bit
    in_val = 0b001
    single_match = 1
    multiple_match = 0
    output = 0
    yield from set_encoder(dut, in_val)
    yield from check_all(dut, single_match, multiple_match, output, 0, 0, 0)

    # Check another single bit
    in_val = 0b100
    single_match = 1
    multiple_match = 0
    output = 2
    yield from set_encoder(dut, in_val)
    yield from check_all(dut, single_match, multiple_match, output, 0, 0, 0)

    # Check multiple match
    # We expected the lowest bit to be returned which is address 0
    in_val = 0b101
    single_match = 0
    multiple_match = 1
    output = 0
    yield from set_encoder(dut, in_val)
    yield from check_all(dut, single_match, multiple_match, output, 0, 0, 0)

    # Check another multiple match
    # We expected the lowest bit to be returned which is address 1
    in_val = 0b110
    single_match = 0
    multiple_match = 1
    output = 1
    yield from set_encoder(dut, in_val)
    yield from check_all(dut, single_match, multiple_match, output, 0, 0, 0)


def test_addr():
    dut = AddressEncoder(4)
    run_simulation(dut, tbench(dut),
                   vcd_name="Waveforms/test_address_encoder.vcd")
    print("AddressEncoder Unit Test Success")


if __name__ == "__main__":
    test_addr()
