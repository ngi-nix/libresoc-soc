#The server code
import socket
from socket import close, AF_INET, SOCK_STREAM
import sys
import select
import time

from soc.debug.jtagutils import JTAGServer, JTAGClient


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

