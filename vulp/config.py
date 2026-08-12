"""Vulp configuration and constants."""
import os
import platform

VULP_DIR = os.path.expanduser("~/.vulp")
CACHE_DIR = os.path.join(VULP_DIR, "cache")
INDEX_DB = os.path.join(VULP_DIR, "index.db")
CONFIG_FILE = "vulpin.toml"
LOCK_FILE = "vulpin.lock"
DEPS_DIR = "vulp_modules"

GITHUB_API = "https://api.github.com"
GITHUB_RAW = "https://raw.githubusercontent.com"

DEFAULT_REGISTRY_OWNER = None  # If set, 'repo' resolves to 'owner/repo'


def ensure_dirs():
    os.makedirs(VULP_DIR, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)
