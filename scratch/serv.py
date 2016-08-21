
'''
    Simple socket server using threads
'''
 
import socket,sys
import binascii
from enum import Enum
 
HOST = ''
PORT = 7846
 
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
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

conn,addr = s.accept()

while 1:
    data = conn.recv(4096)

s.close()
