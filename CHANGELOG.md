# CHANGELOG

<!-- version list -->

## v0.3.0 (2025-06-25)

### Bug Fixes

- Add URL verification to resolve broken wikilinks and cache results
  ([`ed0279c`](https://github.com/jsade/atlas-markdown/commit/ed0279c21c907c815e1ce2fb2b9056dbf512368b))

- Broken wikilinks handling.
  ([`17f9b3d`](https://github.com/jsade/atlas-markdown/commit/17f9b3d6fe685739da0a9892233930bf5d18e208))

- Partial fix to broken wikilink handling and add relative path support in link resolver.
  ([`1e25eec`](https://github.com/jsade/atlas-markdown/commit/1e25eece5bf552829a6c87f9fe249ac14e6adf00))

### Documentation

- Added wikilinks devnotes and couple proposals
  ([`17f9b3d`](https://github.com/jsade/atlas-markdown/commit/17f9b3d6fe685739da0a9892233930bf5d18e208))

### Features

- Enhance LinkResolver to support redirect handling and add tests for redirect functionality
  ([`ab17f11`](https://github.com/jsade/atlas-markdown/commit/ab17f11ec58949230b50e0aedf237cb893d4db6f))


## v0.2.1 (2025-06-24)

### Bug Fixes

- Update version management to use semantic-release in pyproject.toml
  ([`3c98107`](https://github.com/jsade/atlas-markdown/commit/3c981071314f299576c7c2eb2d0514e8fead2b47))


## v0.2.0 (2025-06-24)

### Build System

- Clean up patch tags in pyproject.toml
  ([`d500edc`](https://github.com/jsade/atlas-markdown/commit/d500edcacec9252d98d94524098fe8f89b18c5e9))

- Github action fixes
  ([`625a755`](https://github.com/jsade/atlas-markdown/commit/625a7553fee6478aacca0e4acb05bd35e733736a))

- Refactored github action for semantic releases and added a new action for PR comments
  ([`32570c0`](https://github.com/jsade/atlas-markdown/commit/32570c041e4a5ab16472a054e77018423e0e47fe))

- Revert version number to 0.1.1 in fallback and pyproject.toml
  ([`79036ce`](https://github.com/jsade/atlas-markdown/commit/79036cee18c8cec0bc0e51145f1e894b1d35a621))

- Tweaking github actions
  ([`b724f6e`](https://github.com/jsade/atlas-markdown/commit/b724f6ec9849e8c0d77454ff33f37937575407e1))

- **deps**: Bump urllib3 from 2.4.0 to 2.5.0
  ([`8e8af6a`](https://github.com/jsade/atlas-markdown/commit/8e8af6a7b214670ffa91f7ebb20f90dcb07cb468))

### Features

- Enhance command-line interface with default behavior and version info
  ([`3fa6250`](https://github.com/jsade/atlas-markdown/commit/3fa6250da7c083a630e2c8632864ac4cefcd9d46))

### Refactoring

- Add custom help command with version info to CLI
  ([`fde3227`](https://github.com/jsade/atlas-markdown/commit/fde3227b4016805a6468d76df254bf33d3803390))

- Improve type hints and logging in various modules; update dependencies and fix markdown linting
  issues
  ([`dd92f06`](https://github.com/jsade/atlas-markdown/commit/dd92f069c42d5723c16c94b73573acbd90da541b))

- Restructure project configuration and build process
  ([`3d00f4b`](https://github.com/jsade/atlas-markdown/commit/3d00f4bac2322e6f070a84c3738703223946ce41))


## v0.1.2 (2025-06-17)

Initial testing release.
