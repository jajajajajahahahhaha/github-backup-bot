"""
کلاینت گیت‌هاب: لیست ریپوها، کامیت‌ها، diff، دانلود ZIP
"""
import requests
import time
from typing import Optional


class GitHubClient:
    API = "https://api.github.com"

    def __init__(self, token: str, username: str = None):
        self.token = token
        self.username = username
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "gh-backup-bot/1.0",
        })

    def _get(self, url, params=None, stream=False, retries=3):
        for attempt in range(retries):
            try:
                r = self.session.get(url, params=params, stream=stream, timeout=60)
                if r.status_code == 403 and "rate limit" in r.text.lower():
                    reset = int(r.headers.get("X-RateLimit-Reset", time.time() + 60))
                    wait = max(5, reset - int(time.time()))
                    print(f"[github] rate limited, sleeping {wait}s")
                    time.sleep(min(wait, 120))
                    continue
                return r
            except requests.RequestException as e:
                print(f"[github] request error {e}, retry {attempt+1}")
                time.sleep(2 ** attempt)
        return None

    def whoami(self) -> Optional[dict]:
        r = self._get(f"{self.API}/user")
        if r and r.status_code == 200:
            return r.json()
        return None

    def list_all_repos(self):
        """لیست همه ریپوها (پابلیک + پرایوت) - صفحه‌بندی شده"""
        repos = []
        page = 1
        while True:
            r = self._get(f"{self.API}/user/repos", params={
                "per_page": 100,
                "page": page,
                "affiliation": "owner",
                "sort": "pushed",
                "direction": "desc",
            })
            if not r or r.status_code != 200:
                break
            batch = r.json()
            if not batch:
                break
            repos.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return repos

    def list_public_repos_of(self, username: str):
        """لیست ریپوهای پابلیک یک اکانت دیگه"""
        repos = []
        page = 1
        while True:
            r = self._get(f"{self.API}/users/{username}/repos", params={
                "per_page": 100,
                "page": page,
                "sort": "pushed",
                "direction": "desc",
            })
            if not r or r.status_code != 200:
                break
            batch = r.json()
            if not batch:
                break
            repos.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return repos

    def list_commits_since(self, owner_repo: str, since_sha: str = None, branch: str = None, limit: int = 30):
        """کامیت‌های جدید از یک sha به بعد رو میگیره"""
        params = {"per_page": limit}
        if branch:
            params["sha"] = branch
        r = self._get(f"{self.API}/repos/{owner_repo}/commits", params=params)
        if not r or r.status_code != 200:
            return []
        commits = r.json()
        if since_sha:
            filtered = []
            for c in commits:
                if c["sha"] == since_sha:
                    break
                filtered.append(c)
            return filtered
        return commits

    def get_commit_detail(self, owner_repo: str, sha: str):
        """جزییات یک کامیت شامل diff فایل‌ها"""
        r = self._get(f"{self.API}/repos/{owner_repo}/commits/{sha}")
        if not r or r.status_code != 200:
            return None
        return r.json()

    def download_zip(self, owner_repo: str, ref: str, out_path: str) -> bool:
        """دانلود ZIP یک ریپو"""
        url = f"{self.API}/repos/{owner_repo}/zipball/{ref}"
        r = self._get(url, stream=True)
        if not r or r.status_code != 200:
            print(f"[github] zip download failed for {owner_repo}: {r.status_code if r else 'no response'}")
            return False
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 128):
                if chunk:
                    f.write(chunk)
        return True
