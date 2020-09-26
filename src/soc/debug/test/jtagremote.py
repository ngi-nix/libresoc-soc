#The server code
import socket
from socket import close, AF_INET, SOCK_STREAM
import sys
import select
import time


def server():
    HOST = '' 
    PORT = 44853
    s = socket.socket(AF_INET, SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
    s.bind((HOST, PORT))
    s.listen(1) #only needs to receive one connection (the client)
    return s

def get_connection(s):
    r, w, e = select.select( [s], [], [], 0)
    for sock in r:
        #incoming message from remote server
        if sock == s:
            conn, addr = s.accept() #accepts the connection
            print("Connected by: ", addr) #prints the connection
            conn.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
            return conn
    return None


def get_data(s, length=1024, timeout=None):
    r, w, e = select.select( [s], [], [], timeout)

    for sock in r:
        #incoming message from remote server
        if sock == s:
            return sock.recv(length)
    return None

def client():
    HOST = 'localhost'
    PORT = 44853
    s = socket.socket(AF_INET, SOCK_STREAM)
    s.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
    s.connect((HOST, PORT))
    return s


def jtagremote_client_send(c, to_send):
    # encode tck, tms and tdi as number from 0-7
    tck, tms, tdi = to_send
    data = 0
    if tdi: data |= 1
    if tms: data |= 2
    if tck: data |= 4
    data = chr(ord('0') + data)
    c.sendall(str.encode(data))
    print ("jtagremote_client_send", data)
    # now read tdo
    c.sendall(str.encode('R'))


def jtagremote_client_recv(c):
    data = get_data(c, 1) # read 1 byte, blocking
    print ("client recv", data)
    data = bytes.decode(data)
    return ord(data) - ord('0') # subtract ASCII for "0" to give value 0 or 1


def jtagremote_server_recv(s, tdo):
    data = get_data(s, 1, 0) # read 1 byte, non-blocking
    if data is None:
        return None # no data read
    data = bytes.decode(data)
    print ("jtagremote_server_recv", data)
    # request to read TDO
    if data == 'R':
        s.sendall(str.encode(chr(ord('0') + tdo)))
        return [] # no data
    # decode tck, tms, tdi
    data = ord(data) - ord('0')
    # encode tck, tms and tdi as number from 0-7
    tdi = 1 if (data & 1) else 0
    tms = 1 if (data & 2) else 0
    tck = 1 if (data & 3) else 0

    return (tck, tms, tdi)


def test_clientserver_jtagremote():
    s = server()
    c = client()
    sc = get_connection(s)

    jtagremote_client_send(c, (1, 0, 1))
    while True:
        resp = jtagremote_server_recv(sc, 1)
        if resp is not None:
            print ("response", resp)
            break

    while True:
        resp = jtagremote_server_recv(sc, 1)
        if resp is not None:
            print ("response", resp)
            break

    tdo = jtagremote_client_recv(c)
    print ("client recv", tdo)

    s.close()
    sc.close()
    c.close()


def test_clientserver():
    s = server()
    c = client()
    sc = get_connection(s)

    c.sendall(str.encode("h"))
    while True:
        resp = get_data(sc)
        if resp is not None:
            print ("response", resp)
            break
    s.close()
    sc.close()
    c.close()


if __name__ == '__main__':
    #test_clientserver()
    test_clientserver_jtagremote()

