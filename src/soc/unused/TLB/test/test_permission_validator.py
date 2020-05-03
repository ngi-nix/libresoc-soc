from nmigen.compat.sim import run_simulation

from soc.TLB.PermissionValidator import PermissionValidator

from soc.TestUtil.test_helper import assert_op


def set_validator(dut, d, xwr, sm, sa, asid):
    yield dut.data.eq(d)
    yield dut.xwr.eq(xwr)
    yield dut.super_mode.eq(sm)
    yield dut.super_access.eq(sa)
    yield dut.asid.eq(asid)
    yield


def check_valid(dut, v, op):
    out_v = yield dut.valid
    assert_op("Valid", out_v, v, op)


def tbench(dut):
    # 80 bits represented. Ignore the MSB as it will be truncated
    # ASID is bits first 4 hex values (bits 64 - 78)

    # Test user mode entry valid
    # Global Bit matching ASID
    # Ensure that user mode and valid is enabled!
    data = 0x7FFF0000000000000031
    # Ignore MSB it will be truncated
    asid = 0x7FFF
    super_mode = 0
    super_access = 0
    xwr = 0
    valid = 1
    yield from set_validator(dut, data, xwr, super_mode, super_access, asid)
    yield from check_valid(dut, valid, 0)

    # Test user mode entry valid
    # Global Bit nonmatching ASID
    # Ensure that user mode and valid is enabled!
    data = 0x7FFF0000000000000031
    # Ignore MSB it will be truncated
    asid = 0x7FF6
    super_mode = 0
    super_access = 0
    xwr = 0
    valid = 1
    yield from set_validator(dut, data, xwr, super_mode, super_access, asid)
    yield from check_valid(dut, valid, 0)

    # Test user mode entry invalid
    # Global Bit nonmatching ASID
    # Ensure that user mode and valid is enabled!
    data = 0x7FFF0000000000000021
    # Ignore MSB it will be truncated
    asid = 0x7FF6
    super_mode = 0
    super_access = 0
    xwr = 0
    valid = 0
    yield from set_validator(dut, data, xwr, super_mode, super_access, asid)
    yield from check_valid(dut, valid, 0)

    # Test user mode entry valid
    # Ensure that user mode and valid is enabled!
    data = 0x7FFF0000000000000011
    # Ignore MSB it will be truncated
    asid = 0x7FFF
    super_mode = 0
    super_access = 0
    xwr = 0
    valid = 1
    yield from set_validator(dut, data, xwr, super_mode, super_access, asid)
    yield from check_valid(dut, valid, 0)

    # Test user mode entry invalid
    # Ensure that user mode and valid is enabled!
    data = 0x7FFF0000000000000011
    # Ignore MSB it will be truncated
    asid = 0x7FF6
    super_mode = 0
    super_access = 0
    xwr = 0
    valid = 0
    yield from set_validator(dut, data, xwr, super_mode, super_access, asid)
    yield from check_valid(dut, valid, 0)

    # Test supervisor mode entry valid
    # The entry is NOT in user mode
    # Ensure that user mode and valid is enabled!
    data = 0x7FFF0000000000000001
    # Ignore MSB it will be truncated
    asid = 0x7FFF
    super_mode = 1
    super_access = 0
    xwr = 0
    valid = 1
    yield from set_validator(dut, data, xwr, super_mode, super_access, asid)
    yield from check_valid(dut, valid, 0)

    # Test supervisor mode entry invalid
    # The entry is in user mode
    # Ensure that user mode and valid is enabled!
    data = 0x7FFF0000000000000011
    # Ignore MSB it will be truncated
    asid = 0x7FFF
    super_mode = 1
    super_access = 0
    xwr = 0
    valid = 0
    yield from set_validator(dut, data, xwr, super_mode, super_access, asid)
    yield from check_valid(dut, valid, 0)

    # Test supervisor mode entry valid
    # The entry is NOT in user mode with access
    # Ensure that user mode and valid is enabled!
    data = 0x7FFF0000000000000001
    # Ignore MSB it will be truncated
    asid = 0x7FFF
    super_mode = 1
    super_access = 1
    xwr = 0
    valid = 1
    yield from set_validator(dut, data, xwr, super_mode, super_access, asid)
    yield from check_valid(dut, valid, 0)

    # Test supervisor mode entry valid
    # The entry is in user mode with access
    # Ensure that user mode and valid is enabled!
    data = 0x7FFF0000000000000011
    # Ignore MSB it will be truncated
    asid = 0x7FFF
    super_mode = 1
    super_access = 1
    xwr = 0
    valid = 1
    yield from set_validator(dut, data, xwr, super_mode, super_access, asid)
    yield from check_valid(dut, valid, 0)


def test_permv():
    dut = PermissionValidator(15, 64)
    run_simulation(dut, tbench(
        dut), vcd_name="Waveforms/test_permission_validator.vcd")
    print("PermissionValidator Unit Test Success")


if __name__ == "__main__":
    test_permv()
