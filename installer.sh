#!/usr/bin/env bash
set -euo pipefail

APP_NAME="tele2rub"
REPO_URL="http://github.com/mostafaafrouzi/telegramtorubika"
DEFAULT_INSTALL_DIR="/opt/tele2rub"
DEFAULT_SERVICE_NAME="tele2rub"
DEFAULT_BACKUP_DIR="/opt/tele2rub-backups"
LOG_FILE="/tmp/tele2rub-installer.log"
LOG_JSON_FILE="/tmp/tele2rub-installer.jsonl"

BLUE="\033[34m"; GREEN="\033[32m"; YELLOW="\033[33m"; RED="\033[31m"; RESET="\033[0m"
mkdir -p "$(dirname "$LOG_FILE")" >/dev/null 2>&1 || true
: > "$LOG_FILE"
: > "$LOG_JSON_FILE"

json_escape(){
  local s="${1:-}"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  s="${s//$'\r'/\\r}"
  s="${s//$'\t'/\\t}"
  echo "$s"
}

log_event(){
  local level="${1:-INFO}"; shift || true
  local event="${1:-message}"; shift || true
  local message="${*:-}"
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf '{"ts":"%s","level":"%s","event":"%s","message":"%s"}\n' \
    "$(json_escape "$ts")" \
    "$(json_escape "$level")" \
    "$(json_escape "$event")" \
    "$(json_escape "$message")" >> "$LOG_JSON_FILE"
}

info(){ echo -e "${BLUE}[INFO]${RESET} $*" | tee -a "$LOG_FILE"; log_event "INFO" "message" "$*"; }
ok(){ echo -e "${GREEN}[OK]${RESET} $*" | tee -a "$LOG_FILE"; log_event "OK" "message" "$*"; }
warn(){ echo -e "${YELLOW}[WARN]${RESET} $*" | tee -a "$LOG_FILE"; log_event "WARN" "message" "$*"; }
err(){ echo -e "${RED}[ERR]${RESET} $*" | tee -a "$LOG_FILE" >&2; log_event "ERR" "message" "$*"; }

run_cmd(){
  local d="$1"; shift
  local started_at ended_at elapsed rc cmd_text
  started_at="$(date +%s)"
  cmd_text="$*"
  info "$d"
  log_event "INFO" "command_start" "desc=$d cmd=$cmd_text"
  set +e
  "$@" >>"$LOG_FILE" 2>&1
  rc=$?
  set -e
  ended_at="$(date +%s)"
  elapsed=$((ended_at - started_at))
  if [[ $rc -eq 0 ]]; then
    ok "$d"
    log_event "OK" "command_end" "desc=$d cmd=$cmd_text exit_code=$rc elapsed_sec=$elapsed"
    return 0
  fi
  err "$d failed. See $LOG_FILE"
  log_event "ERR" "command_end" "desc=$d cmd=$cmd_text exit_code=$rc elapsed_sec=$elapsed"
  tail -n 40 "$LOG_FILE" || true
  return 1
}
pause(){ read -r -p "Press Enter to continue..."; }
ask(){
  local p="$1"; local def="${2:-}"; local v=""
  if [[ ! -t 0 ]]; then
    [[ -n "$def" ]] && { echo "$def"; return; }
    err "Non-interactive mode نیاز به مقدار پیش‌فرض دارد: $p"
    exit 1
  fi
  while true; do
    read -r -p "$p${def:+ [$def]}: " v
    v="${v:-$def}"
    [[ -n "$v" ]] && { echo "$v"; return; }
    warn "Value cannot be empty."
  done
}

ask_yn(){
  local p="$1"; local def="${2:-y}"; local v=""
  if [[ ! -t 0 ]]; then
    v="$def"
  else
    while true; do
      read -r -p "$p (y/n) [$def]: " v
      v="${v:-$def}"
      case "${v,,}" in y|yes) return 0;; n|no) return 1;; *) warn "Please choose y or n";; esac
    done
  fi
  case "${v,,}" in y|yes) return 0;; *) return 1;; esac
}

