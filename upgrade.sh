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
    log_info "Updating scripts in /usr/local/bin/..."

    local scripts=(
        "chromium-panel.sh"
        "chromium-kiosk.sh"
        "chromium-admin.sh"
        "display-init.sh"
        "toggle-panel-kiosk.sh"
        "toggle-admin.sh"
        "switch-to-panel.sh"
        "switch-to-kiosk.sh"
    )

    for script in "${scripts[@]}"; do
        if [[ -f "$INSTALL_DIR/scripts/$script" ]]; then
            cp "$INSTALL_DIR/scripts/$script" "/usr/local/bin/$script"
            chmod +x "/usr/local/bin/$script"
        fi
    done

    log_success "Scripts updated"
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
    log_info "Updating scripts..."
    rm -rf "$INSTALL_DIR/scripts"
    cp -r "$source_dir/scripts" "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/scripts/"*.sh
    update_scripts

    # Update templates directory
    if [[ -d "$source_dir/templates" ]]; then
        rm -rf "$INSTALL_DIR/templates"
        cp -r "$source_dir/templates" "$INSTALL_DIR/"
    fi

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
