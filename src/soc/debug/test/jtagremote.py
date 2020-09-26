#The server code
import socket
from socket import close, AF_INET, SOCK_STREAM
import sys
import select
import time


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


def test_clientserver_jtagremote():
    s = JTAGServer()
    c = JTAGClient()
    s.get_connection()

    c.jtagremote_client_send((1, 0, 1))
    while True:
        resp = s.jtagremote_server_recv(1)
        if resp is not None:
            print ("response", resp)
            break

    while True:
        resp = s.jtagremote_server_recv(1)
        if resp is not None:
            print ("response", resp)
            break

    tdo = c.jtagremote_client_recv()
    print ("client recv", tdo)

    s.close()
    c.close()


def test_clientserver():
    s = JTAGServer()
    c = JTAGClient()
    s.get_connection()

    c.send(str.encode("h"))
    while True:
        resp = s.get_data()
        if resp is not None:
            print ("response", resp)
            break
    s.close()
    c.close()


if __name__ == '__main__':
    #test_clientserver()
    test_clientserver_jtagremote()