ensure_root(){ [[ "$EUID" -eq 0 ]] || { err "Run as root: sudo bash installer.sh"; exit 1; }; }
os_check(){ [[ -f /etc/os-release ]] || { err "Unsupported OS"; exit 1; }; source /etc/os-release; info "OS: ${PRETTY_NAME:-unknown}"; }

INST_NAMES=()
INST_DIRS=()
INST_USERS=()

discover_instances(){
  INST_NAMES=()
  INST_DIRS=()
  INST_USERS=()
  local f name dir user
  for f in /etc/systemd/system/*.service; do
    [[ -f "$f" ]] || continue
    name="$(basename "$f" .service)"
    dir="$(grep '^WorkingDirectory=' "$f" | head -n1 | sed 's/^WorkingDirectory=//' || true)"
    user="$(grep '^User=' "$f" | head -n1 | sed 's/^User=//' || true)"
    [[ -z "$dir" ]] && continue
    [[ -f "$dir/main.py" ]] || continue
    INST_NAMES+=("$name")
    INST_DIRS+=("$dir")
    INST_USERS+=("${user:-root}")
  done
}

select_instance(){
  discover_instances
  if [[ ${#INST_NAMES[@]} -eq 0 ]]; then
    warn "No installed Tele2Rub instances were auto-detected."
    return 1
  fi
  echo
  echo "Detected instances:"
  local i
  for i in "${!INST_NAMES[@]}"; do
    echo "$((i+1))) ${INST_NAMES[$i]}  dir=${INST_DIRS[$i]}  user=${INST_USERS[$i]}"
  done
  echo
  if [[ ! -t 0 ]]; then
    SELECTED_NAME="${INST_NAMES[0]}"
    SELECTED_DIR="${INST_DIRS[0]}"
    SELECTED_USER="${INST_USERS[0]}"
    info "Non-interactive mode: auto-selected instance ${SELECTED_NAME}"
    return 0
  fi
  local pick
  while true; do
    read -r -p "Choose instance [1-${#INST_NAMES[@]}]: " pick
    if [[ "$pick" =~ ^[0-9]+$ ]] && (( pick >= 1 && pick <= ${#INST_NAMES[@]} )); then
      SELECTED_NAME="${INST_NAMES[$((pick-1))]}"
      SELECTED_DIR="${INST_DIRS[$((pick-1))]}"
      SELECTED_USER="${INST_USERS[$((pick-1))]}"
      return 0
    fi
    warn "Invalid selection."
  done
}

install_deps(){
  if command -v apt-get >/dev/null 2>&1; then
    run_cmd "apt update" apt-get update
    run_cmd "install dependencies" apt-get install -y python3 python3-venv python3-pip git ffmpeg curl
    return
  fi
  if command -v dnf >/dev/null 2>&1; then
    run_cmd "install dependencies" dnf install -y python3 python3-pip python3-virtualenv git ffmpeg curl
    return
  fi
  err "No supported package manager found (apt/dnf)."; return 1
}

clone_or_update_repo(){
  local dir="$1"
  local tmp_clone=""

  if [[ -d "$dir/.git" ]]; then
    run_cmd "git fetch" git -C "$dir" fetch --all --tags || return 1
    run_cmd "git reset to origin/main" git -C "$dir" reset --hard origin/main || return 1
    return 0
  fi

  if [[ ! -d "$dir" || -z "$(ls -A "$dir" 2>/dev/null || true)" ]]; then
    run_cmd "clone repository" git clone "$REPO_URL" "$dir" || return 1
    return 0
  fi

  # Non-git existing directory (common when users copied files manually).
  # Clone to temp and sync code into install dir while preserving runtime data.
  tmp_clone="$(mktemp -d /tmp/tele2rub-src-XXXXXX)"
  run_cmd "clone repository to temp" git clone "$REPO_URL" "$tmp_clone" || return 1
  run_cmd "sync repository files to install dir" rsync -a --delete \
    --exclude ".git" \
    --exclude ".env" \
    --exclude "venv" \
    --exclude "queue" \
    --exclude "downloads" \
    "${tmp_clone}/" "${dir}/" || return 1
  run_cmd "cleanup temp clone" rm -rf "$tmp_clone" || true
}

setup_venv(){
  local dir="$1"
  run_cmd "create venv" python3 -m venv "$dir/venv"
  run_cmd "upgrade pip" "$dir/venv/bin/pip" install --upgrade pip
  run_cmd "install requirements" "$dir/venv/bin/pip" install -r "$dir/requirements.txt"
}

write_env(){
  local dir="$1" api_id="$2" api_hash="$3" bot_token="$4" rubika_session="$5" admin_ids="$6" part_size="$7"
  local build_version
  build_version="$(date +%Y.%m.%d-%H%M)"
  cat > "$dir/.env" <<EOF
API_ID=$api_id
API_HASH=$api_hash
BOT_TOKEN=$bot_token
RUBIKA_SESSION=$rubika_session
ADMIN_IDS=$admin_ids
DEFAULT_PART_SIZE_MB=$part_size
APP_BUILD_VERSION=$build_version
EOF
  ok "Saved $dir/.env"
}

update_build_version_in_env(){
  local dir="$1"
  local env_file="$dir/.env"
  [[ -f "$env_file" ]] || return 0
  local build_version
  build_version="$(date +%Y.%m.%d-%H%M)"
  if grep -q '^APP_BUILD_VERSION=' "$env_file"; then
    sed -i "s/^APP_BUILD_VERSION=.*/APP_BUILD_VERSION=$build_version/" "$env_file"
  else
    echo "APP_BUILD_VERSION=$build_version" >> "$env_file"
  fi
}

