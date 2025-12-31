# Stream Buddy - Deployment Guide

## Target Environment
- **Server**: AWS Lightsail (13.43.37.64)
- **URL Path**: `/stream-buddy/`
- **Port**: 8088

## Prerequisites
- SSH access to resume-buddy server
- API keys: OpenAI, Google Gemini, ElevenLabs
- Redis running on server

---

## Quick Deploy (Automated)

```bash
# From local project directory
chmod +x deploy.sh
./deploy.sh
```

---

## Manual Deployment Steps

### 1. SSH to Server
```bash
ssh -i /home/katnyeung/resume-buddy.pem ubuntu@13.43.37.64
```

### 2. Create Directory Structure
```bash
mkdir -p /home/ubuntu/resume-buddy/deploy/stream-buddy
cd /home/ubuntu/resume-buddy/deploy/stream-buddy
```

### 3. Upload Files (from local)
```bash
# Run from local project directory
rsync -avz -e "ssh -i /home/katnyeung/resume-buddy.pem" \
  --exclude '.git' --exclude '__pycache__' --exclude '.venv' --exclude 'venv' \
  ./ ubuntu@13.43.37.64:/home/ubuntu/resume-buddy/deploy/stream-buddy/
```

### 4. Setup Python Environment (on server)
```bash
cd /home/ubuntu/resume-buddy/deploy/stream-buddy
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 5. Configure Environment Variables
```bash
cp .env.example .env
nano .env  # Add production API keys
```

Required keys:
- `OPENAI_API_KEY`
- `GOOGLE_API_KEY`
- `ELEVENLABS_API_KEY`
- `ELEVENLABS_VOICE_CIPHER` (optional custom voice)
- `ELEVENLABS_VOICE_NARRATOR` (optional custom voice)

### 6. Install Systemd Service
```bash
sudo cp stream-buddy.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable stream-buddy
sudo systemctl start stream-buddy
```

### 7. Configure Nginx

Edit nginx config (resumebuddy.cv site):
```bash
sudo nano /etc/nginx/sites-available/resumebuddy.cv
```

Add inside the `server {}` block (paste content from `nginx-stream-buddy.conf`):
```nginx
# Main application proxy
location /stream-buddy/ {
    proxy_pass http://127.0.0.1:8088/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 300;
    proxy_send_timeout 300;
    proxy_buffering off;
}

# WebSocket endpoint
location /stream-buddy/ws/ {
    proxy_pass http://127.0.0.1:8088/ws/;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 3600;
    proxy_send_timeout 3600;
    proxy_buffering off;
}
```

Test and reload:
```bash
sudo nginx -t
sudo systemctl reload nginx
```

### 8. Verify Deployment
```bash
# Check service status
sudo systemctl status stream-buddy

# Check logs
sudo journalctl -u stream-buddy -f

# Test health endpoint
curl http://localhost:8088/health
```

---

## Access URL

After deployment: `https://your-domain.com/stream-buddy/`

---

## Troubleshooting

### Service won't start
```bash
sudo journalctl -u stream-buddy -n 50
```

### WebSocket connection fails
- Check nginx has WebSocket headers (Upgrade, Connection)
- Check `proxy_read_timeout` is high enough (86400)
- Verify wss:// is used on https sites

### Redis connection error
```bash
redis-cli ping  # Should return PONG
```

### Restart service
```bash
sudo systemctl restart stream-buddy
```

### View real-time logs
```bash
sudo journalctl -u stream-buddy -f
```

---

## Update Deployment

### Using deploy script
```bash
./deploy.sh
```

### Manual update
```bash
# On server
cd /home/ubuntu/resume-buddy/deploy/stream-buddy
# Pull latest files (rsync from local or git pull)
sudo systemctl restart stream-buddy
```

---

## Service Management

```bash
# Start
sudo systemctl start stream-buddy

# Stop
sudo systemctl stop stream-buddy

# Restart
sudo systemctl restart stream-buddy

# Status
sudo systemctl status stream-buddy

# Enable on boot
sudo systemctl enable stream-buddy

# Disable on boot
sudo systemctl disable stream-buddy
```
