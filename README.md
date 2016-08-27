# ZSNES-serv

A server to allow >2 ZSNES clients to connect to each other.

Still has lots of broken parts.  Not intended for general use.

Requires:
* ZSNES 1.42(n) (for testing)

# General usage:

Server:

* `python3 server.py`

Client:
* Start ZSNES
* click 'netplay' -> 'internet'
* uncheck 'Use udp instead of tcp'
* connect to server on port 7845
* coordinate player select across clients
* when all clients are connected, select 'Save Data: None'