notify_admin(){
  local bot_token="$1" admin_ids_csv="$2" text="$3"
  IFS=',' read -r -a ids <<< "$admin_ids_csv"
  for id in "${ids[@]}"; do
    id="$(echo "$id" | xargs)"
    [[ -z "$id" ]] && continue
    curl -sS -X POST "https://api.telegram.org/bot${bot_token}/sendMessage" \
      -d "chat_id=$id" -d "text=$text" >>"$LOG_FILE" 2>&1 || true
  done
}

create_service(){
  local name="$1" dir="$2" user="$3"
  cat > "/etc/systemd/system/${name}.service" <<EOF
[Unit]
Description=Tele2Rub Bot Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${user}
WorkingDirectory=${dir}
ExecStart=${dir}/venv/bin/python ${dir}/main.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
  run_cmd "systemd daemon reload" systemctl daemon-reload
  run_cmd "enable service" systemctl enable "$name"
  run_cmd "restart service" systemctl restart "$name"
  run_cmd "service status" systemctl --no-pager --full status "$name"
}

post_deploy_health_check(){
  local svc="$1" dir="$2"
  info "Running post-deploy health checks..."
  run_cmd "service is-active check" systemctl is-active --quiet "$svc"
  run_cmd "service is-enabled check" systemctl is-enabled --quiet "$svc"
  run_cmd "python syntax smoke check" "$dir/venv/bin/python" -m py_compile "$dir/main.py" "$dir/telebot.py" "$dir/rub.py" "$dir/queue_db.py"
  ok "Health check passed for service=$svc dir=$dir"
  log_event "OK" "health_check_passed" "service=$svc dir=$dir"
}

show_requirements_reminder(){
  echo "Before installation, prepare these values:"
  echo "- Telegram API_ID"
  echo "- Telegram API_HASH"
  echo "- Telegram BOT_TOKEN (BotFather)"
  echo "- ADMIN_IDS (comma-separated Telegram user IDs)"
  echo "- Optional: RUBIKA_SESSION name"
  echo "- Optional: DEFAULT_PART_SIZE_MB"
}

