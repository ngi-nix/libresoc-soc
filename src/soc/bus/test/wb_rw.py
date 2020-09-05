"""Wishbone read/write utility routines
"""


def wb_write(bus, addr, data, sel=True):

    # write wb
    yield bus.we.eq(1)
    yield bus.cyc.eq(1)
    yield bus.stb.eq(1)
    yield bus.sel.eq(0b1111 if sel else 0b1) # 32-bit / 8-bit
    yield bus.adr.eq(addr)
    yield bus.dat_w.eq(data)

    # wait for ack to go high
    while True:
        ack = yield bus.ack
        print ("ack", ack)
        if ack:
            break
        yield # loop until ack
        yield bus.stb.eq(0) # drop stb so only 1 thing into pipeline

    # leave cyc/stb valid for 1 cycle while writing
    yield

    # clear out before returning data
    yield bus.cyc.eq(0)
    yield bus.stb.eq(0)
    yield bus.we.eq(0)
    yield bus.adr.eq(0)
    yield bus.sel.eq(0)
    yield bus.dat_w.eq(0)


def wb_read(bus, addr, sel=True):

    # read wb
    yield bus.cyc.eq(1)
    yield bus.stb.eq(1)
    yield bus.we.eq(0)
    yield bus.sel.eq(0b1111 if sel else 0b1) # 32-bit / 8-bit
    yield bus.adr.eq(addr)

    # wait for ack to go high
    while True:
        ack = yield bus.ack
        print ("ack", ack)
        if ack:
            break
        yield # loop until ack
        yield bus.stb.eq(0) # drop stb so only 1 thing into pipeline

    # get data on same cycle that ack raises
    data = yield bus.dat_r

    # leave cyc/stb valid for 1 cycle while reading
    yield

    # clear out before returning data
    yield bus.cyc.eq(0)
    yield bus.stb.eq(0)
    yield bus.we.eq(0)
    yield bus.adr.eq(0)
    yield bus.sel.eq(0)
    return data

