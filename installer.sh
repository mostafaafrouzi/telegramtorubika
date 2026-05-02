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

INST_LABELS=()
INST_DIRS=()
INST_USERS=()
INST_BASES=()
INST_SPLITS=()

discover_instances(){
  INST_LABELS=()
  INST_DIRS=()
  INST_USERS=()
  INST_BASES=()
  INST_SPLITS=()
  local f name dir user ex base
  declare -A dir_has_combined dir_combined_name dir_combined_user
  declare -A dir_split_base dir_split_user

  for f in /etc/systemd/system/*.service; do
    [[ -f "$f" ]] || continue
    name="$(basename "$f" .service)"
    dir="$(grep '^WorkingDirectory=' "$f" | head -n1 | sed 's/^WorkingDirectory=//' || true)"
    user="$(grep '^User=' "$f" | head -n1 | sed 's/^User=//' || true)"
    [[ -z "$dir" ]] || [[ ! -f "$dir/main.py" ]] && continue
    ex="$(grep '^ExecStart=' "$f" | head -n1 || true)"
    if [[ "$ex" == *'/main.py'* ]] || [[ "$ex" == *' main.py'* ]]; then
      dir_has_combined["$dir"]=1
      dir_combined_name["$dir"]="$name"
      dir_combined_user["$dir"]="${user:-root}"
    elif [[ "$ex" == *telebot.py* ]]; then
      base="${name%-bot}"
      [[ "$base" == "$name" ]] && base="$name"
      dir_split_base["$dir"]="$base"
      dir_split_user["$dir"]="${user:-root}"
    fi
  done

  for dir in "${!dir_has_combined[@]}"; do
    INST_DIRS+=("$dir")
    INST_USERS+=("${dir_combined_user[$dir]}")
    INST_BASES+=("${dir_combined_name[$dir]}")
    INST_SPLITS+=(0)
    INST_LABELS+=("${dir_combined_name[$dir]}")
  done

  for dir in "${!dir_split_base[@]}"; do
    [[ -n "${dir_has_combined[$dir]:-}" ]] && continue
    INST_DIRS+=("$dir")
    INST_USERS+=("${dir_split_user[$dir]}")
    INST_BASES+=("${dir_split_base[$dir]}")
    INST_SPLITS+=(1)
    INST_LABELS+=("${dir_split_base[$dir]} (split)")
  done
}

select_instance(){
  discover_instances
  if [[ ${#INST_DIRS[@]} -eq 0 ]]; then
    warn "No installed Tele2Rub instances were auto-detected."
    return 1
  fi
  echo
  echo "Detected instances:"
  local i
  for i in "${!INST_DIRS[@]}"; do
    echo "$((i+1))) ${INST_LABELS[$i]}  dir=${INST_DIRS[$i]}  user=${INST_USERS[$i]}  systemd=${INST_BASES[$i]}  split=${INST_SPLITS[$i]}"
  done
  echo
  if [[ ! -t 0 ]]; then
    SELECTED_LABEL="${INST_LABELS[0]}"
    SELECTED_DIR="${INST_DIRS[0]}"
    SELECTED_USER="${INST_USERS[0]}"
    SELECTED_BASE="${INST_BASES[0]}"
    SELECTED_SPLIT="${INST_SPLITS[0]}"
    info "Non-interactive mode: auto-selected instance ${SELECTED_LABEL}"
    return 0
  fi
  local pick
  while true; do
    read -r -p "Choose instance [1-${#INST_DIRS[@]}]: " pick
    if [[ "$pick" =~ ^[0-9]+$ ]] && (( pick >= 1 && pick <= ${#INST_DIRS[@]} )); then
      SELECTED_LABEL="${INST_LABELS[$((pick-1))]}"
      SELECTED_DIR="${INST_DIRS[$((pick-1))]}"
      SELECTED_USER="${INST_USERS[$((pick-1))]}"
      SELECTED_BASE="${INST_BASES[$((pick-1))]}"
      SELECTED_SPLIT="${INST_SPLITS[$((pick-1))]}"
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
    --exclude "*.session" \
    --exclude "*.session-journal" \
    --exclude "*.sqlite" \
    "${tmp_clone}/" "${dir}/" || return 1
  # *.session / *.sqlite = Telegram + Rubika/pyrogram sessions (avoid wiping logins on update)
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

read_app_version(){
  local env_file="${1:-}"
  [[ -n "$env_file" && -f "$env_file" ]] || { echo "unknown"; return; }
  grep '^APP_BUILD_VERSION=' "$env_file" 2>/dev/null | head -n1 | sed 's/^APP_BUILD_VERSION=//' || echo "unknown"
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

stop_instance_services(){
  local base="$1" split="${2:-0}"
  if [[ "$split" == "1" ]]; then
    systemctl stop "${base}-bot" >>"$LOG_FILE" 2>&1 || true
    systemctl stop "${base}-worker" >>"$LOG_FILE" 2>&1 || true
  else
    systemctl stop "$base" >>"$LOG_FILE" 2>&1 || true
  fi
}

restart_instance_services(){
  local base="$1" split="${2:-0}"
  if [[ "$split" == "1" ]]; then
    run_cmd "restart bot" systemctl restart "${base}-bot"
    run_cmd "restart worker" systemctl restart "${base}-worker"
  else
    run_cmd "restart service" systemctl restart "$base"
  fi
}

create_service_split(){
  local base="$1" dir="$2" user="$3"
  local bot="${base}-bot" worker="${base}-worker"
  if [[ -f "/etc/systemd/system/${base}.service" ]]; then
    systemctl stop "$base" >>"$LOG_FILE" 2>&1 || true
    systemctl disable "$base" >>"$LOG_FILE" 2>&1 || true
    run_cmd "remove combined unit (migrate to split)" rm -f "/etc/systemd/system/${base}.service"
  fi
  cat > "/etc/systemd/system/${bot}.service" <<EOF
[Unit]
Description=Tele2Rub Telegram bot (telebot.py)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${user}
WorkingDirectory=${dir}
ExecStart=${dir}/venv/bin/python ${dir}/telebot.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
  cat > "/etc/systemd/system/${worker}.service" <<EOF
[Unit]
Description=Tele2Rub Rubika worker (rub.py)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${user}
WorkingDirectory=${dir}
ExecStart=${dir}/venv/bin/python ${dir}/rub.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
  run_cmd "systemd daemon reload" systemctl daemon-reload
  run_cmd "enable bot" systemctl enable "$bot"
  run_cmd "enable worker" systemctl enable "$worker"
  run_cmd "restart bot" systemctl restart "$bot"
  run_cmd "restart worker" systemctl restart "$worker"
  run_cmd "service status (bot)" systemctl --no-pager --full status "$bot"
  run_cmd "service status (worker)" systemctl --no-pager --full status "$worker"
}

create_service(){
  local name="$1" dir="$2" user="$3" split="${4:-0}"
  if [[ "$split" == "1" ]]; then
    create_service_split "$name" "$dir" "$user"
    return 0
  fi
  if [[ -f "/etc/systemd/system/${name}-bot.service" ]] || [[ -f "/etc/systemd/system/${name}-worker.service" ]]; then
    systemctl stop "${name}-bot" >>"$LOG_FILE" 2>&1 || true
    systemctl stop "${name}-worker" >>"$LOG_FILE" 2>&1 || true
    systemctl disable "${name}-bot" >>"$LOG_FILE" 2>&1 || true
    systemctl disable "${name}-worker" >>"$LOG_FILE" 2>&1 || true
    run_cmd "remove split units (switch to combined)" rm -f "/etc/systemd/system/${name}-bot.service" "/etc/systemd/system/${name}-worker.service"
  fi
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
  local base="$1" dir="$2" split="${3:-0}"
  info "Running post-deploy health checks..."
  if [[ "$split" == "1" ]]; then
    run_cmd "bot is-active" systemctl is-active --quiet "${base}-bot"
    run_cmd "worker is-active" systemctl is-active --quiet "${base}-worker"
    run_cmd "bot is-enabled" systemctl is-enabled --quiet "${base}-bot"
    run_cmd "worker is-enabled" systemctl is-enabled --quiet "${base}-worker"
  else
    run_cmd "service is-active check" systemctl is-active --quiet "$base"
    run_cmd "service is-enabled check" systemctl is-enabled --quiet "$base"
  fi
  run_cmd "python syntax smoke check" "$dir/venv/bin/python" -m py_compile "$dir/main.py" "$dir/telebot.py" "$dir/rub.py" "$dir/queue_db.py" "$dir/user_entitlements.py"
  ok "Health check passed for systemd_base=$base split=$split dir=$dir"
  log_event "OK" "health_check_passed" "systemd_base=$base split=$split dir=$dir"
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
  local split_flag=0
  if ask_yn "Use separate systemd units for Telegram bot and Rubika worker? (${svc}-bot + ${svc}-worker; less RAM per process on small VPS)" "n"; then
    split_flag=1
  fi
  install_deps
  clone_or_update_repo "$dir" || return 1
  setup_venv "$dir" || return 1
  write_env "$dir" "$api_id" "$api_hash" "$bot_token" "$rub_sess" "$admin_ids" "$part_size" || return 1
  create_service "$svc" "$dir" "$user" "$split_flag" || return 1
  post_deploy_health_check "$svc" "$dir" "$split_flag" || return 1
  local ver
  ver="$(read_app_version "$dir/.env")"
  notify_admin "$bot_token" "$admin_ids" "telegramtorubika install successful on $(hostname) version=${ver}"
  ok "Install completed."
}

update_flow(){
  ensure_root; os_check
  local dir svc user bot_token admin_ids split_flag=0
  if select_instance; then
    dir="$SELECTED_DIR"
    svc="$SELECTED_BASE"
    user="$SELECTED_USER"
    split_flag="$SELECTED_SPLIT"
    info "Selected instance: $SELECTED_LABEL ($dir)"
  else
    dir="$(ask "Install directory" "$DEFAULT_INSTALL_DIR")"
    svc="$(ask "Systemd service name (base name, without -bot/-worker)" "$DEFAULT_SERVICE_NAME")"
    user="$(ask "Run service as user" "root")"
    if ask_yn "Does this install use split bot+worker systemd units?" "n"; then
      split_flag=1
    fi
  fi
  [[ -d "$dir" ]] || { err "Install directory not found: $dir"; return 1; }
  if ask_yn "Create backup before update?" "y"; then backup_flow "$dir"; fi
  stop_instance_services "$svc" "$split_flag"
  install_deps || return 1
  clone_or_update_repo "$dir" || return 1
  setup_venv "$dir" || return 1
  update_build_version_in_env "$dir"
  create_service "$svc" "$dir" "$user" "$split_flag" || return 1
  post_deploy_health_check "$svc" "$dir" "$split_flag" || return 1
  if [[ -f "$dir/.env" ]]; then
    bot_token="$(grep '^BOT_TOKEN=' "$dir/.env" | sed 's/^BOT_TOKEN=//' || true)"
    admin_ids="$(grep '^ADMIN_IDS=' "$dir/.env" | sed 's/^ADMIN_IDS=//' || true)"
    local ver
    ver="$(read_app_version "$dir/.env")"
    [[ -n "$bot_token" && -n "$admin_ids" ]] && notify_admin "$bot_token" "$admin_ids" "telegramtorubika update successful on $(hostname) version=${ver}"
  fi
  ok "Update completed."
}

backup_flow(){
  ensure_root
  local dir="${1:-}" bdir stamp out
  if [[ -z "$dir" ]]; then
    if select_instance; then
      dir="$SELECTED_DIR"
      info "Selected instance for backup: $SELECTED_LABEL ($dir)"
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
  local dir base archive split_flag=0
  if select_instance; then
    dir="$SELECTED_DIR"
    base="$SELECTED_BASE"
    split_flag="$SELECTED_SPLIT"
    info "Selected instance for restore: $SELECTED_LABEL ($dir)"
  else
    dir="$(ask "Install directory" "$DEFAULT_INSTALL_DIR")"
    base="$(ask "Systemd service name (base name)" "$DEFAULT_SERVICE_NAME")"
    [[ -f "/etc/systemd/system/${base}-bot.service" ]] && split_flag=1
  fi
  archive="$(ask "Backup file (.tar.gz) path")"
  [[ -f "$archive" ]] || { err "Backup not found: $archive"; return 1; }
  ask_yn "This will overwrite files in $dir. Continue?" "n" || return 0
  stop_instance_services "$base" "$split_flag"
  run_cmd "create install directory" mkdir -p "$dir"
  run_cmd "restore archive" tar -xzf "$archive" -C "$dir"
  restart_instance_services "$base" "$split_flag"
  if [[ "$split_flag" == "1" ]]; then
    run_cmd "service status (bot)" systemctl --no-pager --full status "${base}-bot" || true
    run_cmd "service status (worker)" systemctl --no-pager --full status "${base}-worker" || true
  else
    run_cmd "service status" systemctl --no-pager --full status "$base" || true
  fi
  ok "Restore completed."
}

uninstall_flow(){
  ensure_root
  local dir base split_flag=0
  if select_instance; then
    dir="$SELECTED_DIR"
    base="$SELECTED_BASE"
    split_flag="$SELECTED_SPLIT"
    info "Selected instance for uninstall: $SELECTED_LABEL ($dir)"
  else
    dir="$(ask "Install directory" "$DEFAULT_INSTALL_DIR")"
    base="$(ask "Systemd service name (base name)" "$DEFAULT_SERVICE_NAME")"
    [[ -f "/etc/systemd/system/${base}-bot.service" ]] && split_flag=1
  fi
  ask_yn "Uninstall service and delete $dir ?" "n" || return 0
  stop_instance_services "$base" "$split_flag"
  if [[ "$split_flag" == "1" ]]; then
    run_cmd "disable bot" systemctl disable "${base}-bot" || true
    run_cmd "disable worker" systemctl disable "${base}-worker" || true
    run_cmd "remove split unit files" rm -f "/etc/systemd/system/${base}-bot.service" "/etc/systemd/system/${base}-worker.service"
  else
    run_cmd "disable service" systemctl disable "$base" || true
    run_cmd "remove service file" rm -f "/etc/systemd/system/${base}.service"
  fi
  run_cmd "systemd daemon reload" systemctl daemon-reload
  [[ -d "$dir" ]] && run_cmd "remove install directory" rm -rf "$dir" || warn "Install directory does not exist."
  ok "Uninstall completed."
}

logs_flow(){
  local base split_flag=0
  if select_instance; then
    base="$SELECTED_BASE"
    split_flag="$SELECTED_SPLIT"
    info "Selected instance for logs: $SELECTED_LABEL"
  else
    base="$(ask "Systemd service name (base name)" "$DEFAULT_SERVICE_NAME")"
    [[ -f "/etc/systemd/system/${base}-bot.service" ]] && split_flag=1
  fi
  info "Installer logs: $LOG_FILE"
  info "Installer JSON logs: $LOG_JSON_FILE"
  if [[ "$split_flag" == "1" ]]; then
    journalctl -u "${base}-bot" -u "${base}-worker" -f -n 120
  else
    journalctl -u "$base" -f -n 120
  fi
}

installer_logs_flow(){
  info "Showing installer text logs: $LOG_FILE"
  tail -n 300 "$LOG_FILE" || true
}

installer_json_logs_flow(){
  info "Showing installer JSON logs: $LOG_JSON_FILE"
  tail -n 300 "$LOG_JSON_FILE" || true
}

bot_logs_flow(){
  local dir
  if select_instance; then
    dir="$SELECTED_DIR"
    info "Selected instance for bot logs: $SELECTED_LABEL ($dir)"
  else
    dir="$(ask "Install directory" "$DEFAULT_INSTALL_DIR")"
  fi
  info "Showing bot logs: $dir/queue/bot_events.jsonl"
  tail -n 300 "$dir/queue/bot_events.jsonl" || true
}

worker_logs_flow(){
  local dir
  if select_instance; then
    dir="$SELECTED_DIR"
    info "Selected instance for worker logs: $SELECTED_LABEL ($dir)"
  else
    dir="$(ask "Install directory" "$DEFAULT_INSTALL_DIR")"
  fi
  info "Showing worker logs: $dir/queue/worker_events.jsonl"
  tail -n 300 "$dir/queue/worker_events.jsonl" || true
}

all_logs_flow(){
  # Avoid exiting entire script on missing files / journal quirks (set -e at top of installer)
  set +e
  local base dir out split_flag=0
  if select_instance; then
    base="$SELECTED_BASE"
    split_flag="$SELECTED_SPLIT"
    dir="$SELECTED_DIR"
    info "Selected instance for all logs: $SELECTED_LABEL ($dir)"
  else
    dir="$(ask "Install directory" "$DEFAULT_INSTALL_DIR")"
    base="$(ask "Systemd service name (base name)" "$DEFAULT_SERVICE_NAME")"
    [[ -f "/etc/systemd/system/${base}-bot.service" ]] && split_flag=1
  fi

  [[ -z "${base:-}" ]] && base="$DEFAULT_SERVICE_NAME"
  [[ -z "${dir:-}" ]] && dir="$DEFAULT_INSTALL_DIR"

  out="/tmp/tele2rub-all-logs-$(date +%Y%m%d-%H%M%S).txt"
  {
    echo "===== TELE2RUB ALL LOGS ====="
    echo "generated_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "systemd_base=$base"
    echo "split=$split_flag"
    echo "install_dir=$dir"
    echo

    echo "===== INSTALLER LOG (tail -n 300) ====="
    tail -n 300 "$LOG_FILE" 2>/dev/null || echo "(missing) $LOG_FILE"
    echo

    echo "===== INSTALLER JSON LOG (tail -n 300) ====="
    tail -n 300 "$LOG_JSON_FILE" 2>/dev/null || echo "(missing) $LOG_JSON_FILE"
    echo

    echo "===== SERVICE JOURNAL (tail -n 300) ====="
    if [[ "$split_flag" == "1" ]]; then
      journalctl -u "${base}-bot" -u "${base}-worker" -n 300 --no-pager 2>/dev/null || echo "(journal unavailable for ${base}-bot / ${base}-worker)"
    else
      journalctl -u "$base" -n 300 --no-pager 2>/dev/null || echo "(journal unavailable for $base)"
    fi
    echo

    echo "===== BOT EVENTS (tail -n 300) ====="
    tail -n 300 "$dir/queue/bot_events.jsonl" 2>/dev/null || echo "(missing) $dir/queue/bot_events.jsonl"
    echo

    echo "===== WORKER EVENTS (tail -n 300) ====="
    tail -n 300 "$dir/queue/worker_events.jsonl" 2>/dev/null || echo "(missing) $dir/queue/worker_events.jsonl"
    echo
  } > "$out"
  local rc=$?
  set -e

  ok "All logs exported: $out"
  echo
  cat "$out"
  return "$rc"
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
    echo "7) Show Installer Logs"
    echo "8) Show Installer JSON Logs"
    echo "9) Show Bot Logs"
    echo "10) Show Worker Logs"
    echo "11) Export + Show All Logs (copy-friendly)"
    echo "12) Exit"
    echo
    read -r -p "Choose [1-12]: " c
    case "$c" in
      1) install_flow || err "Install failed"; pause ;;
      2) update_flow || err "Update failed"; pause ;;
      3) uninstall_flow || err "Uninstall failed"; pause ;;
      4) backup_flow || err "Backup failed"; pause ;;
      5) restore_flow || err "Restore failed"; pause ;;
      6) logs_flow || true; pause ;;
      7) installer_logs_flow || true; pause ;;
      8) installer_json_logs_flow || true; pause ;;
      9) bot_logs_flow || true; pause ;;
      10) worker_logs_flow || true; pause ;;
      11) all_logs_flow || true; pause ;;
      12) exit 0 ;;
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
    --installer-logs) installer_logs_flow; exit $? ;;
    --installer-json-logs) installer_json_logs_flow; exit $? ;;
    --bot-logs) bot_logs_flow; exit $? ;;
    --worker-logs) worker_logs_flow; exit $? ;;
    --all-logs) all_logs_flow; exit $? ;;
    "") return 0 ;;
    *)
      err "Unknown flag: $flag"
      echo "Usage: bash installer.sh [--install|--update|--uninstall|--backup|--restore|--logs|--installer-logs|--installer-json-logs|--bot-logs|--worker-logs|--all-logs]"
      exit 1
      ;;
  esac
}

# Flag mode: never fall through to interactive menu (avoids confusing UX after --all-logs etc.)
if [[ -n "${1:-}" ]]; then
  run_quick_flag "${1}"
else
  menu
fi
