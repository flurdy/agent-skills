---
name: confluence
description: >
  Read Confluence pages and comments. Use to fetch design docs, ADRs, runbooks,
  or any wiki content for context when working on tasks.
allowed-tools: "Read,AskUserQuestion,mcp__confluence__*"
version: "1.0.0"
author: "flurdy"
---

# Confluence Page Lookup

Fetch content from Confluence pages and their comments.

## Requirements

This skill requires the [mcp-server-atlassian-confluence](https://github.com/aashari/mcp-server-atlassian-confluence) MCP server configured with the name `confluence`.

## Usage

```
# Search for a page by title
/confluence search "Authentication Design Doc"

# Get a page by ID
/confluence 123456

# Get a page by URL
/confluence https://myorg.atlassian.net/wiki/spaces/ENG/pages/123456
```

## Instructions

When invoked, determine the user's intent from the arguments provided.

### 1. Search for Pages

If the user provides a search term (not a numeric ID or URL):

```
mcp__confluence__confluence_get with:
  path: /rest/api/content/search
  jq: "{results: .results[] | {id: .id, title: .title, space: .space.key, url: ._links.webui}}"
  query: "cql=title~\"<search term>\" OR text~\"<search term>\""
```

Present results as a table and ask the user which page to fetch.

### 2. Get Page Content

If the user provides a page ID or after selecting from search results:

```
mcp__confluence__confluence_get with:
  path: /rest/api/content/<pageId>?expand=body.storage,version,space,ancestors
  jq: "{id: .id, title: .title, space: .space.key, version: .version.number, ancestors: [.ancestors[].title], body: .body.storage.value}"
```

### 3. Get Page Comments

If the user asks for comments on a page:

```
mcp__confluence__confluence_get with:
  path: /rest/api/content/<pageId>/child/comment?expand=body.storage,version
  jq: "{comments: [.results[] | {author: .version.by.displayName, date: .version.when, body: .body.storage.value}]}"
```

### 4. Parse URL

If the user provides a Confluence URL, extract the page ID from it:
- Pattern: `https://<domain>/wiki/spaces/<spaceKey>/pages/<pageId>/<title>`
- Extract `<pageId>` and use it for the page content lookup in step 2.

### 5. Present Results

Provide the user with:
- Page title
- Space key
- Last updated version number
- Ancestor path (breadcrumbs) if available
- Page content (converted from Confluence storage format to readable text)
- Comments (if requested)

Strip HTML/XML tags from the storage format body to present clean readable text.

### Example Output

```
Page: Authentication Design Doc
Space: ENG
Version: 12
Path: Engineering > Architecture > Auth

---

## Overview
This document describes the authentication flow for...

---

Comments (3):
  - Alice (2026-01-15): Approved, looks good.
  - Bob (2026-01-14): Can we add a sequence diagram?
  - Carol (2026-01-13): Initial review — see inline comments.
```
