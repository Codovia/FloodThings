# Hosting FloodPulse on AWS Lightsail

The same Docker setup as the Azure guide, on an Amazon Lightsail server. Lightsail is AWS's simple
virtual-server product with a fixed monthly price. One server runs the PostGIS database, the app
(which also serves the website) and Caddy, which gets a free HTTPS certificate automatically.

Time: about 45 minutes. You need: an AWS account (a card or UPI for the ₹2 sign-up check), a
free DuckDNS name, and the keys from your laptop's private `.env`.

## 1. Create the AWS account

Sign up at <https://aws.amazon.com/>. Indian accounts are run by AWS India (AISPL). Verification
charges ₹2 and refunds it; AWS India accepts Visa, Mastercard, RuPay cards and UPI. Choose the
**Free** plan if offered. Then open **Billing → Budgets** and create a budget alert (for example
US$5) so you are emailed before anything is charged.

## 2. Create the Lightsail server

Open <https://lightsail.aws.amazon.com/> → **Create instance**:

| Setting | Value |
|---|---|
| Region | **Mumbai (ap-south-1)** |
| Platform / blueprint | **Linux/Unix → OS Only → Ubuntu 24.04 LTS** |
| SSH key | Create and **download** a new key pair (keep it safe, never commit it) |
| Plan | **2 GB memory, 2 vCPUs** (dual-stack/IPv4). Lightsail lists three months free on selected plans for new users; check that the plan you pick shows the offer, and check the price after the free period. |
| Name | `floodpulse` |

After it starts:

- **Networking → Create static IP** and attach it to `floodpulse` (free while attached).
- **Networking → IPv4 firewall**: keep SSH (22) and HTTP (80), and **add HTTPS (443)**.

## 3. Free domain name (DuckDNS)

Lightsail gives an IP address, not a name, and HTTPS needs a name.

1. Go to <https://www.duckdns.org/>, sign in (GitHub or Google).
2. Add a subdomain, e.g. `floodpulse-smvitm`, and put your **static IP** in the "current ip" box.
   Click **update ip**.
3. Your address is `floodpulse-smvitm.duckdns.org`. Use it as `FLOODPULSE_DOMAIN`.

## 4. Prepare the server

```bash
chmod 600 ~/Downloads/LightsailDefaultKey-ap-south-1.pem   # your downloaded key file name
ssh -i ~/Downloads/LightsailDefaultKey-ap-south-1.pem ubuntu@YOUR_STATIC_IP
```

On the server:

```bash
# Swap space, so the first build has enough memory
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Docker (official convenience script) and permission to use it
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
exit
```

Log in again, then download FloodPulse:

```bash
ssh -i ~/Downloads/LightsailDefaultKey-ap-south-1.pem ubuntu@YOUR_STATIC_IP
git clone --branch floodpulse-v2 https://github.com/Codovia/FloodThings.git floodpulse
cd floodpulse/deploy
```

## 5. Settings, install and admin

```bash
cp env.example .env
nano .env        # set FLOODPULSE_DOMAIN=floodpulse-smvitm.duckdns.org and paste your keys
./setup.sh       # first build takes several minutes
./create-admin.sh nandan
```

Open `https://floodpulse-smvitm.duckdns.org/`; the certificate is issued on the first visit.
**Never commit or share `deploy/.env`.**

## 6. After the first start

The same as the Azure guide (`docs/AZURE_HOSTING.md`, step 7): add `https://YOUR-DOMAIN/*` to the
Google key's website restrictions, point Telegram at the server with
`docker compose run --rm --no-deps app python -B /app/deploy-tools/telegram_webhook.py`, and add
and verify shelters again in `/admin`. Everyday commands, **daily backups, the uptime monitor,
automatic updates and limit settings** are also in that guide; set up the daily backup and the uptime monitor before the demo.

## Cost notes

- Lightsail charges the plan price whether the server is running or stopped. To stop all charges
  after the evaluation, **delete** the instance and release the static IP (back up first:
  `docker compose exec -T db pg_dump -U floodpulse_admin floodpulse_directory > backup.sql`).
- An unattached static IP is charged; release it when you delete the instance.
