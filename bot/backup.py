"""
منطق بک‌آپ گیری از ریپوها + سنجیدن تغییرات + آپلود روی کانال
"""
import os
import time
from datetime import datetime, timezone
from . import config, telegram_client
from .github_client import GitHubClient


def human_time(iso_str: str) -> str:
    if not iso_str:
        return "-"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return iso_str


def build_changelog(repo_rec: dict, new_commits: list) -> str:
    """ساخت فایل متنی خلاصه تغییرات"""
    lines = []
    lines.append(f"Repository: {repo_rec['full_name']}")
    lines.append(f"Default branch: {repo_rec.get('default_branch','main')}")
    lines.append(f"Generated at: {datetime.now(timezone.utc).isoformat()}")
    lines.append("=" * 60)
    lines.append("")

    if repo_rec.get("previous_names"):
        lines.append("Previous names: " + ", ".join(repo_rec["previous_names"]))
        lines.append("")

    lines.append(f"New commits in this run: {len(new_commits)}")
    lines.append("-" * 60)
    for c in new_commits:
        lines.append(f"\n[{c.get('date','?')}] {c['sha'][:8]}  by {c.get('author','?')}")
        lines.append(f"  {c.get('message','').splitlines()[0] if c.get('message') else ''}")
        for f in c.get("files_changed", []):
            lines.append(f"    - {f.get('status','?'):8s} {f.get('filename','?')} (+{f.get('additions',0)}/-{f.get('deletions',0)})")

    lines.append("")
    lines.append("=" * 60)
    lines.append("Full history since bot activation:")
    lines.append("-" * 60)
    for h in repo_rec.get("history", [])[-200:]:
        if h["type"] == "commit":
            lines.append(f"[{h.get('at','?')}] commit {h['sha'][:8]} — {h.get('message','').splitlines()[0] if h.get('message') else ''}")
        elif h["type"] == "rename":
            lines.append(f"[{h.get('at','?')}] renamed: {h.get('old_name')} → {h.get('new_name')}")
        elif h["type"] == "created_tracking":
            lines.append(f"[{h.get('at','?')}] tracking started: {h.get('name')}")

    return "\n".join(lines)


def build_diff_text(new_commits: list, max_bytes: int = 3_500_000) -> str:
    """diff کامل همه فایل‌های تغییر یافته"""
    out = []
    size = 0
    for c in new_commits:
        header = f"\n{'='*70}\nCommit: {c['sha']}\nAuthor: {c.get('author','?')}\nDate: {c.get('date','?')}\nMessage: {c.get('message','')}\n{'='*70}\n"
        out.append(header)
        size += len(header)
        for f in c.get("files_changed", []):
            fh = f"\n--- {f.get('filename')} ({f.get('status')}) +{f.get('additions',0)}/-{f.get('deletions',0)}\n"
            out.append(fh)
            size += len(fh)
            patch = f.get("patch") or "(binary or no patch)"
            if size + len(patch) > max_bytes:
                out.append("\n[... truncated ...]\n")
                return "".join(out)
            out.append(patch + "\n")
            size += len(patch)
    return "".join(out)


