import socket,sys
import binascii
from enum import Enum
import threading
import time

import pdb

class ClientState():
    New = 0
    Disconnected = 1
    Connected = 2
    FoundRom = 3

    
    
class ZsnesClient:
    def __init__(self, manager, id, conn, addr):
        self.conn = conn
        self.addr = addr
        
        self.manager = manager
        self.id = id
        self.isLeader = False

        self.emulatorState = 0x00

        # b'\x02\x04\x80\x00\x00' is the 'no buttons pressed' mask,
        # but we don't actually start by sending that control packet.
        self.controlMask = b'\x02\x00\x80\x00\x00'

        self.numPacketsRecv = 0

        self.state = ClientState.New

        self.lastNonControlPacket = None

        self.packetLog = []

    def sendToClient(self, data):
        self.packetLog.append(['send', data])
        self.conn.sendall(data)

    def recvFromClient(self):
        data = self.conn.recv(4096)
        self.packetLog.append(['recv', data])
        # print("got data: " + str(binascii.hexlify(data)))

        return data

    def printPacketLog(self):
        prevPacket = None
        numTimes = 0
        
        for packet in self.packetLog:
            if packet == prevPacket:
                numTimes += 1
            else:
                print(str(numTimes) + " instance of " + str(prevPacket))
                prevPacket = packet
                numTimes = 1

        print(str(numTimes) + " instance of " + str(prevPacket))

        
    def connect(self, in_data):
        data = in_data

        #pdb.set_trace()

        ## This should be the initial connection string
        connVersion = str(int(data[3:6].decode("ascii")) / 100)
        print("client using version " + connVersion)
        soundOn = data[7]
        CNetType = data[8] ## unsure, seems to always be 1

        self.sendToClient(b'ID\xde142 \x01\x01') # we're always version 1.42!

        data = self.recvFromClient() # this is always b'\x01' ?
        self.sendToClient(b'\x01') # unsure why necessary. maybe a status code?

    def claimPlayer(self, playerNum):
        conversion = {1: b'\x03',
                      2: b'\x04',
                      3: b'\x05',
                      4: b'\x06',
                      5: b'\x07'}

        self.sendToClient(conversion[playerNum])

    def sendChatMessage(self, msg):
        msg = b'\x02' + msg.encode("ascii") + b'\x00'
        self.sendToClient(msg)

    def startGame(self, fileName):
        pass

    def msgDispatcher(self, init_data):
        data = init_data

        if data[0:2] == b'ID': # client connection
            print("client connecting")
            self.connect(data)
            self.state = ClientState.Connected

            self.manager.syncNewClientPlayers(self)
            
        elif all(x == 0xff for x in data) or data == b'': # client quitting / socket empty
            print("client exiting!")
            self.state = ClientState.Disconnected
            self.manager.removeClient(self)

        elif data[0] == 0x02 and self.state == ClientState.Connected: # sending chat message
            "Chat messages are encoded as [0x02 string_of_message 0x00]"
            msg = data[1:-1].decode("ascii")
            self.manager.sendToOtherClients(self, data)
            print("receiving chat message: " + msg)

        elif data[0] in [0x03, 0x04, 0x05, 0x06, 0x07] and \
             self.state == ClientState.Connected: # player assignment message
            self.manager.claimPlayer(self, (data[0] - 2))

        elif data[0] == 0x14: # setting latency
            self.manager.sendToOtherClients(self, data)

        elif data[0] == 0x08: # setting back buffer
            self.manager.sendToOtherClients(self, data)

        ## save data might need to be modified a little to work 3-way
        ## currently neutered (except none), and it must be set manually.
        elif data[0] == 0x29: # wants to use local save data
            #self.manager.sendToOtherClients(self, data)
            pass

        elif data[0] == 0x2a: # wants to use remote save data
            #self.manager.sendToOtherClients(self, data)
            pass

        elif data[0] == 0x32: # wants to use no save data
            self.manager.sendToOtherClients(self, data)
            
        ## starting game management

        elif data[0] == 0x0a: # filename of rom to start
            print("attempting to launch game: " + data[1:-1].decode("ascii"))
            self.manager.sendToOtherClients(self, data)
            self.isLeader = True
            self.state = ClientState.FoundRom

        elif data[0] == 0x0b: # file found on remote
            print("ROM found on remote successfully")
            self.state = ClientState.FoundRom

            if self.manager.allClientsAre(ClientState.FoundRom): # when all remotes are OK
                self.manager.sendToLeaderClient(b'\x0b')

        elif data[0] == 0x0d: # file not found on remote
            print("file not found on remote")
            self.manager.sendToOtherClients(self, data)

        elif data[0] == 0xea: # acknowledging file found from leader? 
            print("acknowledge file found")
            self.manager.sendToOtherClients(self, data)

        elif data[0] == 0xe9: # follower requesting game file?
            self.state = ClientState.RequestSave

        ## in-game

        elif data[0] == 0x00: # no idea anymore - some sort of emulator state?
            ## double-sending breaks sync?
            if data != self.lastNonControlPacket:
                self.lastNonControlPacket = data
                print(str(self) + " sent new non-control packet " + str(binascii.hexlify(data)))

            self.numPacketsRecv += 1
            #print(str(self) + " at state " + str(data[1]))
            self.emulatorState = data[1]
            lowestOthers = self.manager.lowestEmuStateOfOthers(self)
            #self.sendToClient(bytes([0] + [lowestOthers]))
            #self.sendToClient(data)
            self.manager.sendToOthersBuffered(self, data)
            #self.manager.sendToOtherClients(self, data)
            #self.manager.sendToOtherClients(self, data)
            #self.manager.sendToOthersBuffered(self, data)

        elif data == b'\x1e\xe6\xfc\x51': # unsure, part of initialization,
            # but ok to receive more than one
            # trying just sending one to make packet log more similar to 1-on-1
            #self.manager.sendToOtherClients(self, data)
            self.manager.sendToOthersBuffered(self, data)
            #self.manager.sendToOtherClients(self, data)

        elif data[0] == 0xe5: # unsure, checking for doublesend
            # NOT okay to doublesend
            # just mirroring back for now, which is a brittle hacky thing to do!
            # send back only when everyone has put in their e5?
            #time.sleep(.5)
            #self.sendToClient(data)
            self.manager.sendToOthersBuffered(self, data)

        # add 'and if' to make sure client state is in the right state (i.e. foundRom)
        # note that if you hit 'esc' in-game to pause, 0x02 packets are chat messages again
        elif data[0] == 0x02: # in-game controls
            ## these packets are OK to have more come in than 'expected' (from the 1-1).
            #self.manager.sendToOtherClients(self, data)

            #0x80 is a 'c' for some reason. idk.

            #if self == self.manager.clients[-1]:
            #    return

            # There is a heartbeat one sent out every so often,
            # but it is NOT sent if there has been an actual control packet sent.

            
            print("received control packet " +  str(binascii.hexlify(data)) + " from " + str(self) + " after " + str(self.numPacketsRecv) + " 0x00 packets")

            if not data == b'\x02\x04\x80\x00\x00':
                print("NOT standard control packet")

            ## latter part of control packets -- everything after
            ## \x02 -- 'control packet' header
            ## \x04 -- state? of emulator.  Will increment if disconnected until \x0b which is pause
            ## next 6 bytes: some combination of 'characters I'm responsible for'
            ## and 'keys I'm pressing', I think.
            ## DO NOT pad out this full length if you are not responsible for any controllers!
            
            self.numPacketsRecv = 0
            
            self.controlMask = data

            #print("self.emulatorState: " + str(self.emulatorState))

            #self.sendToClient(bytes([2] + [self.emulatorState] + [128, 0, 0]))

            #self.manager.sendToOtherClients(self, data)
            #if data == b'\x02\x00\x80\x00\x00' and self.isLeader:
            #    self.sendToClient(data)
            #    self.manager.sendToOtherClients(self, data)
            #elif self.isLeader:
                #self.manager.sendToOthersBuffered(self, data):
                #self.manager.distributeCurrentKeypresses(self)

            if self.isLeader:
                self.manager.sendToFollowingClients(data)
            else:
                self.manager.sendToLeaderOnce(data)
            
            #if self != self.manager.clients[-1]:
            #    self.manager.sendToOtherClients(self, data)
            
        else: # debugging catchall
            print(str(self) + " sent new unknown packet " + str(binascii.hexlify(data)))
            self.manager.sendToOtherClients(self, data)
            #self.manager.sendToOthersBuffered(self, data)

            

    def serve(self):
        #self.connect()

        while self.state != ClientState.Disconnected:
            data = self.recvFromClient()
            self.msgDispatcher(data)
            #print("clientState now: " + str(self.state))


        self.conn.close()
