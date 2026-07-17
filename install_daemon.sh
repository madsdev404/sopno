#!/bin/bash

# Sopno User Daemon Installer
# Installs Sopno as a systemd user service

SERVICE_NAME="sopno"
USER_SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$USER_SERVICE_DIR/$SERVICE_NAME.service"
PROJECT_DIR="$(pwd)"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python3"
SCRIPT_PATH="$PROJECT_DIR/gui.py"

echo "========================================="
echo "   SOPNO SYSTEMD USER SERVICE INSTALLER  "
echo "========================================="

# Ensure directories exist
mkdir -p "$USER_SERVICE_DIR"

# Check if venv python exists
if [ ! -f "$VENV_PYTHON" ]; then
    echo "Error: Virtual environment python not found at $VENV_PYTHON"
    echo "Please set up virtual environment first."
    exit 1
fi

# Write systemd user service file
cat <<EOF > "$SERVICE_FILE"
[Unit]
Description=Sopno AI Voice Assistant HUD
After=default.target sound.target

[Service]
Type=simple
WorkingDirectory=$PROJECT_DIR
ExecStart=$VENV_PYTHON $SCRIPT_PATH
Restart=always
RestartSec=5
Environment=DISPLAY=:0
Environment=XAUTHORITY=$HOME/.Xauthority

[Install]
WantedBy=default.target
EOF

echo "✓ User service file written to $SERVICE_FILE"

# Reload systemd user daemon
systemctl --user daemon-reload
echo "✓ Systemd user daemon reloaded."

# Enable and start the service
systemctl --user enable "$SERVICE_NAME"
systemctl --user start "$SERVICE_NAME"

echo "-----------------------------------------"
echo "✓ Sopno service enabled and started!"
echo "-----------------------------------------"
echo "To check the service status, run:"
echo "  systemctl --user status $SERVICE_NAME"
echo ""
echo "To view live logs from the service, run:"
echo "  journalctl --user -u $SERVICE_NAME -f"
echo ""
echo "To stop the service, run:"
echo "  systemctl --user stop $SERVICE_NAME"
echo "========================================="
