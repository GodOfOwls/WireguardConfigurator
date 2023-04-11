import base64
import uuid

import paramiko
import ipaddress
import os
import tempfile
import random
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, PublicFormat, NoEncryption

# MikroTik router settings
ROUTER_HOST = 'router.godofowls.eu'
ROUTER_USERNAME = 'admin'
ROUTER_PASSWORD = 'admin'
IP_POOL = ipaddress.ip_network('10.156.69.0/24')
try:
    from secret import ROUTER_USERNAME, ROUTER_PASSWORD
except ImportError:
    print('Its advised to put ROUTER_USERNAME and ROUTER_PASSWORD into a seperate file called secret.py')


# Helper function to generate a WireGuard public/private key pair
def gen_key_pair():
    private_key = x25519.X25519PrivateKey.generate()
    private_raw = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())
    private_b64 = base64.b64encode(private_raw).decode('utf-8')
    public_key = private_key.public_key()
    public_raw = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    public_b64 = base64.b64encode(public_raw).decode('utf-8')
    return private_b64, public_b64


# Helper function to find the next available IP address in the pool

def find_next_available_ip(pool):
    pool_hosts = list(pool.hosts())
    idx = 0

    while idx < len(pool_hosts):
        ip = pool_hosts[idx]
        if not ip_assigned(str(ip)):
            subnet = ipaddress.ip_network(f"{ip}/30", strict=False)
            if all(not ip_assigned(str(host)) for host in subnet.hosts()):
                return subnet
        idx += 4

    raise ValueError("No available /30 subnets in the pool")


# Helper function to check if an IP address is already assigned
def ip_assigned(ip):
    cmd = f"/ip route print where dst-address in {ip}/30"
    stdin, stdout, stderr = ssh.exec_command(cmd)
    tt = stdout.readlines()
    return len(tt) > 1


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
    t = stdout.readlines()
    return len(t) > 2


# Helper function to generate a random name for the WireGuard interface
def generate_interface_name():
    dictionary = ["elephant", "bee", "tiger", "lion", "giraffe", "whale", "shark", "eagle", "panda", "turtle"]
    return f"wg-{str(uuid.uuid4())[:7]}"


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
mikrotik_subnet = find_next_available_ip(IP_POOL)
hosts = mikrotik_subnet.hosts()
mikrotik_ip, client_ip = list(mikrotik_subnet.hosts())[:2]
ssh.exec_command(f"/ip address add address={mikrotik_ip}/30 interface={interface_name}")

# Retrieve the WireGuard interface listening port and public key
stdin, stdout, stderr = ssh.exec_command(f"/interface wireguard print where name=\"{interface_name}\"")
line = stdout.readlines()
mikrotik_port = unused_port
mikrotik_pubkey = line[3].split('=', 1)[1].split("\r")[0]

# Create a config file for the client
client_privkey, client_pubkey = gen_key_pair()


# Add the client public key as a peer for the WireGuard interface on the MikroTik router
stdin, stdout, stderr = ssh.exec_command(
    f'/interface wireguard peers add allowed-address={client_ip}/32,0.0.0.0/0 public-key="{client_pubkey}" interface={interface_name}')
line = stdout.readlines()
line2 = stderr.readlines()
config_template = f"""
[Interface]
PrivateKey = {client_privkey}
Address = {client_ip}/30

[Peer]
PublicKey = {mikrotik_pubkey[1:-2]}
AllowedIPs = 0.0.0.0/0
Endpoint = {ROUTER_HOST}:{mikrotik_port}
"""

# Save the config to a temporary file
with tempfile.NamedTemporaryFile(delete=False) as temp_config:
    temp_config.write(config_template.encode())
    temp_config.close()
    print(f"Client config saved to: {temp_config.name}")

os.makedirs('configs', exist_ok=True)
config_filename = f"configs/c-{interface_name}.conf"
with open(config_filename, 'w') as config_file:
    config_file.write(config_template.strip())

print(interface_name)
# Close the SSH connection
ssh.close()
