#!/usr/bin/python

# This script creates a .click file which can then be run using the click router.
# it requires that you have installed the OdinAgent within your click installation

# see https://github.com/lalithsuresh/odin for more details

#About the driver patch see:
#https://github.com/lalithsuresh/odin-driver-patches/blob/master/ath9k/ath9k-bssid-mask.patch

import sys

if (len(sys.argv) != 7):
    print 'Usage:'
    print ''
    print '%s <AP_CHANNEL> <QUEUE_SIZE> <HW_ADDR> <ODIN_MASTER_IP> <ODIN_MASTER_PORT> <DEBUGFS_FILE>' %(sys.argv[0])
    print ''
    print 'AP_CHANNEL: it must be the same where mon0 of the AP is placed'
    print 'QUEUE_SIZE: you can use the size 50'
    print 'HW_ADDR: the MAC of the wireless interface mon0 of the AP. e.g. 74-F0-6E-20-D4-74'
    print 'ODIN_MASTER_IP is the IP of the openflow controller where Odin master is running'
    print 'ODIN_MASTER_PORT should be 2819 by default'
    print 'DEBUGFS_FILE is the path of the bssid_extra file created by the ath9k patch'	
    print '             it can be /sys/kernel/debug/ieee80211/phy0/ath9k/bssid_extra'
    print ''
    print 'Example:'
    print '$ python %s 6 50 E8:DE:27:F7:02:16 192.168.1.2 2819 /sys/kernel/debug/ieee80211/phy0/ath9k/bssid_extra > agent.click' %(sys.argv[0])
    print ''
    print 'and then run the .click file you have generated'
    print 'click$ ./bin/click agent.click'
    sys.exit(0)

AP_UNIQUE_IP = "192.168.1.5"				# IP address of the wlan0 interface of the router where Click runs (in monitor mode). It seems it does not matter.
MASK = "24"
seq = (AP_UNIQUE_IP,"/",MASK)
#AP_UNIQUE_IP_WITH_MASK = ''.join(seq)		# join the AP_UNIQUE_IP and the mask
AP_UNIQUE_BSSID = "E8:DE:27:F7:02:16"		# MAC address of the wlan0 interface of the router where Click runs (in monitor mode). It seems it does not matter.
AP_CHANNEL = sys.argv[1]
QUEUE_SIZE = sys.argv[2]
HW_ADDR = sys.argv[3]		# not needed ??
ODIN_MASTER_IP = sys.argv[4]
ODIN_MASTER_PORT = sys.argv[5]
DEBUGFS_FILE = sys.argv[6]

DEFAULT_CLIENT_MAC = "E8:DE:27:F7:02:16"	# invented and not used
NETWORK_INTERFACE_NAMES = "mon"				# beginning of the network interface names in monitor mode. e.g. mon
TAP_INTERFACE_NAME = "ap"					# name of the TAP device that Click will create in the 
STA_IP = "192.168.1.11"						# IP address of the STA in the LVAP tuple. It only works for a single client without DHCP
STA_MAC = "74:F0:6D:20:D4:74"				# MAC address of the STA in the LVAP tuple. It only works for a single client without DHCP

#the IP address of the Access Point.
DEFAULT_GW = "192.168.1.5"

print '''
// This is the scheme:
//
//            TAP interface 'ap' in the machine that runs Click
//             | ^
// from host   | |   to host
//             v |
//            click
//             | ^
// to device   | |   to device 
//             V |
//            'mon0' interface in the machine that runs Click. Must be in monitor mode
//

// call OdinAgent::configure to create and configure an Odin agent:
odinagent::OdinAgent(HWADDR %s, RT rates, CHANNEL %s, DEFAULT_GW %s, DEBUGFS %s)
''' % (HW_ADDR, AP_CHANNEL, DEFAULT_GW, DEBUGFS_FILE )

print '''
// send a ping to odinsocket every 2 seconds ??
TimedSource(2, "ping\n")->  odinsocket::Socket(UDP, %s, %s, CLIENT true)
''' % (ODIN_MASTER_IP, ODIN_MASTER_PORT)


print '''
// output 3 of odinagent goes to odinsocket
odinagent[3] -> odinsocket

rates :: AvailableRates(DEFAULT 24 36 48 108);	// wifi rates

control :: ControlSocket("TCP", 6777);
chatter :: ChatterSocket("TCP", 6778);
'''
# ControlSocket and ChatterSocket are Click's remote control elements.
#http://piotrjurkiewicz.pl/files/bsc-dissertation.pdf

