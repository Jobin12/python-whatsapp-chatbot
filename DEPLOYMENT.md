# WhatsApp Chatbot Deployment Guide

This guide describes how to deploy your WhatsApp Chatbot to your production server using Docker.

## 0. Prerequisites
- A server (VPS, EC2, Droplet, etc.) running Linux.
- **Docker** and **Docker Compose** installed on the server.
- **Git** installed on the server.

## 1. Push Code to Git
From your local machine, commit and push your code to your repository (GitHub, GitLab, etc.).
*Note: Your `.env` file is ignored and will NOT be pushed. This is correct.*

```bash
git add .
git commit -m "Ready for deployment"
git push origin main
```

## 2. Pull Code on Server
SSH into your server and clone your repository (or pull if it already exists).

```bash
git clone https://github.com/your-username/your-repo.git
cd your-repo
```

## 3. Configure Environment Variables
Since `.env` is not in Git, you must create it manually on the server.

```bash
nano .env
```

Paste your production secrets into this file. It should look like this:

```ini
ACCESS_TOKEN="your_prod_access_token"
APP_ID="your_app_id"
APP_SECRET="your_app_secret"
RECIPIENT_WAID="your_number"
VERSION="v24.0"
PHONE_NUMBER_ID="your_prod_phone_number_id"
VERIFY_TOKEN="your_verify_token"
GEMINI_API_KEY="your_gemini_api_key"
```

*Press `Ctrl+X`, then `Y`, then `Enter` to save and exit.*

## 4. Build and Run
Run the application using Docker Compose. This will build the container and start it in the background.

```bash
docker compose up --build -d
```

## 5. Deployment Checklist
- [ ] **Firewall**: Ensure port `8000` is open (or use a reverse proxy like Nginx/Caddy to map port 80 to 8000).
- [ ] **Webhook Update**: Go to the [Meta App Dashboard](https://developers.facebook.com/).
    - Update the **Webhook URL** to your server's public IP or domain:
      `http://YOUR_SERVER_IP:8000/webhook` (or `https` if using SSL/Nginx).
    - Verify against your `VERIFY_TOKEN`.
- [ ] **System User**: Ensure your `ACCESS_TOKEN` is a permanent System User token, not a temporary developer token.
