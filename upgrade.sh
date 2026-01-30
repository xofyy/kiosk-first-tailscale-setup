#!/bin/bash
# =============================================================================
# ACO Maintenance Panel - Upgrade Script
# Safe upgrade without touching MongoDB, UFW, or system configuration
# =============================================================================

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Paths
INSTALL_DIR="/opt/aco-panel"
BACKUP_DIR="/opt/aco-panel-backups"
LOG_DIR="/var/log/aco-panel"
VENV_DIR="$INSTALL_DIR/venv"
GITHUB_REPO="xofyy/kiosk-first-tailscale-setup"
GITHUB_RAW="https://raw.githubusercontent.com/$GITHUB_REPO/main"

# =============================================================================
# Helper Functions
# =============================================================================

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root (sudo)"
        exit 1
    fi
}

# Idempotent config deploy helper
# Copies src to dest only if different (or dest doesn't exist)
# Returns 0 if changed, 1 if unchanged
deploy_config() {
    local src="$1"
    local dest="$2"

    if [[ ! -f "$src" ]]; then
        return 1
    fi

    local dest_dir
    dest_dir=$(dirname "$dest")
    [[ -d "$dest_dir" ]] || mkdir -p "$dest_dir"

    if [[ -f "$dest" ]] && cmp -s "$src" "$dest"; then
        return 1
    fi

    cp "$src" "$dest"
    return 0
}

# =============================================================================
# Version Functions
# =============================================================================

get_current_version() {
    if [[ -f "$INSTALL_DIR/VERSION" ]]; then
        cat "$INSTALL_DIR/VERSION" | tr -d '[:space:]'
    else
        echo "0.0.0"
    fi
}

get_remote_version() {
    curl -sS "$GITHUB_RAW/VERSION" 2>/dev/null | tr -d '[:space:]' || echo ""
}

