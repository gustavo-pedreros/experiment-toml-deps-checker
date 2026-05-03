# ADR-0005: Repo content is in English regardless of contributor language

## Status

Accepted — 2026-05-03

## Context

The original repository contained Spanish content in the README and
some user-facing strings. The project is open source and aims to be
useful to Android teams worldwide. Many of its primary maintainers
speak Spanish as a first language and frequently discuss the
project in Spanish.

A consistent convention is needed so that contributors do not have
to guess which artifacts to translate, and so that the repository
remains accessible to readers regardless of language background.

## Decision

All repository artifacts are written in English. This includes:

- Source code, including identifiers and inline comments
- The `README.md` and any other documentation files (`docs/`)
- Configuration keys and example configuration files
- CLI flags, help text, and error messages
- Tool output: console summaries, Markdown reports, JSON keys,
  Slack message text
- Commit messages and PR descriptions
- Architecture Decision Records and proposals

Maintainers and contributors may communicate in any language they
prefer (issues, PR review threads, chat). The artifact remains
English.

If localization of user-facing output becomes a requirement in the
future, it will be handled through a proper i18n mechanism (string
catalogs, locale selection) rather than by allowing alternate
languages to creep into the source artifacts.

## Consequences

**Positive**

- A single, predictable rule: contributors do not have to guess
- The project is immediately accessible to a global audience
- Code review focuses on substance rather than language choice
- Search and grep work consistently across the repo

**Negative**

- Native Spanish speakers maintaining the project occasionally
  carry a small translation overhead when capturing ideas
  originally discussed in Spanish
- Some idiomatic phrases lose nuance in translation; this is
  acceptable for a technical project
