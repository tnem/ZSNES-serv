
'''
    Simple socket server using threads
'''
 
import socket,sys
import binascii
from enum import Enum
import threading

from zsnesClient import ZsnesClient, ClientState
from zsnesClientManager import ZsnesClientManager

import pdb
 
HOST = ''
PORT = 7845
 
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
print('Socket created')
 
#Bind socket to local host and port
try:
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) #used to allow easy re-starting of connection during debug
    s.bind((HOST, PORT))
except socket.error as msg:
    print('Bind failed. Error Code : ' + str(msg[0]) + ' Message ' + msg[1])
    sys.exit()
     
print('Socket bind complete')
 
#Start listening on socket
s.listen(10)
print('Socket now listening')

manager = ZsnesClientManager(s)

threading.Thread(target = manager.listenForClients).start()
#manager.listenForClients()

#conn,addr = s.accept()
#client = ZsnesClient(conn,addr)

#res = client.serve()

#now keep talking with the client
# while 1:
#    #wait to accept a connection - blocking call
#    conn, addr = s.accept()
#    print 'Connected with ' + addr[0] + ':' + str(addr[1])
#    client = ZsnesClient(conn,addr)
#    client.connect()
     
#s.close()
