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

    def distributeCurrentKeypresses(self, client):
        "every other client needs the & of keymasks belonging to non-them clients."
        for nonSubmittingClient in self.allOtherClients(client):
            otherKeymasks = [c.controlMask for c in self.allOtherClients(nonSubmittingClient)]
            resultingMask = bitwiseOrSeq(otherKeymasks)

            print("sending control packet " + str(binascii.hexlify(resultingMask)) + " to " + str(nonSubmittingClient))
            nonSubmittingClient.sendToClient(bitwiseOrSeq(otherKeymasks))
            
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
    
    def allOtherClients(self, client):
        return [c for c in self.clients if c != client]

    def lowestEmuStateOfOthers(self, client):
        otherClients = self.allOtherClients(client)
        return min([client.emulatorState for client in otherClients])

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
                for c in self.allOtherClients(client):
                    c.claimPlayer(playerNum)
            else: # player is assigned, but not to the one selecting it
                time.sleep(.5)
                client.claimPlayer(playerNum)
                client.sendChatMessage("player is assigned to someone else, blocking")
        else:
            self.playerAssignments[playerNum] = client
            for c in self.allOtherClients(client):
                c.claimPlayer(playerNum)

        print(self.playerAssignments)

    def syncNewClientPlayers(self, client):
        client.sendChatMessage("Don't click Xs in player select, things can get out of sync")
        client.claimPlayer(1)
        if not 2 in self.playerAssignments:
            # starts with 1 X'd out and 2 checked, so free 1 and assign 2 properly
            self.playerAssignments[2] = client
        else:
            client.sendChatMessage("Please un-check player 2 and ignore the resulting error")
