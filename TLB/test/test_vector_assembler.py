import sys
sys.path.append("../src")
sys.path.append("../../TestUtil")

from nmigen.compat.sim import run_simulation

from test_helper import assert_eq, assert_ne, assert_op
from VectorAssembler import VectorAssembler

# Constant that defines size of output 
# Dont change this unless you change the input vectors to match!
assembler_size = 4

# This function allows for the easy setting of values to the VectorAssembler
# Arguments:
#   dut: The CamEntry being tested
#   input: The array of single bits to be written
def set_assembler(dut, input):
    assert len(input) == assembler_size
    for index in range(assembler_size):
        # Make sure we start from the beginning of the array
        # at least the side that makes sense from a human standpoint
        # of reading bits
        input_index = assembler_size - index - 1
        yield dut.input[index].eq(input[input_index])
    yield
    
# Checks the data state of the CAM entry
# Arguments:
#   dut: The CamEntry being tested
#   o (Output): The expected output
#   op (Operation): (0 => ==), (1 => !=)
def check_output(dut, o, op):
    out_o = yield dut.o
    assert_op("Output", out_o, o, op)
    
def testbench(dut):
    # Input should but bit readable from left to right
    # with Little Endian notation
    input = [1, 1, 0, 0]
    output = 12
    yield from set_assembler(dut, input)
    yield from check_output(dut, output, 0)
    
    input = [1, 1, 0, 1]
    output = 13
    yield from set_assembler(dut, input)
    yield from check_output(dut, output, 0)    

if __name__ == "__main__":
    dut = VectorAssembler(assembler_size)
    run_simulation(dut, testbench(dut), vcd_name="Waveforms/test_vector_assembler.vcd")
    print("VectorAssembler Unit Test Success")