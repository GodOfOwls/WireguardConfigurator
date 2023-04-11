import paramiko
import ipaddress
import os
import tempfile
import random
from wgctrl import WireGuard

# MikroTik router settings
ROUTER_HOST = 'router.godofowls.com'
ROUTER_USERNAME = 'your_username'
ROUTER_PASSWORD = 'your_password'
IP_POOL = ipaddress.ip_network('10.0.0.0/24')

# Helper function to find the next available IP address in the pool
def find_next_available_ip(pool):
    for ip in pool:
        if not ip_assigned(str(ip)):
            return ip
    raise ValueError("No available IP addresses in the pool")

# Helper function to check if an IP address is already assigned
def ip_assigned(ip):
    cmd = f"/ip route print where dst-address~\"^{ip}/\""
    stdin, stdout, stderr = ssh.exec_command(cmd)
    return len(stdout.readlines()) > 0

# Helper function to find an unused port between 9000 and 9500
def find_unused_port():
    for port in range(9000, 9501):
        if not port_in_use(port):
            return port
    raise ValueError("No available ports between 9000 and 9500")

# Helper function to check if a port is already in use by another interface
def port_in_use(port):
    cmd = f"/interface wireguard print where listen-port={port}"
    stdin, stdout, stderr = ssh.exec_command(cmd)
    return len(stdout.readlines()) > 0

# Helper function to generate a random name for the WireGuard interface
def generate_interface_name():
    dictionary = ["elephant", "bee", "tiger", "lion", "giraffe", "whale", "shark", "eagle", "panda", "turtle"]
    return f"wireguard-{random.choice(dictionary)}-{random.choice(dictionary)}"

# Connect to the MikroTik router using SSH
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(ROUTER_HOST, username=ROUTER_USERNAME, password=ROUTER_PASSWORD)

# Find an unused port between 9000 and 9500
unused_port = find_unused_port()

# Generate a unique name for the WireGuard interface
interface_name = generate_interface_name()

# Create a new WireGuard interface and let MikroTik generate its keypair
ssh.exec_command(f"/interface wireguard add listen-port={unused_port} name={interface_name}")

# Assign the WireGuard interface a /30 IP from the IP pool
mikrotik_ip = find_next_available_ip(IP_POOL)
ssh.exec_command(f"/ip address add address={mikrotik_ip}/30 interface={interface_name}")

# Retrieve the WireGuard interface listening port and public key
stdin, stdout, stderr = ssh.exec_command(f"/interface wireguard print where name=\"{interface_name}\"")
line = stdout.readline()
mikrotik_port = line.split()[5]
mikrotik_pubkey = line.split()[6]

# Create a config file for the client
wg = WireGuard()
client_privkey, client_pubkey = wg.gen_key_pair()
client_ip = find_next_available_ip(IP_POOL)

# Add the client public key as a peer for the WireGuard interface on the MikroTik router
ssh.exec_command(f"/interface wireguard peers add allowed-address={client_ip}/32 public-key={client_pubkey} interface={interface_name}")

config_template = f"""
[Interface]
PrivateKey = {client_privkey}
Address = {client_ip}/32

[Peer]
PublicKey = {mikrotik_pubkey}
AllowedIPs = 0.0.0.0/0
Endpoint = {ROUTER_HOST}:{mikrotik_port}
"""

# Save the config to a temporary file
with tempfile.NamedTemporaryFile(delete=False) as temp_config:
    temp_config.write(config_template.encode())
    temp_config.close()
    print(f"Client config saved to: {temp_config.name}")

# Close the SSH connection
ssh.close()
