import socket,sys
import binascii
from enum import Enum
import threading
import time

import pdb

## intended to be called only during the main loop section, where we expect only:
## 0x00|0x08 - general status keepalive, always 4 bytes
## 0x02 - control packet, 4 + 6 * x bytes based on number of players
def splitBufferIntoPackets(buffer):
    firstPacket = []
    restBuffer = buffer
    
    if buffer[0] in [0x00, 0x08]:
        firstPacket = buffer[:2]
        restBuffer = buffer[2:]
    elif buffer[0] in [0xfe, 0xfd, 0x01]:
        firstPacket = buffer[:1]
        restBuffer = buffer[1:]
    elif buffer[0] == 2:
        firstPacket = buffer[:2]
        restBuffer = buffer[2:]

    while len(restBuffer) > 0 and restBuffer[0] == 128:
        firstPacket += restBuffer[:3]
        restBuffer = restBuffer[3:]

    return firstPacket,restBuffer

class ClientState():
    New = 0
    Disconnected = 1
    Connected = 2
    FoundRom = 3
    RequestSave = 4
    InGame = 5
    Paused = 6

## The idea is to have one PacketManager per client.
## Every time a client sends in a packet, it gets added to every other client's PacketManager.
## Each packetmanager then tries to determine if it can send anything along by merging together
## as many packets as possible from clients.
## It's used only for the main gameplay loop.
class PacketManager:
    def __init__(self, client):
        self.client = client

        self.receivedPackets = {}

    def minBufferLength(self):
        k,v = min(self.receivedPackets.items(), key = lambda x: len(x[1]))

        return len(v)

    def choosePacketToSend(self):
        pass
        
    def tryToSendPackets(self):
        if self.minBufferLength() == 0:
            pass
        else:

            priorityPacket = b'\x00\x00'
        
            #sendPacketForClient
            for client, packetList in self.receivedPackets.items():
                data,rest = splitBufferIntoPackets(packetList)
                self.receivedPackets[client] = rest

                if data[0] >= priorityPacket[0]:
                    priorityPacket = data

            if priorityPacket[0] == 0:
                self.client.sendToClient(bytes(priorityPacket))
            elif priorityPacket[0] == 2:
                packet = bytes(priorityPacket[:2] + self.client.manager.buildControlPacketForClient(self.client))
                self.client.sendToClient(packet)
            else:
                print("nonstandard packet: " + str(priorityPacket))

                self.client.sendToClient(bytes(priorityPacket))

            if self.minBufferLength() > 0:
                self.tryToSendPackets()
            
        
    def addPacketForClient(self, client, data):
        self.receivedPackets[client] += data

    def addClient(self, client):
        self.receivedPackets[client] = []
        
    
