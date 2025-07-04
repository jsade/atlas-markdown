# CHANGELOG

<!-- version list -->

## v0.5.0 (2025-07-04)

### Bug Fixes

- Handle hyphenated YAML keys and extract shared formatter utility
  ([`44f22aa`](https://github.com/jsade/atlas-markdown/commit/44f22aa16661c22649940053a55f81a390a2843f))

- Improve PR release preview to handle branch restrictions
  ([`fcb7ca8`](https://github.com/jsade/atlas-markdown/commit/fcb7ca89dfbc6054064c265b8cdbe8ab9b84a0df))

### Build System

- **deps**: Bump pillow from 11.2.1 to 11.3.0
  ([`be3e2f3`](https://github.com/jsade/atlas-markdown/commit/be3e2f35a1023f77c40bb8c1caa3310a62da8af4))

### Documentation

- Add no-h1-headings to readme
  ([`8d2f45f`](https://github.com/jsade/atlas-markdown/commit/8d2f45f957e198c2ddb4ff17255bab8d84cd6ef8))

### Features

- Add auto-tagging feature and support for disabling tags in markdown output
  ([`c107f66`](https://github.com/jsade/atlas-markdown/commit/c107f66f47434e2765062c0095ca726e8bcf1b47))

- Add auto-tagging feature with semantic content analysis
  ([`6e417af`](https://github.com/jsade/atlas-markdown/commit/6e417af3c048e09a14499198fef9a5bed626cba8))

### Refactoring

- Change option from --include-resources to --exclude-resources in CLI
  ([`3ea3d87`](https://github.com/jsade/atlas-markdown/commit/3ea3d876739c6f1cc3b302e3063c4ec680639000))


## v0.4.0 (2025-06-25)

### Documentation

- Add auto-tagging proposal
  ([`6206068`](https://github.com/jsade/atlas-markdown/commit/6206068c46c6cd3415b3b9517cb56676372a742d))

- Convert redirect handling proposal to developer guide
  ([`df0d23e`](https://github.com/jsade/atlas-markdown/commit/df0d23e31d6963dcb07ab89a032f7d4edaa4d2ca))

### Features

- Add support for disabling H1 headings in markdown output
  ([`6206068`](https://github.com/jsade/atlas-markdown/commit/6206068c46c6cd3415b3b9517cb56676372a742d))

### Refactoring

- Migrate from .env file to prefixed environment variables
  ([`6047248`](https://github.com/jsade/atlas-markdown/commit/604724824bf6b82f50655be74494098b78a01a13))


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
