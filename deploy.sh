#!/bin/bash
# Stream Buddy Deployment Script
# Deploys to AWS Lightsail server (resume-buddy)

set -e

# Configuration
SSH_KEY="/home/katnyeung/resume-buddy.pem"
SERVER="ubuntu@13.43.37.64"
DEPLOY_PATH="/home/ubuntu/resume-buddy/deploy/stream-buddy"
SERVICE_NAME="stream-buddy"

# SSH/rsync options with key
SSH_OPTS="-i $SSH_KEY"
RSYNC_SSH="ssh -i $SSH_KEY"

echo "=========================================="
echo "Stream Buddy Deployment"
echo "=========================================="

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "ERROR: .env file not found!"
    echo "Please create .env with your API keys before deploying."
    exit 1
fi

echo ""
echo "[1/6] Creating remote directory..."
ssh $SSH_OPTS $SERVER "mkdir -p $DEPLOY_PATH"

echo ""
echo "[2/6] Uploading files..."
rsync -avz --progress -e "$RSYNC_SSH" \
    --exclude '.git' \
    --exclude '__pycache__' \
    --exclude '.venv' \
    --exclude 'venv' \
    --exclude '*.pyc' \
    --exclude '.env.local' \
    ./ $SERVER:$DEPLOY_PATH/

echo ""
echo "[3/6] Setting up Python environment..."
ssh $SSH_OPTS $SERVER "cd $DEPLOY_PATH && python3 -m venv .venv && source .venv/bin/activate && pip install -q -r requirements.txt"

echo ""
echo "[4/6] Installing systemd service..."
ssh $SSH_OPTS $SERVER "sudo cp $DEPLOY_PATH/$SERVICE_NAME.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable $SERVICE_NAME"

echo ""
echo "[5/6] Restarting service..."
ssh $SSH_OPTS $SERVER "sudo systemctl restart $SERVICE_NAME"

echo ""
echo "[6/6] Checking service status..."
sleep 2
ssh $SSH_OPTS $SERVER "sudo systemctl status $SERVICE_NAME --no-pager"

echo ""
echo "=========================================="
echo "Deployment Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Add nginx config (if not already done):"
echo "   ssh $SERVER"
echo "   sudo nano /etc/nginx/sites-available/default"
echo "   # Paste content from nginx-stream-buddy.conf"
echo "   sudo nginx -t && sudo systemctl reload nginx"
echo ""
echo "2. Access URL: https://your-domain.com/stream-buddy/"
echo ""
echo "View logs: ssh $SERVER 'sudo journalctl -u $SERVICE_NAME -f'"
