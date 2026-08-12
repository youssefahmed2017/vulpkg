"""GitHub API integration for Vulp."""
import os
import json
import urllib.request
import urllib.error
from typing import Optional, List, Dict

from .config import GITHUB_API


class GitHubAPI:
    def __init__(self, token: Optional[str] = None):
        self.token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")

    def _headers(self) -> Dict[str, str]:
        h = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "vulp/0.1.0",
        }
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def _request(self, endpoint: str, method="GET", data=None, headers=None) -> dict:
        url = f"{GITHUB_API}{endpoint}"
        req_headers = self._headers()
        if headers:
            req_headers.update(headers)

        req = urllib.request.Request(url, method=method, headers=req_headers)
        if data:
            req.data = json.dumps(data).encode("utf-8")
            req_headers["Content-Type"] = "application/json"
            req = urllib.request.Request(url, data=req.data, method=method, headers=req_headers)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8")
            try:
                err = json.loads(body)
                msg = err.get("message", body)
            except:
                msg = body or str(e)
            raise GitHubError(f"GitHub API error: {msg} (HTTP {e.code})")

    def get_repo(self, owner: str, repo: str) -> dict:
        return self._request(f"/repos/{owner}/{repo}")

    def list_releases(self, owner: str, repo: str, per_page: int = 100) -> List[dict]:
        return self._request(f"/repos/{owner}/{repo}/releases?per_page={per_page}")

    def get_release_by_tag(self, owner: str, repo: str, tag: str) -> dict:
        return self._request(f"/repos/{owner}/{repo}/releases/tags/{tag}")

    def create_release(self, owner: str, repo: str, tag: str, name: str, body: str = "", draft=False, prerelease=False) -> dict:
        data = {
            "tag_name": tag,
            "name": name or tag,
            "body": body,
            "draft": draft,
            "prerelease": prerelease,
        }
        return self._request(f"/repos/{owner}/{repo}/releases", method="POST", data=data)

    def upload_release_asset(self, owner: str, repo: str, release_id: int, filename: str, data: bytes, content_type="application/octet-stream") -> dict:
        url = f"https://uploads.github.com/repos/{owner}/{repo}/releases/{release_id}/assets?name={filename}"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": content_type,
        }
        req = urllib.request.Request(url, data=data, method="POST", headers=headers)
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def get_latest_release(self, owner: str, repo: str) -> dict:
        return self._request(f"/repos/{owner}/{repo}/releases/latest")

    def get_rate_limit(self) -> dict:
        return self._request("/rate_limit")


class GitHubError(Exception):
    pass
