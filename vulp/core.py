"""Core Vulp logic."""
import os
import sys
import json
import shutil
import hashlib
import urllib.request
import zipfile
import io
import subprocess
from pathlib import Path

from .config import (
    CONFIG_FILE, LOCK_FILE, DEPS_DIR, CACHE_DIR,
    ensure_dirs, GITHUB_RAW
)
from .db import IndexDB
from .github import GitHubAPI, GitHubError
from .resolver import Resolver


def _load_toml(path):
    """Minimal TOML parser — enough for vulpin.toml."""
    import tomllib
    with open(path, "rb") as f:
        return tomllib.load(f)


def _save_toml(path, data):
    import tomli_w
    with open(path, "wb") as f:
        tomli_w.dump(data, f)


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


class VulpCore:
    def __init__(self):
        ensure_dirs()
        self.db = IndexDB()
        self.github = GitHubAPI()
        self.resolver = Resolver(self.db, self.github)

    # --- Project init ---

    def init(self, name=None):
        if os.path.exists(CONFIG_FILE):
            print(f"[!] {CONFIG_FILE} already exists.")
            return

        pkg_name = name or os.path.basename(os.getcwd())
        config = {
            "package": {
                "name": pkg_name,
                "version": "0.1.0",
                "description": "",
                "author": "",
                "license": "MIT",
            },
            "deps": {},
        }
        _save_toml(CONFIG_FILE, config)
        print(f"[+] Created {CONFIG_FILE} for package '{pkg_name}'")

    # --- Dependencies ---

    def add(self, spec: str, version: str = "latest"):
        if not os.path.exists(CONFIG_FILE):
            print(f"[!] No {CONFIG_FILE} found. Run 'vulp init' first.")
            return

        config = _load_toml(CONFIG_FILE)
        owner, repo, _ = self.resolver.parse_spec(spec)
        full_name = f"{owner}/{repo}"

        # Resolve version
        tag = self.resolver.resolve_version(owner, repo, version)

        # Update vulpin.toml
        deps = config.get("deps", {})
        deps[full_name] = tag
        config["deps"] = deps
        _save_toml(CONFIG_FILE, config)
        print(f"[+] Added {full_name}@{tag} to {CONFIG_FILE}")

        # Install immediately
        self._fetch_and_install(owner, repo, tag)

    def remove(self, spec: str):
        if not os.path.exists(CONFIG_FILE):
            print(f"[!] No {CONFIG_FILE} found.")
            return

        config = _load_toml(CONFIG_FILE)
        deps = config.get("deps", {})

        # Try exact match first, then resolve
        if spec in deps:
            full_name = spec
        else:
            owner, repo, _ = self.resolver.parse_spec(spec)
            full_name = f"{owner}/{repo}"

        if full_name not in deps:
            print(f"[!] {full_name} is not a dependency.")
            return

        del deps[full_name]
        config["deps"] = deps
        _save_toml(CONFIG_FILE, config)

        # Remove from vulp_modules
        mod_path = os.path.join(DEPS_DIR, full_name.replace("/", "_"))
        if os.path.exists(mod_path):
            shutil.rmtree(mod_path)

        print(f"[+] Removed {full_name}")

    def install(self, skip_cache=False):
        if not os.path.exists(CONFIG_FILE):
            print(f"[!] No {CONFIG_FILE} found.")
            return

        config = _load_toml(CONFIG_FILE)
        deps = config.get("deps", {})

        if not deps:
            print("[*] No dependencies to install.")
            return

        lock = {"version": 1, "packages": {}}
        os.makedirs(DEPS_DIR, exist_ok=True)

        for full_name, constraint in deps.items():
            owner, repo = full_name.split("/", 1)
            tag = self.resolver.resolve_version(owner, repo, constraint)
            lock["packages"][full_name] = tag
            self._fetch_and_install(owner, repo, tag, skip_cache=skip_cache)

        with open(LOCK_FILE, "w") as f:
            json.dump(lock, f, indent=2)
        print(f"[+] Installed {len(deps)} package(s). Lockfile: {LOCK_FILE}")

    def _fetch_and_install(self, owner: str, repo: str, tag: str, skip_cache=False):
        full_name = f"{owner}/{repo}"
        mod_path = os.path.join(DEPS_DIR, full_name.replace("/", "_"))

        # Check local cache
        if not skip_cache:
            cached = self.db.get_cache(full_name, tag)
            if cached and os.path.exists(cached["local_path"]):
                if os.path.exists(mod_path):
                    shutil.rmtree(mod_path)
                shutil.copytree(cached["local_path"], mod_path)
                print(f"  [cache] {full_name}@{tag}")
                return

        # Download from GitHub release
        release = self.github.get_release_by_tag(owner, repo, tag)
        assets = release.get("assets", [])

        # Look for a .zip or .tar.gz asset, or fall back to source zipball
        vulpin_asset = None
        for asset in assets:
            if asset["name"].endswith(".vul") or asset["name"].endswith(".zip") or asset["name"].endswith(".tar.gz"):
                vulpin_asset = asset
                break

        if vulpin_asset:
            url = vulpin_asset["browser_download_url"]
            data = self._download(url)
            if vulpin_asset["name"].endswith(".zip"):
                self._extract_zip(data, mod_path)
            elif vulpin_asset["name"].endswith(".tar.gz"):
                self._extract_tgz(data, mod_path)
            else:
                os.makedirs(mod_path, exist_ok=True)
                with open(os.path.join(mod_path, vulpin_asset["name"]), "wb") as f:
                    f.write(data)
        else:
            # Download source zipball
            url = release.get("zipball_url")
            if not url:
                raise ValueError(f"No downloadable assets for {full_name}@{tag}")
            data = self._download(url)
            self._extract_zip(data, mod_path)

        # Cache it
        cache_path = os.path.join(CACHE_DIR, f"{owner}_{repo}_{tag}")
        if os.path.exists(cache_path):
            shutil.rmtree(cache_path)
        shutil.copytree(mod_path, cache_path)
        size = sum(os.path.getsize(os.path.join(dp, f)) for dp, dn, filenames in os.walk(cache_path) for f in filenames)
        self.db.add_cache(full_name, tag, cache_path, size_bytes=size)

        # Update local index
        self._index_package(owner, repo, release)

        print(f"  [+] {full_name}@{tag}")

    def _download(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={
            "User-Agent": "vulp/0.1.0",
            "Accept": "application/octet-stream",
        })
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read()

    def _extract_zip(self, data: bytes, dest: str):
        os.makedirs(dest, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            # GitHub zipballs have a root folder like "owner-repo-tag/"
            root = None
            for name in zf.namelist():
                parts = name.split("/")
                if len(parts) > 1:
                    root = parts[0]
                    break
            for member in zf.namelist():
                if root and member.startswith(root + "/"):
                    target = member[len(root) + 1:]
                else:
                    target = member
                if not target:
                    continue
                target_path = os.path.join(dest, target)
                if member.endswith("/"):
                    os.makedirs(target_path, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    with zf.open(member) as src, open(target_path, "wb") as dst:
                        dst.write(src.read())

    def _extract_tgz(self, data: bytes, dest: str):
        import tarfile
        os.makedirs(dest, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
            root = None
            for member in tf.getmembers():
                parts = member.name.split("/")
                if len(parts) > 1:
                    root = parts[0]
                    break
            for member in tf.getmembers():
                if root and member.name.startswith(root + "/"):
                    target = member.name[len(root) + 1:]
                else:
                    target = member.name
                if not target:
                    continue
                target_path = os.path.join(dest, target)
                if member.isdir():
                    os.makedirs(target_path, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(target_path), exist_ok=True)
                    with tf.extractfile(member) as src, open(target_path, "wb") as dst:
                        dst.write(src.read())

    def _index_package(self, owner: str, repo: str, release: dict):
        full_name = f"{owner}/{repo}"
        try:
            repo_info = self.github.get_repo(owner, repo)
        except GitHubError:
            repo_info = {}

        pkg_id = self.db.upsert_package(
            full_name=full_name,
            name=repo,
            owner=owner,
            description=repo_info.get("description", ""),
            latest_tag=release.get("tag_name"),
            stars=repo_info.get("stargazers_count", 0),
            updated_at=repo_info.get("updated_at"),
        )

        self.db.upsert_version(
            pkg_id=pkg_id,
            tag=release["tag_name"],
            tarball_url=release.get("tarball_url"),
            zipball_url=release.get("zipball_url"),
            published_at=release.get("published_at"),
            size_bytes=release.get("assets", [{}])[0].get("size") if release.get("assets") else None,
        )

    def list_deps(self):
        if not os.path.exists(CONFIG_FILE):
            print(f"[!] No {CONFIG_FILE} found.")
            return
        config = _load_toml(CONFIG_FILE)
        deps = config.get("deps", {})
        if not deps:
            print("[*] No dependencies.")
            return
        print(f"{'Package':<30} {'Version':<15}")
        print("-" * 45)
        for name, ver in deps.items():
            print(f"{name:<30} {ver:<15}")

    # --- Search & Index ---

    def search(self, query: str):
        results = self.db.search_packages(query)
        if not results:
            print(f"[*] No packages found for '{query}'")
            return
        print(f"{'Package':<30} {'Latest':<12} {'Stars':<8} Description")
        print("-" * 80)
        for pkg in results:
            desc = (pkg["description"] or "")[:35]
            print(f"{pkg['full_name']:<30} {pkg['latest_tag'] or 'unknown':<12} {pkg['stars']:<8} {desc}")

    def update_index(self):
        """Update local index from known packages in vulpin.toml files and GitHub."""
        print("[*] Updating package index...")
        # This is a placeholder — in practice you'd scan a known list or
        # have a central registry repo that lists all packages.
        # For now, we just re-index installed packages.
        if os.path.exists(CONFIG_FILE):
            config = _load_toml(CONFIG_FILE)
            for full_name in config.get("deps", {}):
                owner, repo = full_name.split("/", 1)
                try:
                    release = self.github.get_latest_release(owner, repo)
                    self._index_package(owner, repo, release)
                except Exception as e:
                    print(f"  [!] Failed to index {full_name}: {e}")
        print("[+] Index updated.")

    # --- Publish ---

    def publish(self, tag: str, token: str = None):
        if not os.path.exists(CONFIG_FILE):
            print(f"[!] No {CONFIG_FILE} found.")
            return

        config = _load_toml(CONFIG_FILE)
        pkg = config.get("package", {})
        name = pkg.get("name", os.path.basename(os.getcwd()))

        # Detect git remote to get owner/repo
        owner, repo = self._detect_git_remote()
        if not owner or not repo:
            print("[!] Could not detect GitHub remote. Make sure you're in a git repo with a GitHub origin.")
            return

        gh = GitHubAPI(token)

        # Create or get release
        try:
            release = gh.get_release_by_tag(owner, repo, tag)
            print(f"[*] Release {tag} already exists.")
        except GitHubError:
            release = gh.create_release(
                owner, repo, tag,
                name=f"{name} {tag}",
                body=pkg.get("description", ""),
            )
            print(f"[+] Created release {tag}")

        # Find .vul files to upload
        vul_files = list(Path(".").glob("*.vul"))
        if not vul_files:
            print("[!] No .vul files found to publish.")
            return

        # Also package the whole project as a zip
        zip_name = f"{repo}-{tag}.zip"
        import zipfile
        with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in Path(".").rglob("*"):
                if ".git" in str(path) or str(path).startswith("vulp_modules") or str(path).startswith("__pycache__"):
                    continue
                if path.is_file():
                    zf.write(path, path)

        with open(zip_name, "rb") as f:
            data = f.read()
        gh.upload_release_asset(owner, repo, release["id"], zip_name, data, "application/zip")
        print(f"[+] Uploaded {zip_name}")
        os.remove(zip_name)

        # Upload individual .vul files
        for vf in vul_files:
            with open(vf, "rb") as f:
                data = f.read()
            gh.upload_release_asset(owner, repo, release["id"], vf.name, data, "text/plain")
            print(f"[+] Uploaded {vf.name}")

        # Update local index
        self._index_package(owner, repo, release)
        print(f"[+] Published {owner}/{repo}@{tag}")

    def _detect_git_remote(self) -> tuple:
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True, text=True, check=True
            )
            url = result.stdout.strip()
            # Parse github.com/owner/repo or git@github.com:owner/repo
            if "github.com" in url:
                if url.startswith("git@github.com:"):
                    path = url.replace("git@github.com:", "").replace(".git", "")
                else:
                    path = url.split("github.com/")[-1].replace(".git", "")
                parts = path.split("/")
                if len(parts) >= 2:
                    return parts[0], parts[1]
        except Exception:
            pass
        return None, None

    # --- Run ---

    def run(self, file: str):
        """Run a Vulpin file with dependencies in the module path."""
        if not os.path.exists(file):
            print(f"[!] File not found: {file}")
            return

        # Ensure deps are installed
        if os.path.exists(CONFIG_FILE):
            config = _load_toml(CONFIG_FILE)
            if config.get("deps"):
                self.install()

        # Build module path for Vulpin runtime
        env = os.environ.copy()
        module_paths = [DEPS_DIR]
        if "VULPIN_PATH" in env:
            module_paths = env["VULPIN_PATH"].split(os.pathsep) + module_paths
        env["VULPIN_PATH"] = os.pathsep.join(module_paths)

        # Prepend dependency injections to the file
        injected = self._build_injection_preamble()

        with open(file, "r") as f:
            source = f.read()

        tmp_file = f"._vulp_{os.path.basename(file)}"
        with open(tmp_file, "w") as f:
            f.write(injected)
            f.write(source)

        # Try multiple ways to invoke vulpin
        vulpin_cmd = self._find_vulpin()
        if not vulpin_cmd:
            print("[!] Vulpin interpreter not found.")
            print("    Try: python -m vulpin --version")
            print("    Or:  python /path/to/vulpin/src/vulpin.py --version")
            if os.path.exists(tmp_file):
                os.remove(tmp_file)
            return

        try:
            subprocess.run(vulpin_cmd + [tmp_file], env=env)
        except Exception as e:
            print(f"[!] Failed to run vulpin: {e}")
        finally:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)

    def _find_vulpin(self):
        """Find the vulpin interpreter. Returns a list suitable for subprocess."""
        # 1. Try './vulpin' in current directory
        local_vulpin = os.path.join(os.getcwd(), "vulpin")
        if os.path.exists(local_vulpin) and os.access(local_vulpin, os.X_OK):
            return [local_vulpin]

        # 2. Try 'vulpin' command in PATH
        if shutil.which("vulpin"):
            return ["vulpin"]

        # 3. Try 'python -m vulpin'
        try:
            result = subprocess.run(
                [sys.executable, "-m", "vulpin", "version"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return [sys.executable, "-m", "vulpin"]
        except Exception:
            pass

        # 4. Try common paths for vulpin.py
        candidates = [
            os.path.expanduser("~/vulpin/src/vulpin.py"),
            os.path.expanduser("~/vulpin/vulpin.py"),
            "/usr/local/lib/python*/site-packages/vulpin/vulpin.py",
            os.path.join(sys.prefix, "lib", f"python{sys.version_info.major}.{sys.version_info.minor}", "site-packages", "vulpin", "vulpin.py"),
        ]
        import glob
        for c in candidates:
            for path in glob.glob(c) if "*" in c else [c]:
                if os.path.exists(path):
                    return [sys.executable, path]

        return None

    def _build_injection_preamble(self) -> str:
        """Build a preamble that injects all dependency modules."""
        lines = []
        if not os.path.exists(DEPS_DIR):
            return ""

        for entry in os.listdir(DEPS_DIR):
            mod_path = os.path.join(DEPS_DIR, entry)
            if not os.path.isdir(mod_path):
                continue

            # Find all .vul files in the module
            for root, _, files in os.walk(mod_path):
                for f in files:
                    if f.endswith(".vul"):
                        rel = os.path.relpath(os.path.join(root, f), ".")
                        # Vulpin comment-style injection directive
                        lines.append(f'#vulp: module "{rel}"')

        return "\n".join(lines) + "\n\n" if lines else ""

    # --- Cache management ---

    def cache_clear(self):
        if os.path.exists(CACHE_DIR):
            shutil.rmtree(CACHE_DIR)
            os.makedirs(CACHE_DIR, exist_ok=True)
        self.db.clear_cache()
        print("[+] Cache cleared.")

    def cache_list(self):
        entries = self.db.list_cache()
        if not entries:
            print("[*] Cache is empty.")
            return
        print(f"{'Package':<35} {'Tag':<12} {'Size':<10} {'Downloaded'}")
        print("-" * 75)
        for e in entries:
            size = e.get("size_bytes") or "?"
            if isinstance(size, int):
                size = f"{size / 1024:.1f} KB"
            print(f"{e['full_name']:<35} {e['tag']:<12} {size:<10} {e['downloaded_at'] or '?'}")