install_flow(){
  ensure_root; os_check; show_requirements_reminder
  ask_yn "Do you have all required values and want to continue?" "y" || return 0
  local dir svc user api_id api_hash bot_token rub_sess admin_ids part_size
  dir="$(ask "Install directory" "$DEFAULT_INSTALL_DIR")"
  svc="$(ask "Systemd service name" "$DEFAULT_SERVICE_NAME")"
  user="$(ask "Run service as user" "root")"
  api_id="$(ask "Telegram API_ID")"; api_hash="$(ask "Telegram API_HASH")"; bot_token="$(ask "Telegram BOT_TOKEN")"
  rub_sess="$(ask "Default RUBIKA_SESSION name" "rubika_session")"
  admin_ids="$(ask "ADMIN_IDS (comma-separated)")"
  part_size="$(ask "DEFAULT_PART_SIZE_MB" "1900")"
  install_deps
  clone_or_update_repo "$dir" || return 1
  setup_venv "$dir" || return 1
  write_env "$dir" "$api_id" "$api_hash" "$bot_token" "$rub_sess" "$admin_ids" "$part_size" || return 1
  create_service "$svc" "$dir" "$user" || return 1
  post_deploy_health_check "$svc" "$dir" || return 1
  notify_admin "$bot_token" "$admin_ids" "telegramtorubika install successful on $(hostname)"
  ok "Install completed."
}

update_flow(){
  ensure_root; os_check
  local dir svc user bot_token admin_ids
  if select_instance; then
    dir="$SELECTED_DIR"; svc="$SELECTED_NAME"; user="$SELECTED_USER"
    info "Selected instance: $svc ($dir)"
  else
    dir="$(ask "Install directory" "$DEFAULT_INSTALL_DIR")"
    svc="$(ask "Systemd service name" "$DEFAULT_SERVICE_NAME")"
    user="$(ask "Run service as user" "root")"
  fi
  [[ -d "$dir" ]] || { err "Install directory not found: $dir"; return 1; }
  if ask_yn "Create backup before update?" "y"; then backup_flow "$dir"; fi
  run_cmd "stop service" systemctl stop "$svc" || true
  install_deps || return 1
  clone_or_update_repo "$dir" || return 1
  setup_venv "$dir" || return 1
  update_build_version_in_env "$dir"
  create_service "$svc" "$dir" "$user" || return 1
  post_deploy_health_check "$svc" "$dir" || return 1
  if [[ -f "$dir/.env" ]]; then
    bot_token="$(grep '^BOT_TOKEN=' "$dir/.env" | sed 's/^BOT_TOKEN=//' || true)"
    admin_ids="$(grep '^ADMIN_IDS=' "$dir/.env" | sed 's/^ADMIN_IDS=//' || true)"
    [[ -n "$bot_token" && -n "$admin_ids" ]] && notify_admin "$bot_token" "$admin_ids" "telegramtorubika update successful on $(hostname)"
  fi
  ok "Update completed."
}

backup_flow(){
  ensure_root
  local dir="${1:-}" bdir stamp out
  if [[ -z "$dir" ]]; then
    if select_instance; then
      dir="$SELECTED_DIR"
      info "Selected instance for backup: $SELECTED_NAME ($dir)"
    else
      dir="$(ask "Install directory" "$DEFAULT_INSTALL_DIR")"
    fi
  fi
  bdir="$(ask "Backup directory" "$DEFAULT_BACKUP_DIR")"
  [[ -d "$dir" ]] || { err "Install directory not found: $dir"; return 1; }
  run_cmd "create backup directory" mkdir -p "$bdir"
  stamp="$(date +%Y%m%d-%H%M%S)"; out="$bdir/tele2rub-$stamp.tar.gz"
  run_cmd "create backup archive" tar -czf "$out" -C "$dir" .
  ok "Backup created: $out"
}