compare_versions() {
    # Returns: 0 if equal, 1 if $1 > $2, 2 if $1 < $2
    if [[ "$1" == "$2" ]]; then
        return 0
    fi

    local IFS=.
    local i ver1=($1) ver2=($2)

    for ((i=0; i<${#ver1[@]}; i++)); do
        if [[ -z ${ver2[i]} ]]; then
            ver2[i]=0
        fi
        if ((10#${ver1[i]} > 10#${ver2[i]})); then
            return 1
        fi
        if ((10#${ver1[i]} < 10#${ver2[i]})); then
            return 2
        fi
    done
    return 0
}

# =============================================================================
# Backup Functions
# =============================================================================

create_backup() {
    local current_version=$(get_current_version)
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_name="backup_${current_version}_${timestamp}"
    local backup_path="$BACKUP_DIR/$backup_name"

    log_info "Creating backup: $backup_name"

    mkdir -p "$BACKUP_DIR"
    mkdir -p "$backup_path"

    # Backup app directory
    if [[ -d "$INSTALL_DIR/app" ]]; then
        cp -r "$INSTALL_DIR/app" "$backup_path/"
    fi

    # Backup scripts
    if [[ -d "$INSTALL_DIR/scripts" ]]; then
        cp -r "$INSTALL_DIR/scripts" "$backup_path/"
    fi

    # Backup templates directory
    if [[ -d "$INSTALL_DIR/templates" ]]; then
        cp -r "$INSTALL_DIR/templates" "$backup_path/"
    fi

    # Backup configs
    if [[ -d "$INSTALL_DIR/configs" ]]; then
        cp -r "$INSTALL_DIR/configs" "$backup_path/"
    fi

    # Backup VERSION file
    if [[ -f "$INSTALL_DIR/VERSION" ]]; then
        cp "$INSTALL_DIR/VERSION" "$backup_path/"
    fi

    # Backup requirements.txt
    if [[ -f "$INSTALL_DIR/requirements.txt" ]]; then
        cp "$INSTALL_DIR/requirements.txt" "$backup_path/"
    fi

    # Save backup name for potential rollback
    echo "$backup_name" > "$BACKUP_DIR/.last_backup"

    log_success "Backup created: $backup_path"
    echo "$backup_path"
}

list_backups() {
    if [[ ! -d "$BACKUP_DIR" ]]; then
        log_warning "No backups found"
        return
    fi

    echo ""
    echo "Available backups:"
    echo "=================="
    ls -1t "$BACKUP_DIR" | grep -E "^backup_" | while read dir; do
        echo "  - $dir"
    done
    echo ""
}

rollback() {
    local backup_name="$1"

    # If no backup specified, use last backup
    if [[ -z "$backup_name" ]]; then
        if [[ -f "$BACKUP_DIR/.last_backup" ]]; then
            backup_name=$(cat "$BACKUP_DIR/.last_backup")
        else
            log_error "No backup specified and no last backup found"
            list_backups
            exit 1
        fi
    fi

    local backup_path="$BACKUP_DIR/$backup_name"

    if [[ ! -d "$backup_path" ]]; then
        log_error "Backup not found: $backup_path"
        list_backups
        exit 1
    fi

    log_info "Rolling back to: $backup_name"

    # Stop service
    log_info "Stopping aco-panel service..."
    systemctl stop aco-panel 2>/dev/null || true

    # Restore app directory
    if [[ -d "$backup_path/app" ]]; then
        rm -rf "$INSTALL_DIR/app"
        cp -r "$backup_path/app" "$INSTALL_DIR/"
        log_success "Restored app directory"
    fi

    # Restore scripts
    if [[ -d "$backup_path/scripts" ]]; then
        rm -rf "$INSTALL_DIR/scripts"
        cp -r "$backup_path/scripts" "$INSTALL_DIR/"
        update_scripts
        log_success "Restored scripts"
    fi

    # Restore templates
    if [[ -d "$backup_path/templates" ]]; then
        rm -rf "$INSTALL_DIR/templates"
        cp -r "$backup_path/templates" "$INSTALL_DIR/"
        log_success "Restored templates directory"
    fi

    # Restore configs
    if [[ -d "$backup_path/configs" ]]; then
        rm -rf "$INSTALL_DIR/configs"
        cp -r "$backup_path/configs" "$INSTALL_DIR/"
        log_success "Restored configs"
    fi

    # Deploy configs to system locations (idempotent)
    deploy_configs

    # Restore VERSION
    if [[ -f "$backup_path/VERSION" ]]; then
        cp "$backup_path/VERSION" "$INSTALL_DIR/"
        log_success "Restored VERSION"
    fi

    # Restore requirements and reinstall
    if [[ -f "$backup_path/requirements.txt" ]]; then
        cp "$backup_path/requirements.txt" "$INSTALL_DIR/"
        log_info "Reinstalling Python dependencies..."
        $VENV_DIR/bin/pip install -q -r "$INSTALL_DIR/requirements.txt"
        log_success "Restored requirements"
    fi

    # Start service
    log_info "Starting aco-panel service..."
    systemctl start aco-panel

    log_success "Rollback completed to version: $(get_current_version)"
}

# =============================================================================
# Update Functions
# =============================================================================

update_scripts() {
    log_info "Updating scripts..."

    # Scripts are already copied to $INSTALL_DIR/scripts in perform_upgrade
    # Just ensure they are executable
    chmod +x "$INSTALL_DIR/scripts/"*.sh 2>/dev/null || true

    log_success "Scripts updated"
}

deploy_configs() {
    log_info "Deploying configs to system locations..."

    local total_changes=0

    # -------------------------------------------------------------------------
    # Group 1: Systemd Services
    # -------------------------------------------------------------------------
    local SYSTEMD_CHANGED=false

    if deploy_config "$INSTALL_DIR/configs/systemd/aco-panel.service" \
                     "/etc/systemd/system/aco-panel.service"; then
        SYSTEMD_CHANGED=true
        total_changes=$((total_changes + 1))
    fi

    if deploy_config "$INSTALL_DIR/configs/systemd/getty-override.conf" \
                     "/etc/systemd/system/getty@tty1.service.d/override.conf"; then
        SYSTEMD_CHANGED=true
        total_changes=$((total_changes + 1))
    fi

    if deploy_config "$INSTALL_DIR/configs/systemd/aco-network-init.service" \
                     "/etc/systemd/system/aco-network-init.service"; then
        SYSTEMD_CHANGED=true
        total_changes=$((total_changes + 1))
    fi

    if deploy_config "$INSTALL_DIR/configs/systemd/x11vnc.service" \
                     "/etc/systemd/system/x11vnc.service"; then
        SYSTEMD_CHANGED=true
        total_changes=$((total_changes + 1))
    fi

    if deploy_config "$INSTALL_DIR/configs/systemd/nvidia-fallback.service" \
                     "/etc/systemd/system/nvidia-fallback.service"; then
        SYSTEMD_CHANGED=true
        total_changes=$((total_changes + 1))
    fi

    if deploy_config "$INSTALL_DIR/configs/systemd/firstboot-identity.service" \
                     "/etc/systemd/system/firstboot-identity.service"; then
        SYSTEMD_CHANGED=true
        total_changes=$((total_changes + 1))
    fi

    if deploy_config "$INSTALL_DIR/configs/systemd/display-monitor.service" \
                     "/etc/systemd/system/display-monitor.service"; then
        SYSTEMD_CHANGED=true
        total_changes=$((total_changes + 1))
    fi

    if [[ "$SYSTEMD_CHANGED" == "true" ]]; then
        systemctl daemon-reload
        log_info "systemd daemon-reload (unit files changed)"
    fi

    # -------------------------------------------------------------------------
    # Group 2: Kiosk User Configs
    # -------------------------------------------------------------------------
    local KIOSK_CHANGED=false

    if deploy_config "$INSTALL_DIR/configs/kiosk/openbox/rc.xml" \
                     "/home/kiosk/.config/openbox/rc.xml"; then
        KIOSK_CHANGED=true
        total_changes=$((total_changes + 1))
    fi

    if deploy_config "$INSTALL_DIR/configs/kiosk/openbox/autostart" \
                     "/home/kiosk/.config/openbox/autostart"; then
        KIOSK_CHANGED=true
        total_changes=$((total_changes + 1))
    fi

    if deploy_config "$INSTALL_DIR/configs/kiosk/bash_profile" \
                     "/home/kiosk/.bash_profile"; then
        KIOSK_CHANGED=true
        total_changes=$((total_changes + 1))
    fi

    if deploy_config "$INSTALL_DIR/configs/kiosk/xinitrc" \
                     "/home/kiosk/.xinitrc"; then
        KIOSK_CHANGED=true
        total_changes=$((total_changes + 1))
    fi

    if [[ "$KIOSK_CHANGED" == "true" ]]; then
        chmod +x /home/kiosk/.config/openbox/autostart 2>/dev/null || true
        chmod +x /home/kiosk/.xinitrc 2>/dev/null || true
        chown -R kiosk:kiosk /home/kiosk 2>/dev/null || true
        log_info "Kiosk user configs updated (permissions set)"
    fi

    # -------------------------------------------------------------------------
    # Group 3: Udev Rules
    # -------------------------------------------------------------------------
    local UDEV_CHANGED=false

    if deploy_config "$INSTALL_DIR/configs/udev/99-usb-cdc-acm.rules" \
                     "/etc/udev/rules.d/99-usb-cdc-acm.rules"; then
        UDEV_CHANGED=true
        total_changes=$((total_changes + 1))
    fi

    if [[ "$UDEV_CHANGED" == "true" ]]; then
        udevadm control --reload-rules && udevadm trigger
        log_info "Udev rules reloaded"
    fi

    # -------------------------------------------------------------------------
    # Group 4: Chromium Policy (no side effect needed)
    # -------------------------------------------------------------------------
    if deploy_config "$INSTALL_DIR/configs/chromium/aco-policy.json" \
                     "/etc/chromium-browser/policies/managed/aco-policy.json"; then
        total_changes=$((total_changes + 1))
    fi

    # -------------------------------------------------------------------------
    # Group 5: Nginx
    # -------------------------------------------------------------------------
    local NGINX_CHANGED=false

    if deploy_config "$INSTALL_DIR/configs/nginx/nginx.conf" \
                     "/etc/nginx/nginx.conf"; then
        NGINX_CHANGED=true
        total_changes=$((total_changes + 1))
    fi

    if deploy_config "$INSTALL_DIR/configs/nginx/nvr-proxy" \
                     "/etc/nginx/sites-available/nvr-proxy"; then
        NGINX_CHANGED=true
        total_changes=$((total_changes + 1))
    fi

    if [[ "$NGINX_CHANGED" == "true" ]]; then
        if nginx -t 2>/dev/null; then
            systemctl reload nginx 2>/dev/null || true
            log_info "Nginx reloaded (config changed)"
        else
            log_warning "Nginx config test failed - skipping reload"
        fi
    fi

    # -------------------------------------------------------------------------
    # Group 6: Cockpit
    # -------------------------------------------------------------------------
    local COCKPIT_CHANGED=false

    if deploy_config "$INSTALL_DIR/configs/cockpit/cockpit.conf" \
                     "/etc/cockpit/cockpit.conf"; then
        COCKPIT_CHANGED=true
        total_changes=$((total_changes + 1))
    fi

    if deploy_config "$INSTALL_DIR/configs/cockpit/50-aco-network.rules" \
                     "/etc/polkit-1/rules.d/50-aco-network.rules"; then
        COCKPIT_CHANGED=true
        total_changes=$((total_changes + 1))
    fi

    if [[ "$COCKPIT_CHANGED" == "true" ]]; then
        systemctl restart cockpit.socket 2>/dev/null || true
        log_info "Cockpit socket restarted"
    fi

    # -------------------------------------------------------------------------
    # Group 7: Docker configs (go2rtc)
    # -------------------------------------------------------------------------
    if deploy_config "$INSTALL_DIR/configs/go2rtc/go2rtc.yaml" \
                     "/srv/docker/go2rtc/go2rtc.yaml"; then
        total_changes=$((total_changes + 1))
    fi

    # -------------------------------------------------------------------------
    # Group 8: Logrotate config
    # -------------------------------------------------------------------------
    if deploy_config "$INSTALL_DIR/configs/logrotate/aco-panel" \
                     "/etc/logrotate.d/aco-panel"; then
        total_changes=$((total_changes + 1))
    fi

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    if [[ $total_changes -gt 0 ]]; then
        log_success "Deployed $total_changes config changes"
    else
        log_success "All configs already up to date"
    fi
}

download_and_extract() {
    local temp_dir=$(mktemp -d)
    local archive_url="https://github.com/$GITHUB_REPO/archive/refs/heads/main.tar.gz"

    log_info "Downloading latest version..." >&2

    if ! curl -sL "$archive_url" -o "$temp_dir/latest.tar.gz"; then
        log_error "Failed to download from GitHub" >&2
        rm -rf "$temp_dir"
        return 1
    fi

    log_info "Extracting..." >&2
    if ! tar -xzf "$temp_dir/latest.tar.gz" -C "$temp_dir"; then
        log_error "Failed to extract archive" >&2
        rm -rf "$temp_dir"
        return 1
    fi

    # Find extracted directory
    local extracted_dir=$(find "$temp_dir" -maxdepth 1 -type d -name "kiosk-*" | head -1)

    if [[ -z "$extracted_dir" ]]; then
        log_error "Could not find extracted directory" >&2
        rm -rf "$temp_dir"
        return 1
    fi

    echo "$extracted_dir"
}

perform_upgrade() {
    local source_dir="$1"

    # Stop service
    log_info "Stopping aco-panel service..."
    systemctl stop aco-panel 2>/dev/null || true
    sleep 2

    # Update app directory
    log_info "Updating app directory..."
    rm -rf "$INSTALL_DIR/app"
    cp -r "$source_dir/app" "$INSTALL_DIR/"

    # Update scripts
    rm -rf "$INSTALL_DIR/scripts"
    cp -r "$source_dir/scripts" "$INSTALL_DIR/"
    update_scripts

    # Update templates directory
    if [[ -d "$source_dir/templates" ]]; then
        rm -rf "$INSTALL_DIR/templates"
        cp -r "$source_dir/templates" "$INSTALL_DIR/"
    fi

    # Update configs
    if [[ -d "$source_dir/configs" ]]; then
        rm -rf "$INSTALL_DIR/configs"
        cp -r "$source_dir/configs" "$INSTALL_DIR/"
    fi

    # Deploy configs to system locations (idempotent)
    deploy_configs

    # Update VERSION
    cp "$source_dir/VERSION" "$INSTALL_DIR/"

    # Update requirements
    if [[ -f "$source_dir/requirements.txt" ]]; then
        cp "$source_dir/requirements.txt" "$INSTALL_DIR/"
        log_info "Updating Python dependencies..."
        $VENV_DIR/bin/pip install -q --upgrade -r "$INSTALL_DIR/requirements.txt"
    fi

    # Set permissions
    chown -R root:root "$INSTALL_DIR/app"
    chmod -R 755 "$INSTALL_DIR/app"

    # Start service
    log_info "Starting aco-panel service..."
    systemctl start aco-panel

    # Wait for service to start
    sleep 3

    # Verify
    if systemctl is-active --quiet aco-panel; then
        log_success "Service started successfully"
    else
        log_error "Service failed to start!"
        log_warning "Check logs: journalctl -u aco-panel -n 50"
        return 1
    fi

    log_success "Upgrade completed to version: $(get_current_version)"
}

cleanup_old_backups() {
    local keep_count=5

    if [[ ! -d "$BACKUP_DIR" ]]; then
        return
    fi

    local backup_count=$(ls -1 "$BACKUP_DIR" | grep -E "^backup_" | wc -l)

    if [[ $backup_count -gt $keep_count ]]; then
        log_info "Cleaning up old backups (keeping last $keep_count)..."
        ls -1t "$BACKUP_DIR" | grep -E "^backup_" | tail -n +$((keep_count + 1)) | while read dir; do
            rm -rf "$BACKUP_DIR/$dir"
            log_info "  Removed: $dir"
        done
    fi
}

# =============================================================================
# Main Functions
# =============================================================================

check_for_updates() {
    local current=$(get_current_version)
    local remote=$(get_remote_version)

    if [[ -z "$remote" ]]; then
        log_error "Could not fetch remote version"
        exit 1
    fi

    echo ""
    echo "Current version: $current"
    echo "Latest version:  $remote"
    echo ""

    compare_versions "$current" "$remote"
    local result=$?

    if [[ $result -eq 0 ]]; then
        log_success "You are running the latest version"
        return 1
    elif [[ $result -eq 1 ]]; then
        log_warning "Current version is newer than remote (development?)"
        return 1
    else
        log_info "Update available: $current → $remote"
        return 0
    fi
}

upgrade() {
    local force="$1"

    log_info "ACO Maintenance Panel Upgrade"
    echo "=============================="
    echo ""

    # Check if installation exists
    if [[ ! -d "$INSTALL_DIR/app" ]]; then
        log_error "ACO Panel not installed at $INSTALL_DIR"
        log_info "Run install.sh for fresh installation"
        exit 1
    fi

    # Check for updates
    if [[ "$force" != "true" ]]; then
        if ! check_for_updates; then
            exit 0
        fi

        echo ""
        read -p "Do you want to upgrade? [y/N] " -n 1 -r
        echo ""
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Upgrade cancelled"
            exit 0
        fi
    fi

    # Create backup
    echo ""
    create_backup

    # Download and extract
    echo ""
    local source_dir=$(download_and_extract)

    if [[ -z "$source_dir" || ! -d "$source_dir" ]]; then
        log_error "Failed to download update"
        exit 1
    fi

    # Perform upgrade
    echo ""
    perform_upgrade "$source_dir"

    # Cleanup
    rm -rf "$(dirname "$source_dir")"
    cleanup_old_backups

    echo ""
    log_success "Upgrade completed successfully!"
    echo ""
    echo "If you encounter issues, rollback with:"
    echo "  sudo bash upgrade.sh --rollback"
    echo ""
}

show_help() {
    echo ""
    echo "ACO Maintenance Panel - Upgrade Script"
    echo "======================================="
    echo ""
    echo "Usage: sudo bash upgrade.sh [OPTION]"
    echo ""
    echo "Options:"
    echo "  (no option)     Check for updates and upgrade interactively"
    echo "  --check         Check for updates only"
    echo "  --force         Upgrade without confirmation"
    echo "  --rollback      Rollback to last backup"
    echo "  --rollback NAME Rollback to specific backup"
    echo "  --list-backups  List available backups"
    echo "  --help          Show this help message"
    echo ""
    echo "Examples:"
    echo "  sudo bash upgrade.sh              # Interactive upgrade"
    echo "  sudo bash upgrade.sh --check      # Check version only"
    echo "  sudo bash upgrade.sh --force      # Upgrade without asking"
    echo "  sudo bash upgrade.sh --rollback   # Rollback to last backup"
    echo ""
}

# =============================================================================
# Main
# =============================================================================

main() {
    check_root

    case "${1:-}" in
        --help|-h)
            show_help
            ;;
        --check)
            check_for_updates
            ;;
        --force)
            upgrade "true"
            ;;
        --rollback)
            rollback "${2:-}"
            ;;
        --list-backups)
            list_backups
            ;;
        "")
            upgrade
            ;;
        *)
            log_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
}

main "$@"
