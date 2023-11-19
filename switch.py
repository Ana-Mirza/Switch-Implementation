#!/usr/bin/python3
import sys
import struct
import wrapper
import threading
import time
from wrapper import recv_from_any_link, send_to_link, get_switch_mac, get_interface_name

mac_table = {}
port_state = {}
own_bridge_ID = 0
root_bridge_ID = 0
root_path_cost = 0
root_port = 0
switch_id = 0
interfaces = []

def parse_ethernet_header(data):
    # Unpack the header fields from the byte array
    dest_mac = data[0:6]
    src_mac = data[6:12]
    
    # Extract ethertype. Under 802.1Q, this may be the bytes from the VLAN TAG
    ether_type = (data[12] << 8) + data[13]

    vlan_id = -1
    # Check for VLAN tag (0x8100 in network byte order is b'\x81\x00')
    if ether_type == 0x8200:
        vlan_tci = int.from_bytes(data[14:16], byteorder='big')
        vlan_id = vlan_tci & 0x0FFF  # extract the 12-bit VLAN ID
        ether_type = (data[16] << 8) + data[17]

    return dest_mac, src_mac, ether_type, vlan_id

def create_vlan_tag(vlan_id):
    # 0x8100 for the Ethertype for 802.1Q
    # vlan_id & 0x0FFF ensures that only the last 12 bits are used
    return struct.pack('!H', 0x8200) + struct.pack('!H', vlan_id & 0x0FFF)

def compute_BPDU_package(port, age):
    # IEEE 802.3 Ethernet
    len = 38
    hello_time = 2
    forward_delay = 15
    age = 1
    mac_address_str = '01:80:c2:00:00:00'
    data = bytes([int(x, 16) for x in mac_address_str.split(':')]) + get_switch_mac() + len.to_bytes(2, 'big')
    # LLC Header
    data += struct.pack('!B', 0x42) + struct.pack('!B', 0x42) + struct.pack('!B', 0x03)
    # STP Payload   
    data += struct.pack('!H', 0x0000) + struct.pack('!B', 0x00) + struct.pack('!B', 0x00) + struct.pack('!B', 0x00)
    data += root_bridge_ID.to_bytes(8, 'big') + root_path_cost.to_bytes(4, 'big') + own_bridge_ID.to_bytes(8, 'big')
    data += struct.pack('!H', 0x8004) + age.to_bytes(2, 'big') + hello_time.to_bytes(2, 'big') + forward_delay.to_bytes(2, 'big')
    return data

def send_bdpu_every_sec():
    while True:
        if root_bridge_ID == own_bridge_ID:
            for port in interfaces:
                if access_port_vlan_id(get_interface_name(port), switch_id) == 'T':
                    data = compute_BPDU_package(port, 0)
                    send_to_link(port, data, 52)
        time.sleep(1)
        
def is_unicast(dest_mac):
    return dest_mac[0] != 'f'

def access_port_vlan_id(port, switch_id):
    vlan_id = ''
    config_file = './configs/switch' + str(switch_id) + '.cfg'
    with open(config_file, 'r') as file:
        switch_priority = int(file.readline().strip())
        
        # find port vlan
        for line in file:
            parts = line.split()
            if len(parts) == 2:
                device_port, vlan = parts
                if device_port == port:
                    vlan_id = vlan
                    break
    return vlan_id

def switch_priority(switch_id):
    config_file = './configs/switch' + str(switch_id) + '.cfg'
    with open(config_file, 'r') as file:
        switch_priority = int(file.readline().strip())
    
    return switch_priority

def bdpu_parse(data):
    bdpu_root_bridge = int.from_bytes(data[22:30], byteorder='big')
    bdpu_path_cost = int.from_bytes(data[30:34], byteorder='big')
    bdpu_sender_bridge = int.from_bytes(data[34:42], byteorder='big')
    return bdpu_root_bridge, bdpu_path_cost, bdpu_sender_bridge

def run_stp(data, interface):
    global root_bridge_ID
    global root_path_cost
    global port_state
    global root_port
    bdpu_root_bridge, bdpu_path_cost, bdpu_sender_bridge = bdpu_parse(data)
    if bdpu_root_bridge < root_bridge_ID:
        initial_root_bridge = root_bridge_ID
        root_bridge_ID = bdpu_root_bridge
        root_path_cost = bdpu_path_cost + 10
        root_port = interface
        
        if initial_root_bridge == switch_priority(switch_id):
            for port in interfaces:
                if access_port_vlan_id(get_interface_name(port), switch_id) == 'T':
                    if port != interface:
                        port_state[port] = 0
        port_state[interface] = 1
        
        for port in interfaces:
            if access_port_vlan_id(get_interface_name(port), switch_id) == 'T':
                if port != interface:
                    data = compute_BPDU_package(port, 0)
                    send_to_link(port, data, 50)
    elif bdpu_root_bridge == root_bridge_ID:
        if interface == root_port and bdpu_path_cost + 10 < root_path_cost:
            root_path_cost = bdpu_path_cost + 10
        elif interface != root_port:
            if bdpu_path_cost > root_path_cost:
                port_state[interface] = 1
    elif bdpu_sender_bridge == own_bridge_ID:
        port_state[interface] = 0
        
    if own_bridge_ID == root_bridge_ID:
        for port in interfaces:
            if access_port_vlan_id(get_interface_name(port), switch_id) == 'T':
                port_state[port] = 1
            

