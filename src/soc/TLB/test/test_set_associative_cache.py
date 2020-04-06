from nmigen.compat.sim import run_simulation

from soc.TLB.SetAssociativeCache import SetAssociativeCache

from soc.TestUtil.test_helper import assert_eq, assert_ne, assert_op


def set_sac(dut, e, c, s, t, d):
    yield dut.enable.eq(e)
    yield dut.command.eq(c)
    yield dut.cset.eq(s)
    yield dut.tag.eq(t)
    yield dut.data_i.eq(d)
    yield


def tbench(dut):
    enable = 1
    command = 2
    cset = 1
    tag = 2
    data = 3
    yield from set_sac(dut, enable, command, cset, tag, data)
    yield

    enable = 1
    command = 2
    cset = 1
    tag = 5
    data = 8
    yield from set_sac(dut, enable, command, cset, tag, data)
    yield


def test_assoc_cache():
    dut = SetAssociativeCache(4, 4, 4, 4)
    run_simulation(dut, tbench(
        dut), vcd_name="Waveforms/test_set_associative_cache.vcd")
    print("Set Associative Cache Unit Test Success")


if __name__ == "__main__":
    test_assoc_cache()
