import boto3
import os
import time

# Initialize Boto3 clients
region = 'ap-south-1'
ec2 = boto3.resource('ec2', region_name=region)
ec2_client = boto3.client('ec2', region_name=region)
ssm_client = boto3.client('ssm', region_name=region)

print("1. Creating VPC and Subnets (256 Total IPs)...")
# A /24 CIDR provides exactly 256 IPs.
vpc = ec2.create_vpc(CidrBlock='10.0.0.0/24')
vpc.create_tags(Tags=[{"Key": "Name", "Value": "TM-VPC"}])
vpc.wait_until_available()

# Enable DNS Hostnames
ec2_client.modify_vpc_attribute(VpcId=vpc.id, EnableDnsSupport={'Value': True})
ec2_client.modify_vpc_attribute(VpcId=vpc.id, EnableDnsHostnames={'Value': True})

# Splitting the /24 into two /25 subnets (128 IPs each)
public_subnet = ec2.create_subnet(CidrBlock='10.0.0.0/25', VpcId=vpc.id, AvailabilityZone=f'{region}a')
public_subnet.create_tags(Tags=[{"Key": "Name", "Value": "TM-Public-Subnet"}])

private_subnet = ec2.create_subnet(CidrBlock='10.0.0.128/25', VpcId=vpc.id, AvailabilityZone=f'{region}b')
private_subnet.create_tags(Tags=[{"Key": "Name", "Value": "TM-Private-Subnet"}])

print("2. Configuring Internet Gateway & Public Routing...")
igw = ec2.create_internet_gateway()
vpc.attach_internet_gateway(InternetGatewayId=igw.id)

public_route_table = vpc.create_route_table()
public_route_table.create_route(DestinationCidrBlock='0.0.0.0/0', GatewayId=igw.id)
public_route_table.associate_with_subnet(SubnetId=public_subnet.id)

print("3. Configuring NAT Gateway & Private Routing (This may take a minute)...")
# Allocate Elastic IP for NAT Gateway
eip = ec2_client.allocate_address(Domain='vpc')

# Create NAT Gateway in the Public Subnet
nat_gw = ec2_client.create_nat_gateway(SubnetId=public_subnet.id, AllocationId=eip['AllocationId'])

# Wait for NAT Gateway to become available before routing traffic to it
waiter = ec2_client.get_waiter('nat_gateway_available')

# FIX: Access the ID inside the nested 'NatGateway' dictionary
waiter.wait(NatGatewayIds=[nat_gw['NatGateway']['NatGatewayId']])

# Create Private Route Table and route internet-bound traffic to the NAT Gateway
private_route_table = vpc.create_route_table()
private_route_table.create_route(DestinationCidrBlock='0.0.0.0/0', NatGatewayId=nat_gw['NatGateway']['NatGatewayId'])
private_route_table.associate_with_subnet(SubnetId=private_subnet.id)

print("4. Setting up Security Groups...")
public_sg = ec2.create_security_group(GroupName='TM-public-sg', Description='Allow SSH', VpcId=vpc.id)
public_sg.authorize_ingress(IpPermissions=[{'IpProtocol': 'tcp', 'FromPort': 22, 'ToPort': 22, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}])

# Securely chain the private SG to only accept traffic from the public SG
private_sg = ec2.create_security_group(GroupName='TM-private-sg', Description='Allow SSH from Public', VpcId=vpc.id)
private_sg.authorize_ingress(IpPermissions=[{'IpProtocol': 'tcp', 'FromPort': 22, 'ToPort': 22, 'UserIdGroupPairs': [{'GroupId': public_sg.group_id}]}])

print("5. Creating a New SSH Key Pair...")
key_name = 'TM-ubuntu-2604-keypair'

# Clean up local file if re-running the script
try:
    ec2_client.delete_key_pair(KeyName=key_name)
    if os.path.exists(f'{key_name}.pem'):
        os.remove(f'{key_name}.pem')
except Exception:
    pass

key_pair = ec2.create_key_pair(KeyName=key_name)
with open(f'{key_name}.pem', 'w') as key_file:
    key_file.write(key_pair.key_material)
# Secure the file so SSH doesn't reject it for being too open
os.chmod(f'{key_name}.pem', 0o400) 

print("6. Fetching Latest Ubuntu 26.04 LTS AMI...")
ami_parameter = ssm_client.get_parameter(
    Name='/aws/service/canonical/ubuntu/server/resolute/stable/current/amd64/hvm/ebs-gp3/ami-id'
)
ubuntu_2604_ami = ami_parameter['Parameter']['Value']
print(f"   Found AMI ID: {ubuntu_2604_ami}")

print("7. Launching Instances (8GB gp3 storage)...")
# Storage Configuration
block_device_mappings = [{
    'DeviceName': '/dev/sda1',
    'Ebs': {
        'VolumeSize': 8,
        'VolumeType': 'gp3'
    }
}]

# Provision 1 Public EC2
public_ec2 = ec2.create_instances(
    ImageId=ubuntu_2604_ami,
    InstanceType='t2.micro',
    MinCount=1, MaxCount=1,
    KeyName=key_name,
    NetworkInterfaces=[{
        'SubnetId': public_subnet.id,
        'DeviceIndex': 0,
        'AssociatePublicIpAddress': True,
        'Groups': [public_sg.group_id]
    }],
    BlockDeviceMappings=block_device_mappings,
    TagSpecifications=[{'ResourceType': 'instance', 'Tags': [{'Key': 'Name', 'Value': 'TM-Frontend-01'}]}]
)

# Provision Private EC2 - Backend
private_ec2_backend = ec2.create_instances(
    ImageId=ubuntu_2604_ami,
    InstanceType='t2.micro',
    MinCount=1, MaxCount=1,
    KeyName=key_name,
    NetworkInterfaces=[{
        'SubnetId': private_subnet.id,
        'DeviceIndex': 0,
        'Groups': [private_sg.group_id]
    }],
    BlockDeviceMappings=block_device_mappings,
    TagSpecifications=[{'ResourceType': 'instance', 'Tags': [{'Key': 'Name', 'Value': 'TM-Backend-01'}]}]
)

# Provision Private EC2 - Database
private_ec2_db = ec2.create_instances(
    ImageId=ubuntu_2604_ami,
    InstanceType='t2.micro',
    MinCount=1, MaxCount=1,
    KeyName=key_name,
    NetworkInterfaces=[{
        'SubnetId': private_subnet.id,
        'DeviceIndex': 0,
        'Groups': [private_sg.group_id]
    }],
    BlockDeviceMappings=block_device_mappings,
    TagSpecifications=[{'ResourceType': 'instance', 'Tags': [{'Key': 'Name', 'Value': 'TM-Database'}]}]
)

print("\n--- Infrastructure Provisioned ---")
print(f"VPC ID: {vpc.id}")
print(f"NAT Gateway ID: {nat_gw['NatGateway']['NatGatewayId']}")
print(f"Public Instance ID (TM-Frontend-01): {public_ec2[0].id}")
print(f"Private Instance ID (TM-Backend-01): {private_ec2_backend[0].id}")
print(f"Private Instance ID (TM-Database): {private_ec2_db[0].id}")
print(f"Use '{key_name}.pem' to SSH into the Public Instance.")