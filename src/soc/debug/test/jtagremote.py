#The server code
import socket
from socket import close, AF_INET, SOCK_STREAM
import sys
import select
import time


def server():
    HOST = '' 
    PORT = 9999
    s = socket.socket(AF_INET, SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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
            return conn
    return None

def get_data(s):
    r, w, e = select.select( [s], [], [])

    for sock in r:
        #incoming message from remote server
        if sock == s:
            return sock.recv(1024)
    return None


def client():
    HOST = 'localhost'
    PORT = 9999
    s = socket.socket(AF_INET, SOCK_STREAM)
    s.connect((HOST, PORT))
    return s

if __name__ == '__main__':

    s = server()
    c = client()
    sc = get_connection(s)

    c.send(str.encode("hello"))
    while True:
        resp = get_data(sc)
        if resp is not None:
            print ("response", resp)
            break
    s.close()
    sc.close()
    c.close()

