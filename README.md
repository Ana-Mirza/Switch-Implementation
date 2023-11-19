Name: Ana-Maria Mirza

Group: 331CA

Tasks completed: 1 2 3


## Homework 1 -- Switch Implementation --
This is the implementation of a switch with a CAM Table, VLAN 
support and the STP algorithm, in order to avoid loops in the 
local network.

### Switch Implementation
The implementation of the switch CAM table was realized with 
the help of a dictionary keeping record of each mac address 
and the port it came on.

For the VLAN support, I added a verification so that the a
packet received is only sent further on ports in the same 
VLAN and made sure to add or remove the 802.1q tag when going
from an access port to a trunk or from trunk to access.

Adding the STP algorithm implied building BPDU packets and
sending them to all ports if the switch is root bridge and
updating the root bridge and cost each time a BPDU packet
was received.

### How to Run:

```bash
sudo python3 checker/topo.py
```

This will open 9 terminals, 6 hosts and 3 for the switches.
On the switch terminal you will run 

```bash
make run_switch SWITCH_ID=X # X is 0,1 or 2
```

The hosts have the following IP addresses.
```
host0 192.168.1.1
host1 192.168.1.2
host2 192.168.1.3
host3 192.168.1.4
host4 192.168.1.5
host5 192.168.1.6
```

You can test the switch implementation using ICMP packets. For example, from host0 you can run:

```
ping 192.168.1.2
```

or even simpler
```
ping host1
```


Note: You can also use wireshark for debugging and more insight. From any terminal you can run `wireshark&`.