def main():
    # init returns the max interface number. Our interfaces
    # are 0, 1, 2, ..., init_ret value + 1
    global switch_id
    global interfaces
    switch_id = sys.argv[1]

    num_interfaces = wrapper.init(sys.argv[2:])
    interfaces = range(0, num_interfaces)

    print("# Starting switch with id {}".format(switch_id), flush=True)
    print("[INFO] Switch MAC", ':'.join(f'{b:02x}' for b in get_switch_mac()))

    # Printing interface names
    global port_state
    for i in interfaces:
        print(get_interface_name(i))
        # Set trunk ports to blocked
        if access_port_vlan_id(get_interface_name(i), switch_id) == 'T':
            port_state[i] = 0
        else:
            port_state[i] = 1
            
    # Init stp parameters
    global own_bridge_ID
    global root_bridge_ID
    own_bridge_ID = switch_priority(switch_id)
    root_bridge_ID = own_bridge_ID
    if own_bridge_ID == root_bridge_ID:
        for port in interfaces:
            port_state[port] = 1
            
    # Create and start a new thread that deals with sending BDPU
    t = threading.Thread(target=send_bdpu_every_sec)
    t.start()

    while True:
        # Receive packages
        interface, data, length = recv_from_any_link()
        dest_mac, src_mac, ethertype, vlan_id = parse_ethernet_header(data)

        # Print the MAC src and MAC dst in human readable format
        dest_mac = ':'.join(f'{b:02x}' for b in dest_mac)
        src_mac = ':'.join(f'{b:02x}' for b in src_mac)
        
        # delete tag
        if vlan_id != -1:
            data = data[0:12] + data[16:]
            length -= 4

        print(f'Destination MAC: {dest_mac}')
        print(f'Source MAC: {src_mac}')
        print(f'EtherType: {ethertype}')
        print("Received frame of size {} on interface {}".format(length, interface), flush=True)
        
        # Check if BDPU package
        if (dest_mac == '01:80:c2:00:00:00'):
            run_stp(data, interface)
            continue
        
        # Check if port is blocked
        if port_state[interface] == 0:
            continue

        # Forwarding with learning and VLAN's
        mac_table[src_mac] = interface
        if is_unicast(dest_mac):
            if dest_mac in mac_table and port_state[mac_table[dest_mac]] == 1:
                # access port src
                port_vlan_id = access_port_vlan_id(get_interface_name(mac_table[dest_mac]), switch_id)
                if vlan_id == -1:
                    vlan_id = access_port_vlan_id(get_interface_name(interface), switch_id)
                    if str(port_vlan_id) == str(vlan_id):
                        send_to_link(mac_table[dest_mac], data, length)
                    if port_vlan_id == 'T':
                        tagged_frame = data[0:12] + create_vlan_tag(int(vlan_id)) + data[12:]
                        send_to_link(mac_table[dest_mac], tagged_frame, length + 4)
                # trunk port src
                else:
                    # access port route
                    if str(port_vlan_id) == str(vlan_id):
                        send_to_link(mac_table[dest_mac], data, length)
                    # trunk port route
                    if port_vlan_id == 'T':
                        tagged_frame = data[0:12] + create_vlan_tag(int(vlan_id)) + data[12:]
                        send_to_link(mac_table[dest_mac], tagged_frame, length + 4)
            else:
                for port in interfaces:
                    if port != interface and port_state[port] == 1:
                        # access port src
                        port_vlan_id = access_port_vlan_id(get_interface_name(port), switch_id)
                        if vlan_id == -1:
                            vlan_id = access_port_vlan_id(get_interface_name(interface), switch_id)
                            if str(port_vlan_id) == str(vlan_id):
                                send_to_link(port, data, length)
                            if port_vlan_id == 'T':
                                tagged_frame = data[0:12] + create_vlan_tag(int(vlan_id)) + data[12:]
                                send_to_link(port, tagged_frame, length + 4)
                        # trunk port src
                        else:
                            # access port route
                            if str(port_vlan_id) == str(vlan_id):
                                send_to_link(port, data, length)
                            # trunk port route
                            if port_vlan_id == 'T':
                                tagged_frame = data[0:12] + create_vlan_tag(int(vlan_id)) + data[12:]
                                send_to_link(port, tagged_frame, length + 4)
        else:
            # broadcast
            for port in interfaces:
                if port != interface and port_state[port] == 1:
                    # access port src
                    port_vlan_id = access_port_vlan_id(get_interface_name(port), switch_id)
                    if vlan_id == -1:
                        vlan_id = access_port_vlan_id(get_interface_name(interface), switch_id)
                        if str(port_vlan_id) == str(vlan_id):
                            send_to_link(port, data, length)
                        if port_vlan_id == 'T':
                            tagged_frame = data[0:12] + create_vlan_tag(int(vlan_id)) + data[12:]
                            send_to_link(port, tagged_frame, length + 4)
                    # trunk port src
                    else:
                        # access port route
                        if str(port_vlan_id) == str(vlan_id):
                            send_to_link(port, data, length)
                        # trunk port route
                        if port_vlan_id == 'T':
                            tagged_frame = data[0:12] + create_vlan_tag(int(vlan_id)) + data[12:]
                            send_to_link(port, tagged_frame, length + 4)

if __name__ == "__main__":
    main()
