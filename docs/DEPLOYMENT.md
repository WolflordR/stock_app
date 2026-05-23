# Trade Lab Deployment Guide

This app is best deployed as an internal service on a workstation or Linux server.

## Recommended architecture

1. Keep the code in a fixed directory such as `/opt/trade-app`
2. Run Streamlit as a `systemd` service
3. Put `nginx` in front of Streamlit
4. Restrict access to your LAN, VPN, or reverse proxy authentication
5. Update with `git pull` and restart the service

## 1. Prepare the workstation

Create a service user:

```bash
sudo useradd --system --create-home --shell /bin/bash tradeapp
```

Clone the project:

```bash
sudo mkdir -p /opt/trade-app
sudo chown -R $USER:$USER /opt/trade-app
git clone <YOUR_GIT_REPO_URL> /opt/trade-app
cd /opt/trade-app
```

Create the virtual environment and install dependencies:

```bash
python3 -m venv stock_env
stock_env/bin/pip install --upgrade pip
stock_env/bin/pip install -r requirements.txt
```

If you use local Ollama on the workstation, install and start it separately.

## 2. Streamlit configuration

Copy the example config:

```bash
mkdir -p .streamlit
cp deploy/.streamlit/config.toml.example .streamlit/config.toml
```

## 3. Create the systemd service

Copy the example service:

```bash
sudo cp deploy/systemd/trade-app.service.example /etc/systemd/system/trade-app.service
```

Edit the following if needed:

- `User`
- `Group`
- `WorkingDirectory`
- `ExecStart`
- `OPENAI_API_KEY`
- `OPENAI_NEWS_MODEL`

Reload and start:

```bash
sudo systemctl daemon-reload
sudo systemctl enable trade-app
sudo systemctl start trade-app
sudo systemctl status trade-app --no-pager
```

## 4. Put nginx in front

Copy the example nginx config:

```bash
sudo cp deploy/nginx/trade-app.conf.example /etc/nginx/sites-available/trade-app.conf
sudo ln -s /etc/nginx/sites-available/trade-app.conf /etc/nginx/sites-enabled/trade-app.conf
sudo nginx -t
sudo systemctl reload nginx
```

Then point your internal DNS or hosts entry to:

- `trade-app.internal`

You can also change `server_name` to a workstation IP or internal hostname.

## 5. Update the app frequently

Use the included deploy script:

```bash
APP_DIR=/opt/trade-app \
APP_USER=tradeapp \
APP_GROUP=tradeapp \
BRANCH=main \
SERVICE_NAME=trade-app \
bash deploy/deploy.sh
```

What this does:

1. Pulls the latest code
2. Installs dependencies
3. Fixes file ownership
4. Restarts the systemd service

## 6. Useful commands

Start or stop the app:

```bash
sudo systemctl start trade-app
sudo systemctl stop trade-app
sudo systemctl restart trade-app
```

Check logs:

```bash
sudo journalctl -u trade-app -f
```

Check nginx logs:

```bash
sudo tail -f /var/log/nginx/access.log /var/log/nginx/error.log
```

## 7. Security notes

Do not expose raw Streamlit directly to the internet.

At minimum, use one of these:

- Internal LAN only
- VPN only
- Reverse proxy basic auth
- Company SSO or access gateway

If you later want HTTPS:

- add an internal certificate
- or use a reverse proxy such as Caddy or nginx with TLS
