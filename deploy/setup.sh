#!/bin/bash
# DMP Packing Service - Initial Setup Script
# Run this once on the VPS to set up the service

set -e

echo "=== DMP Packing Service Setup ==="

# Install Python if not present
if ! command -v python3 &> /dev/null; then
    echo "Installing Python 3..."
    sudo apt update
    sudo apt install -y python3 python3-pip python3-venv
fi

# Create directory
echo "Creating service directory..."
sudo mkdir -p /var/www/dmp-packing-service
sudo chown $USER:$USER /var/www/dmp-packing-service

# Clone repository (replace with your actual repo URL)
echo "Cloning repository..."
cd /var/www
if [ -d "dmp-packing-service/.git" ]; then
    cd dmp-packing-service
    git pull origin main
else
    # Replace with your GitHub repo URL
    git clone https://github.com/awiw642/dmp-packing-service.git
    cd dmp-packing-service
fi

# Create virtual environment
echo "Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Set permissions
sudo chown -R www-data:www-data /var/www/dmp-packing-service

# Install systemd service
echo "Installing systemd service..."
sudo cp deploy/dmp-packing.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable dmp-packing
sudo systemctl start dmp-packing

# Check status
echo ""
echo "=== Setup Complete ==="
sudo systemctl status dmp-packing --no-pager

echo ""
echo "Service is running on http://127.0.0.1:8001"
echo "Don't forget to configure nginx reverse proxy!"
