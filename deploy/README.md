# Hosting FindMyVibe on AWS EC2

One Ubuntu server runs everything:

```
browser ──https──> Caddy (ports 80/443, automatic HTTPS)
                     ├─ /api/*  → FastAPI  (127.0.0.1:8000)
                     └─ else    → Next.js  (127.0.0.1:3000)
```

## 1. Launch the server (AWS console → EC2 → Launch instance)

- **Name:** `findmyvibe`
- **Image:** Ubuntu Server 24.04 LTS
- **Instance type:** `t3.small` (2 GB RAM)
- **Key pair:** create one (you can also connect from the browser instead)
- **Network settings → Edit:** allow **SSH**, **HTTP** and **HTTPS** from anywhere
- **Storage:** 20 GB
- Launch.

Then **EC2 → Elastic IPs → Allocate**, and **Associate** it with the instance.
That address never changes; your domain will point at it.

## 2. Point your domain at the server

Wherever the domain is registered, open its DNS settings and add:

| Type | Host | Value |
|------|------|-------|
| A | `@` | your Elastic IP |
| A | `www` | your Elastic IP |

Remove any default "parking" records. Wait until https://dnschecker.org shows
your IP for the domain (usually minutes).

## 3. Run the setup script on the server

EC2 → select the instance → **Connect** → **EC2 Instance Connect** → Connect.
In that terminal:

```bash
git clone https://github.com/JoseGurrola1/FindMyVibe.git
cd FindMyVibe
bash deploy/setup.sh yourdomain.tech
```

It asks for `SERPAPI_KEY` and `GEMINI_API_KEY` (typing is hidden), then takes
about 5 minutes. When it finishes, open `https://yourdomain.tech`.

## Updating after new commits

```bash
cd ~/FindMyVibe && bash deploy/update.sh
```

## When something's wrong

| Symptom | Check |
|---|---|
| Site doesn't load | DNS points at the Elastic IP; ports 80/443 open in the security group |
| Certificate / HTTPS error | `sudo journalctl -u caddy -n 50` (usually DNS not updated yet) |
| "502 Bad Gateway" | `systemctl status findmyvibe-api findmyvibe-web` |
| Game errors | `journalctl -u findmyvibe-api -f` |
| Changed a key in `.env` | `sudo systemctl restart findmyvibe-api` |
| Players see "Puss needs a catnap!" | They hit the rate limit (default 20 turns/minute and 150/hour per visitor, 1000/hour total). Change `RATE_LIMIT_PER_MINUTE`, `RATE_LIMIT_PER_HOUR` or `RATE_LIMIT_GLOBAL_PER_HOUR` in `.env`, then `sudo systemctl restart findmyvibe-api` |

## Cost

On an AWS Free plan account this runs on your credits; you are not billed.
The account is suspended when the credits or 6 months run out. Each game turn
still uses your SerpApi and Gemini quotas, so don't post the link publicly.
When you're done, terminate the instance and **release the Elastic IP**.
