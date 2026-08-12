# vulp

Package manager for the [Vulpin](https://github.com/stefand-0/vulpin) programming language.

## Installation

```bash
pip install vulp
```

## Quick Start

```bash
# Initialize a new Vulpin package
vulp init --name my-package

# Add a dependency from GitHub Releases
vulp add stefand-0/string-utils
vulp add stefand-0/json@v1.0.0

# Install all dependencies
vulp install

# Run your Vulpin program with dependencies
vulp run main.vul

# Publish your package to GitHub Releases
vulp publish --tag v1.0.0
```

## Configuration: `vulpin.toml`

```toml
[package]
name = "my-package"
version = "1.0.0"
description = "A useful Vulpin library"
author = "stefand-0"
license = "MIT"

[deps]
"stefand-0/string-utils" = "latest"
"stefand-0/json" = ">=0.5.0"
```

## Commands

| Command | Description |
|---------|-------------|
| `vulp init` | Create a new `vulpin.toml` |
| `vulp add <pkg>` | Add a dependency |
| `vulp install` | Install dependencies from `vulpin.toml` |
| `vulp remove <pkg>` | Remove a dependency |
| `vulp list` | List installed dependencies |
| `vulp search <query>` | Search local package index |
| `vulp update` | Update local package index |
| `vulp publish --tag <tag>` | Publish to GitHub Releases |
| `vulp run <file>` | Run a Vulpin file with deps |
| `vulp cache list` | List cached packages |
| `vulp cache clear` | Clear local cache |

## GitHub Authentication

For publishing and higher rate limits, set a GitHub token:

```bash
export GITHUB_TOKEN=ghp_xxxxxxxxxxxx
```

Or pass it directly:

```bash
vulp publish --tag v1.0.0 --token ghp_xxxxxxxxxxxx
```

## Package Format

Vulp packages are distributed via **GitHub Releases**. When you publish:

1. A zip archive of your project is uploaded
2. Individual `.vul` files are uploaded as assets
3. The release tag becomes the version

Users install by referencing `owner/repo@tag`.

## Local Index

Vulp maintains a local SQLite index at `~/.vulp/index.db` for fast lookups and offline search. Run `vulp update` to refresh it.

## License

MIT
