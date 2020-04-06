from nmigen.compat.sim import run_simulation

from soc.TLB.ariane.tlb_content import TLBContent
from soc.TestUtil.test_helper import assert_op, assert_eq


def update(dut, a, t, g, m):
    yield dut.replace_en_i.eq(1)
    yield dut.update_i.valid.eq(1)
    yield dut.update_i.is_512G.eq(t)
    yield dut.update_i.is_1G.eq(g)
    yield dut.update_i.is_2M.eq(m)
    yield dut.update_i.vpn.eq(a)
    yield
    yield


def check_hit(dut, hit, pagesize):
    hit_d = yield dut.lu_hit_o
    assert_eq("hit", hit_d, hit)

    if(hit):
        if(pagesize == "t"):
            hitp = yield dut.lu_is_512G_o
            assert_eq("lu_is_512G_o", hitp, 1)
        elif(pagesize == "g"):
            hitp = yield dut.lu_is_1G_o
            assert_eq("lu_is_1G_o", hitp, 1)
        elif(pagesize == "m"):
            hitp = yield dut.lu_is_2M_o
            assert_eq("lu_is_2M_o", hitp, 1)


def addr(a, b, c, d):
    return a | b << 9 | c << 18 | d << 27


def tbench(dut):
    yield dut.vpn0.eq(0x0A)
    yield dut.vpn1.eq(0x0B)
    yield dut.vpn2.eq(0x0C)
    yield dut.vpn3.eq(0x0D)
    yield from update(dut, addr(0xFF, 0xFF, 0xFF, 0x0D), 1, 0, 0)
    yield from check_hit(dut, 1, "t")

    yield from update(dut, addr(0xFF, 0xFF, 0x0C, 0x0D), 0, 1, 0)
    yield from check_hit(dut, 1, "g")

    yield from update(dut, addr(0xFF, 0x0B, 0x0C, 0x0D), 0, 0, 1)
    yield from check_hit(dut, 1, "m")

    yield from update(dut, addr(0x0A, 0x0B, 0x0C, 0x0D), 0, 0, 0)
    yield from check_hit(dut, 1, "")

    yield from update(dut, addr(0xAA, 0xBB, 0xCC, 0xDD), 0, 0, 0)
    yield from check_hit(dut, 0, "miss")


if __name__ == "__main__":
    dut = TLBContent(4, 4)
    #
    run_simulation(dut, tbench(dut), vcd_name="test_tlb_content.vcd")
    print("TLBContent Unit Test Success")
