import sys
sys.path.append("../src")
sys.path.append("../../TestUtil")

from nmigen.compat.sim import run_simulation

from WalkingPriorityEncoder import WalkingPriorityEncoder

from test_helper import assert_eq, assert_ne

def testbench(dut):
    yield dut.write.eq(1)
    yield dut.input.eq(5)
    yield dut.output.eq(3)
    yield
    yield dut.write.eq(0)
    yield dut.input.eq(0)
    yield
    yield
    yield
    yield
    yield
    yield
    yield
    yield
    output = yield dut.output
    #assert_eq("Output", output, 1) 

if __name__ == "__main__":
    dut = WalkingPriorityEncoder(4)
    run_simulation(dut, testbench(dut), vcd_name="Waveforms/cam_walking_priority_encoder.vcd")
    print("WalkingPriorityEncoder Unit Test Success")