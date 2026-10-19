# Hosting FloodPulse on Azure for Students

One Linux virtual machine runs everything with Docker: the PostGIS database, the FastAPI app (which
also serves the website) and Caddy, which gets a free HTTPS certificate automatically. HTTPS is
required: phones only allow GPS and the camera on secure pages, and admin cookies are Secure.

Time: about 45 minutes the first time. You need: your college email (Azure for Students), a
terminal with `ssh`, and the keys from your laptop's private `.env`.

## 1. Activate Azure for Students

Go to <https://azure.microsoft.com/free/students/>, sign in with your college email and verify
your student status. No credit card is needed. You get US$100 of credit for 12 months plus some
free services. In the portal, open **Cost Management → Budgets** and create a budget alert (for
example US$20) so you are warned before the credit runs low.

## 2. Create the virtual machine

Portal → **Virtual machines → Create → Azure virtual machine**:

| Setting | Value |
|---|---|
| Resource group | New: `floodpulse` |
| Name | `floodpulse-vm` |
| Region | **(Asia Pacific) Central India** (closest to Karnataka) |
| Image | **Ubuntu Server 24.04 LTS** |
| Size | A burstable size included in the student free services if offered (B1s, B2ats v2 or B2pts v2 Arm). These have about 1 GB memory, so step 4 adds swap. **B2s** (4 GB) is faster and uses credit. Check the cost shown on the page. |
| Authentication | **SSH public key**, user name `azureuser`, generate a new key pair and **download the .pem file** |
| Inbound ports | Allow **SSH (22), HTTP (80), HTTPS (443)** |
| Disk | Standard SSD, 30 GB |

Create it, and keep the downloaded key file safe (never commit it).

## 3. Give it a free domain name

Open the VM → **Overview** → click the **Public IP address** → **Configuration**:

- Set **Assignment** to **Static** (the address stays the same after a restart).
- Set **DNS name label** to something unique, e.g. `floodpulse-smvitm`. Save.

Your address is now `floodpulse-smvitm.centralindia.cloudapp.azure.com`. Use this as
`FLOODPULSE_DOMAIN` below.

## 4. Prepare the server

```bash
chmod 600 ~/Downloads/floodpulse-vm_key.pem
ssh -i ~/Downloads/floodpulse-vm_key.pem azureuser@floodpulse-smvitm.centralindia.cloudapp.azure.com
```

On the server:

```bash
# Swap space (needed on 1 GB machines; harmless on larger ones)
sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile && sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# Docker (official convenience script) and permission to use it
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker azureuser
exit
```

Log in again (so the Docker permission applies), then download FloodPulse:

```bash
ssh -i ~/Downloads/floodpulse-vm_key.pem azureuser@floodpulse-smvitm.centralindia.cloudapp.azure.com
git clone --branch floodpulse-v2 https://github.com/Codovia/FloodThings.git floodpulse
cd floodpulse/deploy
```

## 5. Settings

```bash
cp env.example .env
nano .env
```

Set `FLOODPULSE_DOMAIN` to your address from step 3, and paste the optional keys from your laptop's
private `.env` (Google Maps, OpenRouteService, Telegram). Save with Ctrl+O, Enter, Ctrl+X.
`setup.sh` generates the database passwords itself and keeps the file private (permissions 600).
**Never commit or share `deploy/.env`.**

## 6. Install and start

```bash
./setup.sh
```

It builds the app, creates the database, runs the migrations, imports the Karnataka place
directory, grants least-privilege permissions to the two restricted database logins and starts
everything. The first build takes several minutes on a small VM. Open
`https://YOUR-DOMAIN/` in a browser; the certificate is issued on the first visit.

Create your administrator account (you type the password privately, 16–128 characters):

```bash
./create-admin.sh nandan
```

## 7. After the first start

1. **Google Maps key:** Google Cloud → Credentials → your key → Website restrictions → add
   `https://YOUR-DOMAIN/*`. Otherwise the in-app Google route map shows an error.
2. **Telegram:** stop any laptop tunnel (`start-full.sh --telegram`) first, then point the bot at
   the server:
   ```bash
   docker compose run --rm --no-deps app python -B /app/deploy-tools/telegram_webhook.py
   ```
   Subscribers must send `/start floodpulse` again, because the server has a new database.
3. **Shelters:** the server starts with an empty directory. Sign in to `/admin`, add each shelter
   and verify it (verification lasts 24 hours, so re-verify on demo day).

## Everyday commands (run in `~/floodpulse/deploy`)

| Task | Command |
|---|---|
| Update to the latest code | `git pull && ./setup.sh` |
| See status | `docker compose ps` |
| Read the app's log | `docker compose logs --tail 100 app` |
| Restart | `docker compose restart app` |
| Back up the database now | `./backup.sh` (saved privately in `deploy/backups/`, newest 14 kept) |
| Restore a backup (replaces current data) | `./restore.sh backups/floodpulse-YYYYMMDD-HHMMSS.dump` |
| Check the app and database | `curl https://YOUR-DOMAIN/api/health/ready` |
| Reset an admin password | `./create-admin.sh nandan --reset-password` |
| Stop everything | `docker compose down` (data is kept) |

To save credit after the evaluation, stop the VM in the portal (**Stop**, which deallocates it).
The static address and domain stay the same.

## Daily backups and uptime monitoring

1. **Automatic daily backup.** Run `crontab -e`, choose nano, and add this line (02:00 every day):
   ```
   0 2 * * * cd ~/floodpulse/deploy && ./backup.sh >> backups/backup.log 2>&1
   ```
   Copy an occasional backup off the server too (for example with `scp`), since a deleted server
   takes its backups with it.
2. **Uptime alert.** Create a free monitor at <https://uptimerobot.com/>: type HTTP(s), URL
   `https://YOUR-DOMAIN/api/health/ready`, every 5 minutes, alert to your email. It reports when the
   site or its database is down.
3. **Errors.** Unexpected errors are logged with an error ID (the visitor sees only the ID):
   `docker compose logs app | grep "unhandled error"`. Logs are capped at 30 MB per service.

## Limits (optional settings in `deploy/.env`)

| Setting | Default | Meaning |
|---|---|---|
| `FLOODPULSE_RATE_PUBLIC` | `300/60` | Public API requests per visitor address per 60 s |
| `FLOODPULSE_RATE_EXPENSIVE` | `30/60` | Area risk, routing, AI outlook and admin place lookups per address per 60 s |
| `FLOODPULSE_ROUTE_DAILY_LIMIT` | `1500` | In-app routes per day (OpenRouteService free quota is 2,000) |
| `FLOODPULSE_LOGIN_LIMIT_PER_ACCOUNT` / `_PER_ADDRESS` | `5` / `20` | Admin sign-in attempts per 15 minutes |
| `FLOODPULSE_REPORT_LIMIT_PER_ADDRESS` / `_TOTAL` | `5` / `60` | Citizen reports per 15 minutes |

Change a value, then run `docker compose up -d app` to apply it.

## Security notes

- The running app connects with two restricted database logins (read-only place directory, and an
  app login that cannot alter audit history). The database owner password is used only by
  `setup.sh` and `create-admin.sh`.
- The database has no public port; only ports 22, 80 and 443 are open.
- The app trusts the visitor address that Caddy (fixed internal address 172.28.0.10) reports and
  Caddy replaces any address a client sends, so per-address limits apply to each real visitor.
- One app worker is used on purpose: the risk engine and the admin place lookup keep in-memory
  caches and rate limits.