# Controlsocket: Communication with the Click application at user level is provided by a 
#TCP/IP based protocol. The user declares it in a configuration file, just like any 
#other element. However, ControlSocket does not process packets itself, so it is not 
#connected with other elements. 
# ControlSocket opens a socket and starts listening for connections.
#When a connection is opened, the server responds by stating its protocol version
#number. After that client can send commands to the Click router. The "server"
#(that is, the ControlSocket element) speaks a relatively simple line-based protocol.
#Commands sent to the server are single lines of text; they consist of words separated
#by spaces

# ChatterSocket opens a chatter socket that allows clients to receive copies 
#of router chatter traffic. The "server" (that is, the ChatterSocket element) 
#simply echoes any messages generated by the router configuration to any 
#existing clients.

print '''
// ----------------Packets going down (AP to STA)
// I don't want the ARP requests from the AP to the stations to go to the network device
//so click is in the middle and answers the ARP to the host on behalf of the station
//'ap' is a Linux tap device which is instantiated by Click in the machine.
//FromHost reads packets from 'ap'

// The arp responder configuration here doesnt matter, odinagent.cc sets it according to clients

FromHost(%s, HEADROOM 50)
  -> fhcl :: Classifier(12/0806 20/0001, -)
				// 12 means the 12th byte of the eth frame (i.e. ethertype)
				// 0806 is the ARP ethertype, http://en.wikipedia.org/wiki/EtherType
				// 20 means the 20th byte of the eth frame, i.e. the 6th byte of the ARP packet: 
				// "Operation". It specifies the operation the sender is performing: 1 for request, 2 for reply.
  -> fh_arpr :: ARPResponder(%s %s) 	// looking for an STA's ARP: Resolve STA's ARP
  -> ARPPrint("Resolving client's ARP by myself")
  -> ToHost(%s)
''' % (TAP_INTERFACE_NAME, STA_IP, STA_MAC, TAP_INTERFACE_NAME)

print '''
// Anything from host that is not an ARP request goes to the input 1 of Odin Agent
fhcl[1]
  -> [1]odinagent
'''

print '''
// Not looking for an STA's ARP? Then let it pass.
fh_arpr[1]
  -> [1]odinagent
'''

print '''
// create a queue and connect it to SetTXRate-RadiotapEncap and send it to the network interface
q :: Queue(%s)
  -> SetTXRate (12)
  -> RadiotapEncap()
  -> to_dev :: ToDevice (%s0);
''' % (QUEUE_SIZE, NETWORK_INTERFACE_NAMES )

print '''
odinagent[2]
  -> q
'''

print '''
// ----------------Packets coming up (from the STA to the AP) go to the input 0 of the Odin Agent
from_dev :: FromDevice(%s0, HEADROOM 50)
  -> RadiotapDecap()
  -> ExtraDecap()
  -> phyerr_filter :: FilterPhyErr()
  -> tx_filter :: FilterTX()
  -> dupe :: WifiDupeFilter()	// Filters out duplicate 802.11 packets based on their sequence number
								// click/elements/wifi/wifidupefilter.hh
  -> [0]odinagent
''' % ( NETWORK_INTERFACE_NAMES )

print '''
odinagent[0]
  -> q
''' 

print '''
// Data frames
// The arp responder configuration here does not matter, odinagent.cc sets it according to clients
odinagent[1]
  -> decap :: WifiDecap()	// Turns 802.11 packets into ethernet packets. click/elements/wifi/wifidecap.hh
  -> RXStats				// Track RSSI for each ethernet source.
							// Accumulate RSSI, noise for each ethernet source you hear a packet from.
							// click/elements/wifi/rxstats.hh
  -> arp_c :: Classifier(12/0806 20/0001, -)
				// 12 means the 12th byte of the eth frame (i.e. ethertype)
				// 0806 is the ARP ethertype, http://en.wikipedia.org/wiki/EtherType
				// 20 means the 20th byte of the eth frame, i.e. the 6th byte of the ARP packet: 
				// "Operation". It specifies the operation the sender is performing: 1 for request
  -> arp_resp::ARPResponder (%s %s) // ARP fast path for STA
									// the STA is asking for the MAC address of the AP
									// add the IP of the AP and the BSSID of the LVAP corresponding to this STA
  -> [1]odinagent
''' % ( AP_UNIQUE_IP, AP_UNIQUE_BSSID )
# it seems that AP_UNIQUE_IP and AP_UNIQUE_BSSID do not matter

print '''
// Non ARP packets. Re-write MAC address to
// reflect datapath or learning switch will drop it
arp_c[1]
  -> ToHost(%s)
''' % ( TAP_INTERFACE_NAME )

print '''
// Click is receiving an ARP request from a STA different from his own STA
// I have to forward the ARP request to the host without modification
// ARP Fast path fail. Re-write MAC address (without modification)
// to reflect datapath or learning switch will drop it
arp_resp[1]
  -> ToHost(%s)
''' % ( TAP_INTERFACE_NAME )
