# Transfer Adapters Specification (v2)

## 1) Goal
Unify all transfer features under one task model and adapter interface:
- Telegram <-> Rubika
- Telegram <-> Bale
- Telegram <-> Google Drive
- Link -> Telegram file
- Telegram file -> sharable link
- Zip/split + unzip pipeline

## 2) Transfer Task Model
```json
{
  "task_id": "uuid",
  "user_id": 123,
  "plugin": "transfer",
  "action": "upload|download|bridge|convert",
  "source": {"provider": "telegram|rubika|bale|drive|http", "ref": "..."},
  "destination": {"provider": "telegram|rubika|bale|drive|link", "ref": "..."},
  "options": {
    "zip": false,
    "unzip": false,
    "split_mb": 1900,
    "password": null,
    "overwrite": false
  }
}
```

## 3) Adapter Interface
Required methods per provider:
- `validate_account(user_ctx)`
- `resolve_source(task)`
- `download(source_ref, tmp_path)`
- `upload(local_path, destination_ref)`
- `list_files(ref)` (if provider supports browse)
- `delete(ref)` (optional)
- `healthcheck()`

Standard response:
- `ok`, `provider_id`, `checksum`, `size_bytes`, `metadata`.

## 4) Providers
### 4.1 TelegramAdapter
- Source: incoming file id/message id.
- Destination: send document/media to chat/user/channel.
- Constraints: bot API limits and retry on temporary failures.

### 4.2 RubikaAdapter
- Uses user session mapping.
- Support chunked/large file upload with retries.
- Must emit per-part status events.

### 4.3 BaleAdapter
- Token-based bot send path.
- Respect platform size constraints.
- Optional user mapping/allowlist from reference pattern.

### 4.4 GoogleDriveAdapter
- OAuth2 per user.
- Upload/download with resumable sessions.
- Folder target support and duplicate-name strategy.

### 4.5 LinkAdapter
- `Link -> file`: secure downloader with MIME/type checks and max size checks.
- `File -> link`: upload to managed object store with signed URL expiration.

## 5) Processing Pipeline
1. Validate quota and entitlement.
2. Resolve source.
3. Download to isolated temp workspace.
4. Optional transforms:
   - unzip
   - zip(password)
   - split
5. Upload to destination.
6. Persist result metadata + billing usage.
7. Cleanup temp files.

## 6) unzip Contract
- Input:
  - archive file, optional password.
- Output:
  - extracted files list and total size.
- Policies:
  - max extracted files count.
  - max expanded size (zip bomb prevention).
  - blocked extension policy (configurable).

## 7) Retry and Failure Policy
- Retry only on transient errors (network/timeout/5xx).
- No retry on invalid credentials/quota violations.
- Dead-letter after max attempts with actionable error reason.

## 8) Security and Compliance
- Temporary files isolated per task directory.
- Auto-delete temp workspace after completion/failure.
- Download allowlist/denylist for URL schemes and hosts.
- Virus scan hook point (optional in enterprise tier).

## 9) Milestone Delivery
- M1: Telegram<->Rubika refactor on adapter interface.
- M2: Bale and Drive adapters.
- M3: Link adapter + signed URL storage.
- M4: Full unzip pipeline + safety controls.