def check_repo_changes(gh: GitHubClient, username: str, repo_info: dict, mem, first_seen: bool):
    """
    بررسی یک ریپو برای کامیت‌های جدید.
    اگه کامیت جدید داشت → بک‌آپ ZIP + changelog + diff رو آپلود کانال میکنه.
    """
    repo_rec = mem.upsert_repo(username, repo_info)
    owner_repo = repo_info["full_name"]
    branch = repo_info.get("default_branch") or "main"

    since_sha = repo_rec.get("last_sha")
    commits = gh.list_commits_since(owner_repo, since_sha=since_sha, branch=branch, limit=30)

    if not commits:
        return False  # no change

    # جمع‌آوری دیتیل هر کامیت (شامل diff)
    detailed = []
    for c in reversed(commits):  # از قدیم به جدید
        detail = gh.get_commit_detail(owner_repo, c["sha"])
        if not detail:
            continue
        files = []
        for f in detail.get("files", []) or []:
            files.append({
                "filename": f.get("filename"),
                "status": f.get("status"),
                "additions": f.get("additions", 0),
                "deletions": f.get("deletions", 0),
                "patch": f.get("patch"),
            })
        cd = {
            "sha": detail["sha"],
            "message": (detail.get("commit", {}).get("message") or "").strip(),
            "author": (detail.get("commit", {}).get("author", {}) or {}).get("name", "?"),
            "date": (detail.get("commit", {}).get("author", {}) or {}).get("date"),
            "files_changed": files,
        }
        detailed.append(cd)
        mem.add_commit(username, str(repo_info["id"]), cd, files)

    if not detailed:
        return False

    # آپلود روی کانال
    from tempfile import NamedTemporaryFile
    import zipfile

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    safe_name = repo_info["name"].replace("/", "_")

    # ZIP دانلود
    zip_path = os.path.join(config.WORK_DIR, f"{safe_name}-{ts}.zip")
    ok = gh.download_zip(owner_repo, branch, zip_path)

    caption_parts = [
        f"📦 <b>{repo_info['full_name']}</b>",
        f"🌿 branch: <code>{branch}</code>",
        f"🔒 private: {repo_info.get('private', False)}",
        f"🕒 backup at: {ts}",
        f"✨ new commits: {len(detailed)}",
    ]
    if repo_rec.get("previous_names"):
        caption_parts.append(f"↪️ previous names: {', '.join(repo_rec['previous_names'])}")

    latest = detailed[-1]
    caption_parts.append(f"\n<b>latest commit</b>:")
    caption_parts.append(f"  <code>{latest['sha'][:8]}</code> — {latest['message'].splitlines()[0][:120] if latest['message'] else ''}")

    caption = "\n".join(caption_parts)

    zip_msg_id = None
    if ok and os.path.exists(zip_path):
        size = os.path.getsize(zip_path)
        if size <= config.MAX_UPLOAD_SIZE:
            try:
                zip_msg_id = telegram_client.send_channel_document(zip_path, caption=caption)
            except Exception as e:
                print(f"[backup] upload zip failed: {e}")
                telegram_client.send_channel_text(caption + f"\n\n⚠️ zip upload failed: {e}")
        else:
            telegram_client.send_channel_text(caption + f"\n\n⚠️ zip too big ({size//1024//1024}MB), skipping upload.")
        try:
            os.remove(zip_path)
        except Exception:
            pass

    # changelog
    changelog_path = os.path.join(config.WORK_DIR, f"{safe_name}-{ts}.changelog.txt")
    with open(changelog_path, "w", encoding="utf-8") as f:
        f.write(build_changelog(repo_rec, detailed))
    try:
        telegram_client.send_channel_document(changelog_path, caption=f"📝 changelog for {repo_info['full_name']}")
    except Exception as e:
        print(f"[backup] upload changelog failed: {e}")
    os.remove(changelog_path)

    # diff full
    diff_text = build_diff_text(detailed)
    if diff_text.strip():
        diff_path = os.path.join(config.WORK_DIR, f"{safe_name}-{ts}.diff.txt")
        with open(diff_path, "w", encoding="utf-8") as f:
            f.write(diff_text)
        try:
            telegram_client.send_channel_document(diff_path, caption=f"🧬 full diff for {repo_info['full_name']}")
        except Exception as e:
            print(f"[backup] upload diff failed: {e}")
        os.remove(diff_path)

    if zip_msg_id:
        mem.add_backup(username, str(repo_info["id"]), zip_msg_id, latest["sha"])

    return True


def full_backup_account(gh: GitHubClient, username: str, mem):
    """
    بک‌آپ کامل از همه ریپوهای یک اکانت (برای دکمه‌ی «بک‌آپ اکانت جدید»)
    """
    repos = gh.list_all_repos() if username == config.GITHUB_USERNAME else gh.list_public_repos_of(username)
    telegram_client.send_owner(f"🏁 شروع بک‌آپ کامل اکانت <b>{username}</b> ({len(repos)} ریپو)")
    count = 0
    for repo in repos:
        try:
            changed = check_repo_changes(gh, username, repo, mem, first_seen=True)
            if changed:
                count += 1
            time.sleep(1)  # rate limit friendly
        except Exception as e:
            print(f"[backup] error on {repo.get('full_name')}: {e}")
    telegram_client.send_owner(f"✅ بک‌آپ کامل اکانت <b>{username}</b> تموم شد. {count} ریپو تغییر داشت/بک‌آپ شد.")