class ZsnesClient:
    def __init__(self, manager, id, conn, addr):
        self.conn = conn
        self.addr = addr

        self.packetManager = PacketManager(self)
        
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
        self.saveBuffer = []

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

        if self.state == ClientState.RequestSave or self.state == ClientState.FoundRom:
            print("stashing savebuffer data if necessary")
            self.saveBuffer += data
            ## end of 'sending game data' - will appear on its own if no save data is sent
            if data[-4:] == b'\x1e\xe6\xfc\x51':
                # if len(data) > 4, then save data is being sent.
                print("sending stashed savebuffer data")
                #self.manager.sendToOtherClients(self, data)
                self.state = ClientState.InGame
                self.manager.sendToOthersBuffered(self, bytes(self.saveBuffer))
                #self.manager.sendToOtherClients(self, data)

        if self.state == ClientState.Paused:
            if data[0] == 20: #set latency to second byte
                self.manager.sendToOtherClients(self, data)

            elif data[0] == 30: #start of a 1e packet
                self.state = ClientState.FoundRom
                self.msgDispatcher(data)

            elif data[0] == 0x02: # chat message in this context
                self.manager.sendToOtherClients(self, data)
                
            elif data[0] == 0xfe or data[0] == 0xfd or data[0] == 0x01:
                data,restData = splitBufferIntoPackets(data)

                self.manager.sendToOthersBuffered(self, data)
                if len(restData) > 0:
                    self.msgDispatcher(restData)

        elif self.state == ClientState.InGame:

            if data[0] == 0x00 or data[0] == 0x08: # no idea anymore - some sort of emulator state?
                data,restData = splitBufferIntoPackets(data)
                
                ## double-sending breaks sync?
                if data != self.lastNonControlPacket:
                    self.lastNonControlPacket = data
                    print(str(self) + " sent new non-control packet " + str(binascii.hexlify(data)))

                self.numPacketsRecv += 1
                #print(str(self) + " at state " + str(data[1]))
                self.emulatorState = data[1]
                lowestOthers = self.manager.lowestEmuStateOfOthers(self)

                # self.manager.sendToOthersBuffered(self, data)
                self.manager.setLoopPacket(self, data) # unneccesary? 
                # self.manager.sendPacketForClient(self)
                self.manager.handleLoopPacket(self, data)

                if len(restData) > 0:
                    self.msgDispatcher(restData)

            elif data[0] == 0xfe or data[0] == 0xfd or data[0] == 0x01:
                data,restData = splitBufferIntoPackets(data)
                self.state = ClientState.Paused

                self.manager.sendToOthersBuffered(self, data)
                    
            elif data[0] == 0xe5: # unsure, checking for doublesend
                # NOT okay to doublesend
                # just mirroring back for now, which is a brittle hacky thing to do!
                # send back only when everyone has put in their e5?

                self.manager.sendToOthersBuffered(self, data)
                # self.manager.setLoopPacket(self, data)
                # time.sleep(0.5)
                #self.manager.tryStartMainLoop()

            # add 'and if' to make sure client state is in the right state (i.e. foundRom)
            # note that if you hit 'esc' in-game to pause, 0x02 packets are chat messages again
            elif data[0] == 0x02: # in-game controls
                ## these packets are OK to have more come in than 'expected' (from the 1-1).
                #self.manager.sendToOtherClients(self, data)

                #0x80 is a 'c' for some reason. idk. seems like packet smooshing / something breaking.

                #if self == self.manager.clients[-1]:
                #    return

                # There is a heartbeat one sent out every so often,
                # but it is NOT sent if there has been an actual control packet sent.

                data,restData = splitBufferIntoPackets(data)
            
                #print("received control packet " +  str(binascii.hexlify(data)) + " from " + str(self) + " after " + str(self.numPacketsRecv) + " 0x00 packets")

                # if not data == b'\x02\x04\x80\x00\x00':
                    # print(str(data))

                ## latter part of control packets -- everything after
                ## \x02 -- 'control packet' header
                ## \x04 -- state? of emulator.  Will increment if disconnected until \x0b which is pause
                ## next 3 bytes: some combination of 'characters I'm responsible for'
                ## and 'keys I'm pressing', I think.
                ## DO NOT pad out this full length if you are not responsible for any controllers!
                ## If responsible for more than one character, you can have more than 1 set of 6 bytes.
                ## The other party may respond, but will only respond with as many as they are responsible
                ## for, which may be as little as \x02\x04 and no body.

                ## hypothesis: if you get a control packet that's NOT the length you're expecting
                ## (like you assume 'other' controls 2 players but you get a 10-byte packet)
                ## it will crash?

                ## TODO: break out various controller inputs and register them w/ the manager
                ## when an input is received, manager can determine for each other client:
                ## - how many controllers they expect 'others' to be controlling, and
                ## - what the current state of those controllers are.
                ## The header can be added on separately, we'll probably lock it to 0x04
                ## (or maybe highest of relevant clients?)

                ## Initial \x02\x00 packet is a 'zero' of everything you're responsible for I think
                ## I'm not sure what the leading \x80 is on controller inputs.
                ## The first 2 controllers per client seem to have them, and the others are just 00.
                ## 80 prefix is used if it's connected to a keyboard or something.
                ## If there are no keys assigned, it gets the 00 prefix.
                ## Maybe we can just use the 80 control prefix all the time.
            
            
                self.numPacketsRecv = 0
            
                self.controlMask = data

                #print("self.emulatorState: " + str(self.emulatorState))

                #self.sendToClient(bytes([2] + [self.emulatorState] + [128, 0, 0]))

                #if self.isLeader:
                #    self.manager.sendToFollowingClients(data)
                #else:
                #    self.manager.sendToLeaderOnce(data)

                self.manager.handleControlsFromClient(self, data)
                self.manager.setLoopPacket(self, data)
                
                self.manager.handleLoopPacket(self, data)

                # self.manager.sendPacketForClient(self)

                if len(restData) > 0:
                    self.msgDispatcher(restData)


        else:
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
                self.manager.sendToOtherClients(self, data)
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
                self.manager.sendToOthersBuffered(self, data)

            ## 0xea and 0xe9 can happen in either order, not exactly sure
            elif data[0] == 0xea: # acknowledging save file request?
                print("acknowledge file found")
                self.state = ClientState.RequestSave
                self.manager.sendToOthersBuffered(self, data)

            elif data[0] == 0xe9: # follower requesting game file?
                print(str(self) + " requesting save game file")
                self.state = ClientState.RequestSave
                self.manager.sendToOthersBuffered(self, data)

            
            
            
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