restore_flow(){
  ensure_root
  local dir svc archive
  if select_instance; then
    dir="$SELECTED_DIR"; svc="$SELECTED_NAME"
    info "Selected instance for restore: $svc ($dir)"
  else
    dir="$(ask "Install directory" "$DEFAULT_INSTALL_DIR")"
    svc="$(ask "Systemd service name" "$DEFAULT_SERVICE_NAME")"
  fi
  archive="$(ask "Backup file (.tar.gz) path")"
  [[ -f "$archive" ]] || { err "Backup not found: $archive"; return 1; }
  ask_yn "This will overwrite files in $dir. Continue?" "n" || return 0
  run_cmd "stop service" systemctl stop "$svc" || true
  run_cmd "create install directory" mkdir -p "$dir"
  run_cmd "restore archive" tar -xzf "$archive" -C "$dir"
  run_cmd "restart service" systemctl restart "$svc" || true
  run_cmd "service status" systemctl --no-pager --full status "$svc" || true
  ok "Restore completed."
}

uninstall_flow(){
  ensure_root
  local dir svc
  if select_instance; then
    dir="$SELECTED_DIR"; svc="$SELECTED_NAME"
    info "Selected instance for uninstall: $svc ($dir)"
  else
    dir="$(ask "Install directory" "$DEFAULT_INSTALL_DIR")"
    svc="$(ask "Systemd service name" "$DEFAULT_SERVICE_NAME")"
  fi
  ask_yn "Uninstall service and delete $dir ?" "n" || return 0
  run_cmd "stop service" systemctl stop "$svc" || true
  run_cmd "disable service" systemctl disable "$svc" || true
  run_cmd "remove service file" rm -f "/etc/systemd/system/${svc}.service"
  run_cmd "systemd daemon reload" systemctl daemon-reload
  [[ -d "$dir" ]] && run_cmd "remove install directory" rm -rf "$dir" || warn "Install directory does not exist."
  ok "Uninstall completed."
}

logs_flow(){
  local svc
  if select_instance; then
    svc="$SELECTED_NAME"
    info "Selected instance for logs: $svc"
  else
    svc="$(ask "Systemd service name" "$DEFAULT_SERVICE_NAME")"
  fi
  info "Installer logs: $LOG_FILE"
  info "Installer JSON logs: $LOG_JSON_FILE"
  journalctl -u "$svc" -f -n 120
}

menu(){
  while true; do
    clear
    echo "======================================"
    echo " Tele2Rub Interactive Installer"
    echo "======================================"
    echo "1) Install"
    echo "2) Update"
    echo "3) Uninstall"
    echo "4) Backup"
    echo "5) Restore"
    echo "6) Show Service Logs"
    echo "7) Exit"
    echo
    read -r -p "Choose [1-7]: " c
    case "$c" in
      1) install_flow || err "Install failed"; pause ;;
      2) update_flow || err "Update failed"; pause ;;
      3) uninstall_flow || err "Uninstall failed"; pause ;;
      4) backup_flow || err "Backup failed"; pause ;;
      5) restore_flow || err "Restore failed"; pause ;;
      6) logs_flow || true; pause ;;
      7) exit 0 ;;
      *) warn "Invalid choice"; pause ;;
    esac
  done
}

run_quick_flag(){
  local flag="${1:-}"
  case "$flag" in
    --install) install_flow; exit $? ;;
    --update) update_flow; exit $? ;;
    --uninstall) uninstall_flow; exit $? ;;
    --backup) backup_flow; exit $? ;;
    --restore) restore_flow; exit $? ;;
    --logs) logs_flow; exit $? ;;
    "") return 0 ;;
    *)
      err "Unknown flag: $flag"
      echo "Usage: bash installer.sh [--install|--update|--uninstall|--backup|--restore|--logs]"
      exit 1
      ;;
  esac
}

run_quick_flag "${1:-}"
menu
