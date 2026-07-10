# TravelMemory — EC2 Deployment Documentation

End-to-end guide for deploying the [TravelMemory](https://github.com/OmkarBodhale/TravelMemory.git) MERN-stack app (Node/Express backend + React frontend + MongoDB) on AWS EC2, with Nginx reverse proxy, a load balancer across multiple instances, and a custom domain via Cloudflare.

> **Scope note:** This document covers infrastructure, configuration, and deployment steps. 

---

## Architecture Overview

```
                                   ┌─────────────────────┐
                                   │      Cloudflare      │
                                   │  DNS + Proxy (CDN)   │
                                   └──────────┬───────────┘
                     CNAME (app.yourdomain.com)   A record (www/root -> frontend EC2 IP)
                                   │
                       ┌───────────┴────────────┐
                       │   AWS Load Balancer     │
                       │   (ALB / ELB)           │
                       └───┬─────────────────┬───┘
                           │                 │
                 ┌─────────▼──────┐ ┌────────▼─────────┐
                 │  EC2 Instance 1 │ │  EC2 Instance 2   │
                 │  Nginx (proxy)  │ │  Nginx (proxy)    │
                 │  ├─ Frontend    │ │  ├─ Frontend      │
                 │  │  (React,     │ │  │  (React,       │
                 │  │  served on   │ │  │  served on     │
                 │  │  port 3000)  │ │  │  port 3000)    │
                 │  └─ Backend     │ │  └─ Backend       │
                 │     (Node.js,   │ │     (Node.js,     │
                 │     PM2, :3001) │ │     PM2, :3001)   │
                 └────────┬────────┘ └────────┬──────────┘
                          │                    │
                          └─────────┬──────────┘
                                    │
                          ┌─────────▼─────────┐
                          │   MongoDB Atlas    │
                          │  (managed cluster) │
                          └────────────────────┘

## Prerequisites

- AWS account with permission to create EC2 instances, Security Groups, and a Load Balancer (ALB)
- A MongoDB database — either MongoDB Atlas (recommended, managed) or self-hosted MongoDB
- A domain registered and added to Cloudflare (nameservers pointed to Cloudflare)
- SSH key pair for EC2 access
- Basic familiarity with Linux CLI, Git, npm

---
## Execuete SysArchitecrure-Boto3.py to create the env setup

Aim here is to create VPC network with Public EC2 Instance Creation along with a new .pem screte key
## Infrastructure creation using Boto3
<img width="1477" height="862" alt="image" src="https://github.com/user-attachments/assets/2767b5bf-0b31-483b-87c7-3657b69cf54e" />

## VPC network created 

<img width="1601" height="737" alt="image" src="https://github.com/user-attachments/assets/6b59152e-1692-41a8-9b95-b9eb587737a9" />

## Public EC2 Instance Created
<img width="1577" height="707" alt="image" src="https://github.com/user-attachments/assets/9f391165-4cfd-4248-90bb-e8c0337c24b5" />

## 1. Launch and Prepare the EC2 Instance(s)

1. In the AWS Console, launch an **EC2 instance** (Ubuntu 22.04 LTS recommended, t2.micro/t3.micro is enough for testing).
2. Configure the **Security Group** to allow inbound traffic on:
   - `22` (SSH) — restricted to your IP
   - `80` (HTTP)
   - `443` (HTTPS, once you add SSL)
   - `3000` (optional — only if you want to hit the backend directly for debugging; not required once Nginx proxy is set up)
     
  <img width="1586" height="687" alt="image" src="https://github.com/user-attachments/assets/7e7dc583-09f7-4eb9-b93b-a03d175aac7e" />

3. Repeat this step to create a **second instance** later for load balancing (Task 3), or launch both now with identical configuration.

`[ADD SCREENSHOT: EC2 instance summary page showing public IP and security group]`

4. Connect into the public instance using MobaXtrem:

  <img width="1917" height="960" alt="image" src="https://github.com/user-attachments/assets/cbd91c37-e00c-4a96-8182-5f8f452d7b72" />
  
5. Go to the root directory and create folder and clone TravelMemory Source Code:
   ```bash
   pwd
   mkdir Deployment
   cd Deployment/
   git clone https://github.com/OmkarBodhale/TravelMemory.git
   ```
   <img width="1612" height="296" alt="image" src="https://github.com/user-attachments/assets/0752498a-30a7-41da-91aa-5af97ea3fd21" />

6. Install Docker follow deployment steps from Offical website (https://docs.docker.com/engine/install/ubuntu/).
   
---

## 2. Backend Configuration

1. Create the `.env` file in `backend/`:
   ```
   cd backend/
   touch .env
   sudo nano .env
   ```
   ## .env file
   ```
   MONGO_URI='your-mongodb-connection-string'
   PORT=3000
   ```
   <img width="1617" height="270" alt="Screenshot 2026-07-10 005953" src="https://github.com/user-attachments/assets/a646081d-1649-4a7c-9fa6-e9aa2accc356" />
   > Currently backend implementation consumes 3001 port, Just make sure the `PORT` value here matches the `proxy_pass` port in the Nginx config below.

3. Execute Docker file to create backend app Docker Image:
   ```bash
   sudo docker build -t tmbe .  #Creates docker image
   sudo docker images   #Shows all the images present
   sudo docker run -d -p 3001:3001 --name tmbec tmbe:latest    #Creates Docker container using tmbe
   ```
   <img width="1911" height="336" alt="image" src="https://github.com/user-attachments/assets/e60644b5-e047-4490-af88-90edcc947ff6" />

   <img width="1615" height="297" alt="image" src="https://github.com/user-attachments/assets/1857d202-8197-49f0-89c7-37fb6f7917d2" />

   ## **Verify the backend application running or not by enabling 3001 port under inbound rules:
   <img width="1911" height="942" alt="image" src="https://github.com/user-attachments/assets/66ba7edf-15e3-4a54-9725-4c96c5b746ac" />

### Nginx Installation

```bash
sudo apt install nginx
```
<img width="1617" height="397" alt="image" src="https://github.com/user-attachments/assets/306e4193-52d6-49f6-bfb3-ce80310ac41b" />

### Nginx Reverse Proxy (Backend)
Create an Nginx site config, e.g. `/etc/nginx/sites-available/travelmemory`:

```nginx
server {
    listen 80;
    server_name 3.110.212.211;

    # Frontend (static React build)
    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # Backend API reverse proxy
    location /trip/ {
        proxy_pass http://localhost:3001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```
<img width="1612" height="752" alt="image" src="https://github.com/user-attachments/assets/1b657ccd-068d-47f4-bd5a-af22d18a15fd" />

Enable the site and restart Nginx:
```bash
sudo ln -s /etc/nginx/sites-available/travelmemory /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
```

<img width="1607" height="197" alt="image" src="https://github.com/user-attachments/assets/e9bd8165-3272-495f-bc04-68e3ff38fa01" />
<img width="1615" height="517" alt="image" src="https://github.com/user-attachments/assets/1198a65c-7f18-4589-94c0-eae2763ee063" />

---

## 3. Frontend Configuration and Backend Connection

1. Change directory to frontend and create .env file
   ```
   REACT_APP_BACKEND_URL=http://<EC2_PUBLIC_IP_OR_DOMAIN>
   ```
   ```bash
   cd ~/TravelMemory/frontend
   sudo nano .env
   ```
   <img width="1617" height="215" alt="image" src="https://github.com/user-attachments/assets/a561a186-2722-4298-890d-e4daf2dde75c" />

2. Execute Docker file to create frontend app Docker Image:
   ```bash
   sudo docker build -t tmfe .  #Creates docker image
   sudo docker images   #Shows all the images present
   sudo docker run -d -p 3000:3000 --name tmfec tmfe:latest    #Creates Docker container using tmfe
   ```
<img width="1617" height="657" alt="image" src="https://github.com/user-attachments/assets/a94899b4-f3b0-4a67-b1c7-f23be057283b" />

## Application setup working from nginx reverse proxy
<img width="1917" height="962" alt="image" src="https://github.com/user-attachments/assets/608ee397-d88f-4f56-8237-472a5c012b37" />

## 4. Scaling: Multiple Instances + Load Balancer

1. **Repeat Steps 1–3** on a second EC2 instance (or use an AMI/snapshot of the first instance to speed this up: *Actions → Image and templates → Create image*, then launch a new instance from that AMI).
   ## AMI image created using above implemented setup 
<img width="1596" height="715" alt="image" src="https://github.com/user-attachments/assets/26e7e3ff-b91a-4318-af76-10f0262cdae1" />

2. Create Second EC2 instance using the above AMI image.
   <img width="1895" height="820" alt="image" src="https://github.com/user-attachments/assets/3a9e8c42-252e-47ba-854b-75e9c8334c1a" />
   
3. Setup the second EC2 Instance
   ```bash
   sudo docker images
   sudo docker ps -a              #Shows all the avaliable Containers and its current status
   sudo docker start tmbec
   sudo docker start tmfec
   sudo docker ps -a              #Reconfirm Containers running status
   ```
   <img width="1907" height="392" alt="image" src="https://github.com/user-attachments/assets/903fe013-97dc-4f25-b8a3-3a3bb5d90b90" />
   
4. Now lets setup the travel memory frontend .env file
   ```bash
    sudo docker exec -it tmfec bash         #this will allow us to open the frontend application docker to ipen in interactive mode
   ls
   apt-get update
   apt-get upgrade
   apt install nano                         #open the .env to update backend url
   nano .env
   ```
   <img width="1902" height="565" alt="image" src="https://github.com/user-attachments/assets/78f18932-6917-4d71-9961-f465542a169a" />
   <img width="1917" height="87" alt="image" src="https://github.com/user-attachments/assets/2e310037-0bb5-4276-9a51-b9badde8a621" />

6. **Create a Target Group** (AWS Console → EC2 → Target Groups):
   - Target type: Instances
   - Protocol/Port: HTTP / 80
   - Register both EC2 instances as targets
   - Health check path: `/` (or a lightweight health endpoint if you add one)
 <img width="1901" height="822" alt="image" src="https://github.com/user-attachments/assets/687d396e-d40f-44ed-8557-453882014063" />
 <img width="1905" height="537" alt="image" src="https://github.com/user-attachments/assets/9bb7a91f-0917-449f-9f68-af3f7ac390e5" />
 <img width="1892" height="820" alt="image" src="https://github.com/user-attachments/assets/4e31677e-31b1-4c47-9416-e29fa9f5223e" />

3. **Create an Application Load Balancer (ALB)**:
   - Scheme: internet-facing
   - Listeners: HTTP:80 (add HTTPS:443 later with an ACM certificate)
   - Availability Zones: select subnets covering both instances
   - Attach the Target Group created above

<img width="1896" height="822" alt="image" src="https://github.com/user-attachments/assets/3a19dea5-752c-4f32-9d6d-2d1c7a676ceb" />
<img width="1592" height="305" alt="image" src="https://github.com/user-attachments/assets/36b31464-bb1b-4c77-b5ef-6412861ab38a" />

4. Update the **Security Groups**:
   - ALB's security group: allow inbound 80/443 from `0.0.0.0/0`
   - EC2 instances' security group: allow inbound 80 **only from the ALB's security group** (tighter than opening to the world)
<img width="1592" height="710" alt="image" src="https://github.com/user-attachments/assets/ed67b94b-1930-4408-b0e4-bc9a56a86fdb" />

5. Test the load balancer directly using its DNS name before wiring up Cloudflare:
   ```bash
   curl http://<alb-dns-name>
   ```
<img width="1907" height="1015" alt="image" src="https://github.com/user-attachments/assets/20c1a7ae-9622-4cfe-8825-29a335e0043a" />

## 6. Verification Checklist

- [ ] Backend responds on `http://localhost:3000` on each instance
- [ ] Nginx reverse proxy serves frontend + proxies `/trip/` to backend
- [ ] Frontend `url.js` / `.env` points to the correct backend URL
- [ ] Both EC2 instances registered and **healthy** in the Target Group
- [ ] Load Balancer DNS name serves the app and round-robins between instances
- [ ] Cloudflare CNAME resolves to the Load Balancer
- [ ] Cloudflare A record resolves to the frontend EC2 IP
- [ ] Custom domain loads the app over HTTPS
