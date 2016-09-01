import socket,sys,binascii,threading
import pdb
import time

from zsnesClient import ZsnesClient, ClientState

## need to track which client is the 'leader' and which ones are 'followers' for launching game

foo = [bytes([0, 2]), bytes([1, 0]), bytes([5, 1])]

def bitwiseOr(x, y):
    newBits = []
    for a, b in zip(x, y):
        newBits.append(a|b)

    return bytes(newBits)

def bitwiseOrSeq(xs):
    temp = bytes(5)

    for x in xs:
        temp = bitwiseOr(temp, x)

    return temp

class ZsnesClientManager:
    def __init__(self, sock):
        self.clients = []
        self.sock = sock

        self.playerAssignments = {}

        self.bufLead = []
        self.bufFoll = []

        self.loopPackets = {}

        self.totalKeyPresses = {}

    def setLoopPacket(self, client, data):
        self.loopPackets[client] = data

    def allOtherClients(self, client):
        return [c for c in self.clients if c != client]
    
    def lowestEmuStateOfOthers(self, client):
        otherClients = self.allOtherClients(client)
        return min([client.emulatorState for client in otherClients])

    def playerArrayForClient(self, client):
        return [k for k,v in self.playerAssignments.items() if v == client]

    ## note - this just builds the 'control' part of the packet.
    ## it does not include the leading dispatch or state.
    def buildControlPacketForClient(self, client):
        packet = []
        clientControllers = self.playerArrayForClient(client)
        orderedControls = [v for k,v in self.totalKeyPresses.items() if k not in clientControllers]

        ## get control packets for every controller not controlled by client
        ## must be sorted
        for control in orderedControls:
            packet += b'\x80'
            packet += control

        return packet
            
    
    ## Uses the current state of keypresses in self.totalKeyPresses
    ## and sends out an update packet to every other client of the 'other's state
    def sendControlsToOthers(self, sendingClient):
        oclients = self.allOtherClients(sendingClient)

        for client in oclients:
            packet = bytes([2, sendingClient.emulatorState] + self.buildControlPacketForClient(client))
            #print("sending control packet: " + str(packet) + " to client: " + str(client))
            client.sendToClient(packet)
        

    ## when we receive a control message from a client, send it here.
    ## The manager is required to coordinate what clients have which controllers.
    ## Once the manager knows the controller state of every client,
    ## they can send out the corresponding 'other' control packets.
    def handleControlsFromClient(self, client, data):
        controls = data[2:]
        clientControls = self.playerArrayForClient(client)

        # print("controls: " + str(controls))

        # each control packet is 3 bytes
        for i in range(int(len(controls) / 3)):
            # ignore byte 0, it's just 'controller active'?
            self.totalKeyPresses[clientControls[i]] = controls[1 + i*3 : 3 + i*3]

        print("set totalKeyPresses: " + str(self.totalKeyPresses))

        #self.sendControlsToOthers(client)
            
    def sendPacketForClient(self, origClient):
        otherClients = self.allOtherClients(origClient)

        priorityPacket = b'\x00\x00'

        for sclient in otherClients:
            # print("xx: " + str(self.loopPackets))
            if sclient in self.loopPackets and self.loopPackets[sclient][0] >= priorityPacket[0]:
                priorityPacket = self.loopPackets[sclient]

        if priorityPacket[0] == 0: ## todo: handle different client states - 4, 5, 6, etc
            origClient.sendToClient(priorityPacket)
            # pass
        elif priorityPacket[0] == 2:
            # print("priorityPacket: " + str(priorityPacket))
            # print("otherClients: " + str(otherClients))
            # print("loopPackets: " + str(self.loopPackets))
            # print("loopPacket of " + str(origClient) + " : " + str(self.loopPackets[origClient]))
            # print("loopPacket of " + str(otherClients[0]) + " : " + str(self.loopPackets[otherClients[0]]))
            packet = bytes([2, origClient.emulatorState] + self.buildControlPacketForClient(origClient))
            # print("sending control packet: " + str(packet) + " to client: " + str(origClient))
            origClient.sendToClient(packet)
            # pass
        elif priorityPacket[0] == 229: ## 0xe5 starter packet
            origClient.sendToClient(b'\xe5')

    ## zsnes just sends a packet EVERY 0.033 seconds, and it is:
    # - A modified control packet, if the keys have changed since the last packet
    # - a 'current state' control packet if the keys haven't changed since the last control packet
    # - 0x0004 (or whatever client state is) otherwise.
        
    def sendToLeaderOnce(self, data):
        self.bufLead.append(data)
        
        if self.bufLead.count(data) == len(self.getFollowingClients()):
            self.bufLead = [x for x in self.bufLead if x != data]
            self.sendToLeaderClient(data)

    ## deprecated I think, along with bufLead and bufFoll.
    def sendToOthersBuffered(self, client, data):
        if client.isLeader:
            self.sendToFollowingClients(data)
        else:
            self.sendToLeaderOnce(data)
        
    def addClient(self, conn, addr):
        newClient = ZsnesClient(self, len(self.clients), conn, addr)
        self.clients.append(newClient)

        return newClient

    def removeClient(self, client):
        self.clients.remove(client)
        self.playerAssignments = {k:v for k,v in self.playerAssignments.items() if v != client}

    def listenForClients(self):
        while True:
            conn,addr = self.sock.accept()
            print("manager got new client on thread: " + str(threading.currentThread()))
            newClient = self.addClient(conn,addr)
            
            newThread = threading.Thread(target = newClient.serve)
            newThread.start()

    def messageAllClients(self, msg):
        for client in self.clients:
            client.sendChatMessage(msg)

    def allClientsAre(self, state):
        return all(client.state == state for client in self.clients)

    def getLeadingClient(self):
        for client in self.clients:
            if client.isLeader:
                return client

        return None
    #manager.clients[0].sendToClient(b'\x04\x76\x00')
    #manager.clients[0].sendToClient(b'\x04\x02\x04\x80\x00\x80')
    #manager.clients[0].sendToClient(b'\x02\x04\x80\x00\x80')
    
    def getFollowingClients(self):
        ret = []
        for client in self.clients:
            if not client.isLeader:
                ret.append(client)

        return ret

    def allClients(self):
        return self.clients
            
    def sendToAllClients(self, data):
        for client in self.clients:
            client.sendToClient(data)

    def sendToLeaderClient(self, data):
        self.getLeadingClient().sendToClient(data)

    def sendToFollowingClients(self, data):
        self.sendToClientList(self.getFollowingClients(), data)

    def sendToClientList(self, clients, data):
        for client in clients:
            client.sendToClient(data)
            
    def sendToOtherClients(self, client, data):
        for cl in self.clients:
            if cl != client:
                cl.sendToClient(data)

    ## player controller management
    def claimPlayer(self, client, playerNum):
        "For claiming or unclaiming a player spot"
        print("request from client: " + str(client))
        if playerNum in self.playerAssignments: # if that player is already assigned
            if client == self.playerAssignments[playerNum]: # if they are assigned to client
                self.playerAssignments.pop(playerNum)
                self.totalKeyPresses.pop(playerNum)
                for c in self.allOtherClients(client):
                    c.claimPlayer(playerNum)
            else: # player is assigned, but not to the one selecting it
                time.sleep(.5)
                client.claimPlayer(playerNum)
                client.sendChatMessage("player is assigned to someone else, blocking")
        else:
            self.playerAssignments[playerNum] = client
            self.totalKeyPresses[playerNum] = b'\x00\x00'
            for c in self.allOtherClients(client):
                c.claimPlayer(playerNum)

        print(self.playerAssignments)

    def syncNewClientPlayers(self, client):
        client.sendChatMessage("Don't click Xs in player select, things can get out of sync")
        client.claimPlayer(1)
        if not 2 in self.playerAssignments:
            # starts with 1 X'd out and 2 checked, so free 1 and assign 2 properly
            self.playerAssignments[2] = client
            self.totalKeyPresses[2] = b'\x00\x00'
        else:
            client.sendChatMessage("Please un-check player 2 and ignore the resulting error")
