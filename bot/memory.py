"""
مدیریت حافظه بات
فایل memory.json روی ریپوی گیت‌هاب ذخیره میشه و در پایان هر اجرا آپدیت میشه
"""
import json
import os
import base64
import time
from datetime import datetime, timezone
import requests
from . import config


class Memory:
    """
    ساختار memory.json:
    {
        "started_at": "iso timestamp",
        "last_run": "iso timestamp",
        "accounts": {
            "username": {
                "token_hint": "ghp_...last4",
                "repos": {
                    "repo_id_or_name": {
                        "name": "current_name",
                        "previous_names": ["old1", "old2"],
                        "default_branch": "main",
                        "last_sha": "abc123",
                        "last_pushed_at": "iso",
                        "commits_seen": ["sha1", "sha2"],
                        "history": [
                            {
                                "type": "commit|rename|created",
                                "at": "iso",
                                "sha": "...",
                                "message": "...",
                                "files_changed": [{"filename":"...","status":"...","patch":"..."}],
                                "old_name": "...",
                                "new_name": "..."
                            }
                        ],
                        "backups": [
                            {"at": "iso", "message_id": 123, "sha": "..."}
                        ]
                    }
                }
            }
        },
        "pinned_message_id": null,
        "channel_snapshot_message_ids": []
    }
    """

    def __init__(self):
        self.data = {
            "started_at": None,
            "last_run": None,
            "accounts": {},
            "pinned_message_id": None,
            "channel_snapshot_message_ids": [],
        }
        self._sha = None  # sha of memory.json file on GitHub (for updating)
        self._local_path = os.path.join(config.WORK_DIR, "memory.json")

    # ---------- Local IO ----------
    def load_local(self):
        if os.path.exists(self._local_path):
            try:
                with open(self._local_path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                return True
            except Exception:
                pass
        return False

    def save_local(self):
        os.makedirs(os.path.dirname(self._local_path), exist_ok=True)
        with open(self._local_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        return self._local_path

    # ---------- GitHub sync ----------
    def load_from_github(self):
        """memory.json رو از ریپوی MEMORY_REPO میخونه"""
        if not config.MEMORY_REPO or not config.GITHUB_TOKEN:
            return False
        url = f"https://api.github.com/repos/{config.MEMORY_REPO}/contents/{config.MEMORY_FILE}"
        headers = {
            "Authorization": f"Bearer {config.GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        }
        try:
            r = requests.get(url, headers=headers, timeout=30)
            if r.status_code == 200:
                payload = r.json()
                self._sha = payload.get("sha")
                content = base64.b64decode(payload["content"]).decode("utf-8")
                self.data = json.loads(content)
                self.save_local()
                return True
            elif r.status_code == 404:
                # فایل وجود نداره، اولین اجراست
                return False
        except Exception as e:
            print(f"[memory] load_from_github error: {e}")
        return False

    def save_to_github(self, commit_message: str = None):
        """memory.json رو به ریپوی گیت‌هاب پوش می‌کنه"""
        if not config.MEMORY_REPO or not config.GITHUB_TOKEN:
            return False
        self.save_local()
        url = f"https://api.github.com/repos/{config.MEMORY_REPO}/contents/{config.MEMORY_FILE}"
        headers = {
            "Authorization": f"Bearer {config.GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        }
        content_str = json.dumps(self.data, ensure_ascii=False, indent=2)
        b64 = base64.b64encode(content_str.encode("utf-8")).decode("ascii")
        body = {
            "message": commit_message or f"chore(memory): update at {datetime.now(timezone.utc).isoformat()}",
            "content": b64,
            "branch": "main",
        }
        if self._sha:
            body["sha"] = self._sha
        try:
            r = requests.put(url, headers=headers, json=body, timeout=60)
            if r.status_code in (200, 201):
                self._sha = r.json()["content"]["sha"]
                return True
            else:
                print(f"[memory] save_to_github failed {r.status_code}: {r.text[:300]}")
        except Exception as e:
            print(f"[memory] save_to_github error: {e}")
        return False

    # ---------- Data helpers ----------
    def ensure_account(self, username: str, token: str):
        if username not in self.data["accounts"]:
            self.data["accounts"][username] = {
                "token_hint": (token[-4:] if token else ""),
                "repos": {},
            }
        return self.data["accounts"][username]

    def upsert_repo(self, username: str, repo_info: dict):
        acct = self.data["accounts"].setdefault(username, {"token_hint": "", "repos": {}})
        rid = str(repo_info["id"])
        existing = acct["repos"].get(rid)
        if not existing:
            acct["repos"][rid] = {
                "name": repo_info["name"],
                "full_name": repo_info["full_name"],
                "previous_names": [],
                "default_branch": repo_info.get("default_branch", "main"),
                "last_sha": None,
                "last_pushed_at": repo_info.get("pushed_at"),
                "private": repo_info.get("private", False),
                "commits_seen": [],
                "history": [{
                    "type": "created_tracking",
                    "at": datetime.now(timezone.utc).isoformat(),
                    "name": repo_info["name"],
                }],
                "backups": [],
            }
        else:
            # detect rename
            if existing["name"] != repo_info["name"]:
                existing.setdefault("previous_names", []).append(existing["name"])
                existing["history"].append({
                    "type": "rename",
                    "at": datetime.now(timezone.utc).isoformat(),
                    "old_name": existing["name"],
                    "new_name": repo_info["name"],
                })
                existing["name"] = repo_info["name"]
                existing["full_name"] = repo_info["full_name"]
            existing["default_branch"] = repo_info.get("default_branch", existing.get("default_branch", "main"))
            existing["private"] = repo_info.get("private", existing.get("private", False))
        return acct["repos"][rid]

    def add_commit(self, username: str, repo_id: str, commit: dict, files: list):
        rec = self.data["accounts"][username]["repos"][repo_id]
        if commit["sha"] in rec.get("commits_seen", []):
            return False
        rec.setdefault("commits_seen", []).append(commit["sha"])
        rec["last_sha"] = commit["sha"]
        rec["history"].append({
            "type": "commit",
            "at": commit.get("date") or datetime.now(timezone.utc).isoformat(),
            "sha": commit["sha"],
            "message": commit.get("message", ""),
            "author": commit.get("author", ""),
            "files_changed": files,
        })
        return True

    def add_backup(self, username: str, repo_id: str, message_id: int, sha: str):
        rec = self.data["accounts"][username]["repos"][repo_id]
        rec.setdefault("backups", []).append({
            "at": datetime.now(timezone.utc).isoformat(),
            "message_id": message_id,
            "sha": sha,
        })

    def touch(self):
        now = datetime.now(timezone.utc).isoformat()
        if not self.data.get("started_at"):
            self.data["started_at"] = now
        self.data["last_run"] = now
