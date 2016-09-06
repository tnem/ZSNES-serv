# ZSNES-serv

A server to allow >2 ZSNES clients to connect to each other.

Requires:
* Python 3
* ZSNES 1.42(n)

# General usage:

Server:

* `python3 server.py`

Client:
* Start ZSNES
* click 'netplay' -> 'internet'
* uncheck 'Use udp instead of tcp'
* connect to server on port 7845
* coordinate player select across clients

# Notes:
* ZSNES on linux can take up to a minute to load a netplay saved game.  Be patient!
* When you save your game, exit ZSNES via its menu, not just clicking X to ensure a good save.

# Currently unhandled:
* Pausing
* Save states
* Probably more
