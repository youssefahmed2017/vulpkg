"""Dependency resolution for Vulp."""
import re
from typing import Dict, List, Tuple, Optional
from packaging.version import Version, InvalidVersion

from .db import IndexDB
from .github import GitHubAPI


class Resolver:
    """Resolves package names to owner/repo and versions."""

    def __init__(self, db: IndexDB, github: GitHubAPI):
        self.db = db
        self.github = github

    def parse_spec(self, spec: str) -> Tuple[str, str, str]:
        """Parse a package spec into (owner, repo, version_constraint).

        Supports:
            - "owner/repo"          -> latest
            - "owner/repo@1.0.0"    -> exact
            - "owner/repo@^1.0.0"   -> compatible
            - "owner/repo@>=1.0.0"  -> range
            - "repo"                -> if DEFAULT_REGISTRY_OWNER set, else error
        """
        version = "latest"
        if "@" in spec:
            name_part, version = spec.rsplit("@", 1)
        else:
            name_part = spec

        if "/" in name_part:
            owner, repo = name_part.split("/", 1)
        else:
            # Try to resolve from local index first
            pkg = self.db.get_package(name_part)
            if pkg:
                owner, repo = pkg["owner"], pkg["name"]
            else:
                from .config import DEFAULT_REGISTRY_OWNER
                if DEFAULT_REGISTRY_OWNER:
                    owner, repo = DEFAULT_REGISTRY_OWNER, name_part
                else:
                    raise ValueError(f"Cannot resolve '{spec}': use 'owner/repo' format or set DEFAULT_REGISTRY_OWNER")

        return owner.strip(), repo.strip(), version.strip()

    def resolve_version(self, owner: str, repo: str, constraint: str) -> str:
        """Resolve a version constraint to an actual tag."""
        if constraint == "latest":
            # Check local index first
            pkg = self.db.get_package(f"{owner}/{repo}")
            if pkg and pkg["latest_tag"]:
                return pkg["latest_tag"]
            # Fetch from GitHub
            try:
                release = self.github.get_latest_release(owner, repo)
                return release["tag_name"]
            except Exception:
                # Fall back to listing releases
                releases = self.github.list_releases(owner, repo)
                if not releases:
                    raise ValueError(f"No releases found for {owner}/{repo}")
                return releases[0]["tag_name"]

        # Exact version
        if constraint.startswith("^") or constraint.startswith(">=") or constraint.startswith(">") or constraint.startswith("<") or constraint.startswith("<=") or constraint.startswith("~"):
            return self._resolve_range(owner, repo, constraint)

        # Assume exact tag
        return constraint

    def _resolve_range(self, owner: str, repo: str, constraint: str) -> str:
        releases = self.github.list_releases(owner, repo)
        if not releases:
            raise ValueError(f"No releases found for {owner}/{repo}")

        tags = [r["tag_name"] for r in releases]
        valid = []
        for tag in tags:
            try:
                v = self._to_version(tag)
                valid.append((tag, v))
            except InvalidVersion:
                continue

        if not valid:
            raise ValueError(f"No valid semver releases found for {owner}/{repo}")

        req = self._parse_constraint(constraint)
        candidates = [(t, v) for t, v in valid if req(v)]
        if not candidates:
            raise ValueError(f"No release satisfies '{constraint}' for {owner}/{repo}")

        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    def _to_version(self, tag: str) -> Version:
        # Strip leading 'v' or 'V'
        clean = tag
        if clean.lower().startswith("v"):
            clean = clean[1:]
        return Version(clean)

    def _parse_constraint(self, constraint: str):
        """Return a predicate function for version matching."""
        if constraint.startswith("^"):
            base = self._to_version(constraint[1:])
            major = base.major
            return lambda v: v >= base and v.major == major
        elif constraint.startswith("~="):
            base = self._to_version(constraint[2:])
            return lambda v: v >= base and v.release[:2] == base.release[:2]
        elif constraint.startswith(">="):
            base = self._to_version(constraint[2:])
            return lambda v: v >= base
        elif constraint.startswith(">"):
            base = self._to_version(constraint[1:])
            return lambda v: v > base
        elif constraint.startswith("<="):
            base = self._to_version(constraint[2:])
            return lambda v: v <= base
        elif constraint.startswith("<"):
            base = self._to_version(constraint[1:])
            return lambda v: v < base
        else:
            base = self._to_version(constraint)
            return lambda v: v == base
