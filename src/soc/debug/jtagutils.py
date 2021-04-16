#The server code
import socket
from socket import close, AF_INET, SOCK_STREAM
import sys
import select
import time


def client_sync(dut):
    tck = yield dut.cbus.tck
    tms = yield dut.cbus.tms
    tdi = yield dut.cbus.tdi
    dut.c.jtagremote_client_send((tck, tms, tdi))
    #print ("about to client recv")
    while True:
        tdo = dut.c.jtagremote_client_recv(timeout=0)
        if tdo is not None:
            break
        yield
    yield dut.cbus.tdo.eq(tdo)


def tms_state_set(dut, bits):
    for bit in bits:
        yield dut.cbus.tms.eq(bit)
        yield from client_sync(dut)
        yield dut.cbus.tck.eq(1)
        yield from client_sync(dut)
        yield
        yield dut.cbus.tck.eq(0)
        yield from client_sync(dut)
        yield
        yield from client_sync(dut)
    yield dut.cbus.tms.eq(0)
    yield from client_sync(dut)


def tms_data_getset(dut, tms, d_len, d_in=0):
    res = 0
    yield dut.cbus.tms.eq(tms)
    for i in range(d_len):
        tdi = 1 if (d_in & (1<<i)) else 0
        yield dut.cbus.tck.eq(1)
        yield from client_sync(dut)
        res |= (1<<i) if (yield dut.cbus.tdo) else 0
        yield
        yield from client_sync(dut)
        yield dut.cbus.tdi.eq(tdi)
        yield dut.cbus.tck.eq(0)
        yield from client_sync(dut)
        yield
        yield from client_sync(dut)
    yield dut.cbus.tms.eq(0)
    yield from client_sync(dut)

    return res


def jtag_set_reset(dut):
    yield from tms_state_set(dut, [1, 1, 1, 1, 1])

def jtag_set_shift_dr(dut):
    yield from tms_state_set(dut, [1, 0, 0])

def jtag_set_shift_ir(dut):
    yield from tms_state_set(dut, [1, 1, 0])

def jtag_set_run(dut):
    yield from tms_state_set(dut, [0])

def jtag_set_idle(dut):
    yield from tms_state_set(dut, [1, 1, 0])


def jtag_set_ir(dut, addr):
    yield from jtag_set_run(dut)
    yield from jtag_set_shift_ir(dut)
    result = yield from tms_data_getset(dut, 0, dut._ir_width, addr)
    yield from jtag_set_idle(dut)
    return result


def jtag_set_get_dr(dut, d_len, d_in=0):
    yield from jtag_set_shift_dr(dut)
    result = yield from tms_data_getset(dut, 0, d_len, d_in)
    yield from jtag_set_idle(dut)
    return result

def jtag_read_write_reg(dut, addr, d_len, d_in=0):
    yield from jtag_set_ir(dut, addr)
    return (yield from jtag_set_get_dr(dut, d_len, d_in))


def jtag_srv(dut):
    while not dut.stop:
        # loop and receive data from client
        tdo = yield dut.bus.tdo
        #print ("server tdo data", tdo)
        data = dut.s.jtagremote_server_recv(tdo)
        #print ("server recv data", data)
        if not data:
            yield
            continue
        tck, tms, tdi = data
        yield dut.bus.tck.eq(tck)
        yield dut.bus.tms.eq(tms)
        yield dut.bus.tdi.eq(tdi)
        yield
    print ("jtag srv stopping")


def get_data(s, length=1024, timeout=None):
    r, w, e = select.select( [s], [], [], timeout)

    for sock in r:
        #incoming message from remote server
        if sock == s:
            return sock.recv(length)
    return None

class JTAGServer:
    def __init__(self, debug=False):
        self.debug = debug
        HOST = ''
        PORT = 44853
        s = socket.socket(AF_INET, SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
        s.bind((HOST, PORT))
        s.listen(1) #only needs to receive one connection (the client)
        self.s = s
        self.conn = None

    def close(self):
        self.s.close()
        if self.conn:
            self.conn.close()

    def get_connection(self, timeout=0):
        r, w, e = select.select( [self.s], [], [], timeout)
        for sock in r:
            #incoming message from remote server
            if sock == self.s:
                conn, addr = self.s.accept() #accepts the connection
                if self.debug:
                    print("Connected by: ", addr) #prints the connection
                conn.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
                self.conn = conn
                return conn
        return None

    def get_data(self, length=1024, timeout=None):
        return get_data(self.conn, length, timeout)

    def send(self, data):
        return self.conn.sendall(data)

    def jtagremote_server_recv(self, tdo):
        data = self.get_data(1, 0) # read 1 byte, non-blocking
        if data is None:
            return None # no data read
        data = bytes.decode(data)
        if self.debug:
            print ("jtagremote_server_recv", data)
        # request to read TDO
        if data == 'R':
            self.send(str.encode(chr(ord('0') + tdo)))
            return [] # no data
        # decode tck, tms, tdi
        data = ord(data) - ord('0')
        # encode tck, tms and tdi as number from 0-7
        tdi = 1 if (data & 1) else 0
        tms = 1 if (data & 2) else 0
        tck = 1 if (data & 4) else 0

        return (tck, tms, tdi)



class JTAGClient:
    def __init__(self, debug=False):
        self.debug = debug
        HOST = 'localhost'
        PORT = 44853
        s = socket.socket(AF_INET, SOCK_STREAM)
        s.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
        s.connect((HOST, PORT))
        self.s = s

    def close(self):
        self.s.close()

    def get_data(self, length=1024, timeout=None):
        return get_data(self.s, length, timeout)

    def send(self, data):
        return self.s.sendall(data)

    def jtagremote_client_send(self, to_send):
        # encode tck, tms and tdi as number from 0-7
        tck, tms, tdi = to_send
        data = 0
        if tdi: data |= 1
        if tms: data |= 2
        if tck: data |= 4
        data = chr(ord('0') + data)
        self.send(str.encode(data))
        if self.debug:
            print ("jtagremote_client_send", data)
        # now read tdo
        self.send(str.encode('R'))


    def jtagremote_client_recv(self, timeout=None):
        data = self.get_data(1, timeout) # read 1 byte, blocking
        if data is None:
            return None
        if self.debug:
            print ("client recv", data)
        data = bytes.decode(data)
        return ord(data) - ord('0') # subtract ASCII for "0" to give 0 or 1


