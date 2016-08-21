
'''
    Simple socket client using threads
'''
 
import socket,sys
import binascii
from enum import Enum
 
HOST = ''
PORT = 7846
 
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
print('Socket created')
 
s.connect(("localhost", PORT))
