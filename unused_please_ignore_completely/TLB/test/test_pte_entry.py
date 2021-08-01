from nmigen.compat.sim import run_simulation

from soc.TLB.PteEntry import PteEntry

from soc.TestUtil.test_helper import assert_op


def set_entry(dut, i):
    yield dut.i.eq(i)
    yield


def check_dirty(dut, d, op):
    out_d = yield dut.d
    assert_op("Dirty", out_d, d, op)


def check_accessed(dut, a, op):
    out_a = yield dut.a
    assert_op("Accessed", out_a, a, op)


def check_global(dut, o, op):
    out = yield dut.g
    assert_op("Global", out, o, op)


def check_user(dut, o, op):
    out = yield dut.u
    assert_op("User Mode", out, o, op)


def check_xwr(dut, o, op):
    out = yield dut.xwr
    assert_op("XWR", out, o, op)


def check_asid(dut, o, op):
    out = yield dut.asid
    assert_op("ASID", out, o, op)


def check_pte(dut, o, op):
    out = yield dut.pte
    assert_op("ASID", out, o, op)


def check_valid(dut, v, op):
    out_v = yield dut.v
    assert_op("Valid", out_v, v, op)


def check_all(dut, d, a, g, u, xwr, v, asid, pte):
    yield from check_dirty(dut, d, 0)
    yield from check_accessed(dut, a, 0)
    yield from check_global(dut, g, 0)
    yield from check_user(dut, u, 0)
    yield from check_xwr(dut, xwr, 0)
    yield from check_asid(dut, asid, 0)
    yield from check_pte(dut, pte, 0)
    yield from check_valid(dut, v, 0)


def tbench(dut):
    # 80 bits represented. Ignore the MSB as it will be truncated
    # ASID is bits first 4 hex values (bits 64 - 78)

    i = 0x7FFF0000000000000031
    dirty = 0
    access = 0
    glob = 1
    user = 1
    xwr = 0
    valid = 1
    asid = 0x7FFF
    pte = 0x0000000000000031
    yield from set_entry(dut, i)
    yield from check_all(dut, dirty, access, glob, user, xwr, valid, asid, pte)

    i = 0x0FFF00000000000000FF
    dirty = 1
    access = 1
    glob = 1
    user = 1
    xwr = 7
    valid = 1
    asid = 0x0FFF
    pte = 0x00000000000000FF
    yield from set_entry(dut, i)
    yield from check_all(dut, dirty, access, glob, user, xwr, valid, asid, pte)

    i = 0x0721000000001100001F
    dirty = 0
    access = 0
    glob = 0
    user = 1
    xwr = 7
    valid = 1
    asid = 0x0721
    pte = 0x000000001100001F
    yield from set_entry(dut, i)
    yield from check_all(dut, dirty, access, glob, user, xwr, valid, asid, pte)

    yield


def test_pteentry():
    dut = PteEntry(15, 64)
    run_simulation(dut, tbench(dut), vcd_name="Waveforms/test_pte_entry.vcd")
    print("PteEntry Unit Test Success")


if __name__ == "__main__":
    test_pteentry()
