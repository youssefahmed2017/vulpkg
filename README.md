# vulpkg

Package manager for the [Vulpin](https://github.com/vulpin-lang/vulpin) programming language.

## Installation

```bash
pip install vulpkg
```

## Quick Start

```bash
# Initialize a new Vulpin package
vulpkg init --name my-package

# Add a dependency from GitHub Releases
vulpkg add stefand-0/string-utils
vulpkg add stefand-0/json@v1.0.0

# Install all dependencies
vulpkg install

# Run your Vulpin program with dependencies
vulpkg run main.vul

# Publish your package to GitHub Releases
vulpkg publish --tag v1.0.0
```

## Configuration: `vulpin.toml`

```toml
[package]
name = "my-package"
version = "1.0.0"
description = "A useful Vulpin library"
author = "Name"
license = "MIT"

[deps]
"xyz/string-utils" = "latest"
"xyz/json" = ">=0.5.0"
```

## Commands

| Command | Description |
|---------|-------------|
| `vulpkg init` | Create a new `vulpin.toml` |
| `vulpkg add <pkg>` | Add a dependency |
| `vulpkg install` | Install dependencies from `vulpin.toml` |
| `vulpkg remove <pkg>` | Remove a dependency |
| `vulpkg list` | List installed dependencies |
| `vulpkg search <query>` | Search local package index |
| `vulpkg update` | Update local package index |
| `vulpkg publish --tag <tag>` | Publish to GitHub Releases |
| `vulpkg run <file>` | Run a Vulpin file with deps |
| `vulpkg cache list` | List cached packages |
| `vulpkg cache clear` | Clear local cache |

## GitHub Authentication

For publishing and higher rate limits, set a GitHub token:

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
```

Or pass it directly:

```bash
vulpkg publish --tag v1.0.0 --token ghp_xxxxxxxxxxxx
```

## Package Format

Vulp packages are distributed via **GitHub Releases**. When you publish:

1. A zip archive of your project is uploaded
2. Individual `.vul` files are uploaded as assets
3. The release tag becomes the version

Users install by referencing `owner/repo@tag`.

## Local Index

Vulp maintains a local SQLite index at `~/.vulp/index.db` for fast lookups and offline search. Run `vulpkg update` to refresh it.

## License

MIT
