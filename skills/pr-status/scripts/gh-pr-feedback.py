#!/usr/bin/env python3
"""Read-only, bounded GitHub PR feedback inventory.

Usage: gh-pr-feedback.py <owner> <repo> <number> [<number> ...]

The JSON envelope is deterministic for an unchanged GitHub response. Consumers compare
`identity` plus `updatedAt`/`updateKey`, and use `stateKey` for lifecycle-only changes.
Partial fetches remain machine-readable and exit successfully; `partial` and `errors`
must be inspected before treating an inventory as complete.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from typing import Any


class InventoryConfig:
    def __init__(
        self,
        *,
        body_limit: int = 2_000,
        max_source_items: int = 200,
        max_records_per_pr: int = 500,
        page_size: int = 100,
    ) -> None:
        self.body_limit = max(1, body_limit)
        self.max_source_items = max(1, max_source_items)
        self.max_records_per_pr = max(1, max_records_per_pr)
        self.page_size = max(1, min(100, page_size, self.max_source_items))


THREAD_FIELDS = """
  nodes {
    id
    isResolved
    isOutdated
    path
    line
    originalLine
    comments(first: 100) {
      nodes {
        id
        databaseId
        author { login __typename }
        body
        createdAt
        updatedAt
        url
        replyTo { id databaseId }
      }
      pageInfo { hasNextPage endCursor }
    }
  }
  pageInfo { hasNextPage endCursor }
"""

REVIEW_FIELDS = """
  nodes {
    id
    databaseId
    author { login __typename }
    state
    body
    submittedAt
    updatedAt
    url
  }
  pageInfo { hasNextPage endCursor }
"""

COMMENT_FIELDS = """
  nodes {
    id
    databaseId
    author { login __typename }
    body
    createdAt
    updatedAt
    url
  }
  pageInfo { hasNextPage endCursor }
"""

FILE_FIELDS = """
  nodes { path }
  pageInfo { hasNextPage endCursor }
"""

CONNECTION_FIELDS = {
    "reviewThreads": THREAD_FIELDS,
    "reviews": REVIEW_FIELDS,
    "comments": COMMENT_FIELDS,
    "files": FILE_FIELDS,
}

SOURCE_ORDER = {
    "inline_review": 0,
    "review_summary": 1,
    "conversation": 2,
    "check_annotation": 3,
}

NOISE_CUES = (
    "coverage report",
    "deployment status",
    "preview is ready",
    "build report",
    "test report",
    "automated status",
    "<!-- sticky",
)
SECURITY_CUES = (
    "security",
    "vulnerability",
    "expose a token",
    "credential",
    "injection",
    "xss",
    "csrf",
)
BLOCKING_CUES = (
    "must be fixed",
    "must fix",
    "blocking",
    "block merge",
    "cannot merge",
)
CHANGE_CUES = (
    "please ",
    "should ",
    "needs to ",
    "need to ",
    "remove ",
    "add ",
    "change ",
    "update ",
    "fix ",
)


class GhClient:
    def _run(self, args: list[str]) -> object:
        completed = subprocess.run(
            ["gh", "api", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip() or "gh api failed"
            raise RuntimeError(message[:500])
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"gh api returned invalid JSON: {error}") from error

    def fetch_initial(self, owner: str, repo: str, numbers: list[int], page_size: int) -> dict:
        aliases = []
        for index, number in enumerate(numbers):
            aliases.append(
                f"""
                pr{index}: pullRequest(number: {number}) {{
                  number
                  url
                  headRefOid
                  reviewThreads(first: $pageSize) {{ {THREAD_FIELDS} }}
                  reviews(first: $pageSize) {{ {REVIEW_FIELDS} }}
                  comments(first: $pageSize) {{ {COMMENT_FIELDS} }}
                  files(first: $pageSize) {{ {FILE_FIELDS} }}
                }}
                """
            )
        query = f"""
        query($owner: String!, $repo: String!, $pageSize: Int!) {{
          viewer {{ login }}
          repository(owner: $owner, name: $repo) {{
            {''.join(aliases)}
          }}
        }}
        """
        result = self._run(
            [
                "graphql",
                "-f",
                f"query={query}",
                "-f",
                f"owner={owner}",
                "-f",
                f"repo={repo}",
                "-F",
                f"pageSize={page_size}",
            ]
        )
        if not isinstance(result, dict):
            raise RuntimeError("GraphQL response was not an object")
        return result

    def fetch_connection(
        self,
        owner: str,
        repo: str,
        number: int,
        source: str,
        after: str,
        page_size: int,
    ) -> dict:
        fields = CONNECTION_FIELDS[source]
        query = f"""
        query($owner: String!, $repo: String!, $number: Int!, $after: String!, $pageSize: Int!) {{
          repository(owner: $owner, name: $repo) {{
            pullRequest(number: $number) {{
              {source}(first: $pageSize, after: $after) {{ {fields} }}
            }}
          }}
        }}
        """
        result = self._run(
            [
                "graphql",
                "-f",
                f"query={query}",
                "-f",
                f"owner={owner}",
                "-f",
                f"repo={repo}",
                "-F",
                f"number={number}",
                "-f",
                f"after={after}",
                "-F",
                f"pageSize={page_size}",
            ]
        )
        if isinstance(result, dict) and result.get("errors"):
            messages = "; ".join(
                item.get("message", "GraphQL error") if isinstance(item, dict) else str(item)
                for item in result["errors"]
            )
            raise RuntimeError(messages)
        try:
            connection = result["data"]["repository"]["pullRequest"][source]
        except (KeyError, TypeError) as error:
            raise RuntimeError(f"GraphQL {source} page was incomplete") from error
        if not isinstance(connection, dict):
            raise RuntimeError(f"GraphQL {source} page was not an object")
        return connection

    def rest(self, endpoint: str) -> object:
        return self._run([endpoint])


def error_record(
    owner: str,
    repo: str,
    number: int | None,
    source: str,
    kind: str,
    message: str,
    *,
    retryable: bool,
) -> dict:
    return {
        "repository": f"{owner}/{repo}",
        "pr": number,
        "source": source,
        "kind": kind,
        "message": re.sub(r"\s+", " ", message).strip()[:500],
        "retryable": retryable,
    }


def bounded_text(value: object, limit: int) -> tuple[str, bool]:
    text = value if isinstance(value, str) else ""
    return text[:limit], len(text) > limit


def gist(value: str, limit: int) -> str:
    return re.sub(r"\s+", " ", value).strip()[: min(160, limit)]


def author_fields(author: object, viewer: str) -> tuple[str | None, str, bool]:
    if not isinstance(author, dict):
        return None, "unknown", False
    login = author.get("login") if isinstance(author.get("login"), str) else None
    typename = author.get("__typename")
    self_authored = bool(login and viewer and login.casefold() == viewer.casefold())
    if self_authored:
        kind = "self"
    elif typename == "Bot" or (login and login.casefold().endswith("[bot]")):
        kind = "bot"
    elif login:
        kind = "human"
    else:
        kind = "unknown"
    return login, kind, self_authored


def classify(
    *,
    body: str,
    source: str,
    lifecycle: str,
    review_state: str | None,
    author_kind: str,
    self_authored: bool,
    annotation_level: str | None = None,
) -> tuple[str, str, bool]:
    lowered = body.casefold()
    if review_state == "APPROVED":
        semantic_type = "approval"
    elif source == "check_annotation":
        semantic_type = "ci_annotation"
    elif author_kind == "bot" and any(cue in lowered for cue in NOISE_CUES):
        semantic_type = "automated_status"
    elif any(cue in lowered for cue in SECURITY_CUES):
        semantic_type = "security_claim"
    elif review_state == "CHANGES_REQUESTED" or any(cue in lowered for cue in BLOCKING_CUES):
        semantic_type = "blocking_claim"
    elif "```suggestion" in lowered or "suggestion:" in lowered or "i suggest" in lowered:
        semantic_type = "suggestion"
    elif "?" in body:
        semantic_type = "question"
    elif any(cue in lowered for cue in CHANGE_CUES):
        semantic_type = "change_request"
    else:
        semantic_type = "informational"

    if self_authored or lifecycle in {"resolved", "outdated", "dismissed"}:
        actionability = "suppressed"
    elif semantic_type == "automated_status":
        actionability = "noise"
    elif semantic_type in {"approval", "informational"}:
        actionability = "informational"
    elif source == "check_annotation" and annotation_level not in {"warning", "failure"}:
        actionability = "informational"
    else:
        actionability = "candidate"
    return semantic_type, actionability, actionability == "candidate"


def base_record(
    *,
    owner: str,
    repo: str,
    number: int,
    pr_url: str | None,
    identity: str,
    source: str,
    role: str | None,
    author: object,
    viewer: str,
    body: object,
    created_at: str | None,
    updated_at: str | None,
    lifecycle: str,
    review_state: str | None,
    path: str | None,
    line: int | None,
    url: str | None,
    targets: dict,
    config: InventoryConfig,
    annotation_level: str | None = None,
) -> dict:
    raw_body, truncated = bounded_text(body, config.body_limit)
    login, author_kind, self_authored = author_fields(author, viewer)
    semantic_type, actionability, requires_validation = classify(
        body=raw_body,
        source=source,
        lifecycle=lifecycle,
        review_state=review_state,
        author_kind=author_kind,
        self_authored=self_authored,
        annotation_level=annotation_level,
    )
    effective_update = updated_at or created_at
    return {
        "identity": identity,
        "updateKey": f"{identity}@{effective_update or ''}",
        "stateKey": f"{identity}@{effective_update or ''}:{lifecycle}:{review_state or ''}",
        "repository": f"{owner}/{repo}",
        "pr": number,
        "prUrl": pr_url,
        "source": source,
        "role": role,
        "author": login,
        "authorKind": author_kind,
        "selfAuthored": self_authored,
        "createdAt": created_at,
        "updatedAt": effective_update,
        "path": path,
        "line": line,
        "url": url,
        "lifecycle": lifecycle,
        "reviewState": review_state,
        "semanticType": semantic_type,
        "actionability": actionability,
        "requiresValidation": requires_validation,
        "rawBody": raw_body,
        "gist": gist(raw_body, config.body_limit),
        "bodyTruncated": truncated,
        "targets": targets,
    }


def collect_connection(
    client: object,
    owner: str,
    repo: str,
    number: int,
    source: str,
    initial: object,
    config: InventoryConfig,
    errors: list[dict],
) -> list[dict]:
    if not isinstance(initial, dict):
        errors.append(error_record(owner, repo, number, source, "api", "connection missing", retryable=True))
        return []
    nodes = [node for node in initial.get("nodes", []) if isinstance(node, dict)]
    page_info = initial.get("pageInfo") if isinstance(initial.get("pageInfo"), dict) else {}
    nodes = nodes[: config.max_source_items]

    while page_info.get("hasNextPage"):
        if len(nodes) >= config.max_source_items:
            errors.append(
                error_record(
                    owner,
                    repo,
                    number,
                    source,
                    "truncated",
                    f"{source} exceeded the {config.max_source_items}-item cap",
                    retryable=False,
                )
            )
            break
        cursor = page_info.get("endCursor")
        if not isinstance(cursor, str) or not cursor:
            errors.append(error_record(owner, repo, number, source, "api", "pagination cursor missing", retryable=True))
            break
        try:
            page = client.fetch_connection(owner, repo, number, source, cursor, config.page_size)
        except Exception as exception:
            errors.append(error_record(owner, repo, number, source, "api", str(exception), retryable=True))
            break
        page_nodes = [node for node in page.get("nodes", []) if isinstance(node, dict)]
        remaining = config.max_source_items - len(nodes)
        nodes.extend(page_nodes[:remaining])
        page_info = page.get("pageInfo") if isinstance(page.get("pageInfo"), dict) else {}
        if len(page_nodes) > remaining or (page_info.get("hasNextPage") and len(nodes) >= config.max_source_items):
            errors.append(
                error_record(
                    owner,
                    repo,
                    number,
                    source,
                    "truncated",
                    f"{source} exceeded the {config.max_source_items}-item cap",
                    retryable=False,
                )
            )
            break

    deduplicated: dict[str, dict] = {}
    anonymous: list[dict] = []
    for node in nodes:
        node_id = node.get("id")
        if isinstance(node_id, str):
            deduplicated[node_id] = node
        else:
            anonymous.append(node)
    return [*deduplicated.values(), *anonymous]


def inline_records(
    owner: str,
    repo: str,
    number: int,
    pr_url: str | None,
    viewer: str,
    threads: list[dict],
    config: InventoryConfig,
    errors: list[dict],
) -> list[dict]:
    records = []
    for thread in threads:
        thread_id = thread.get("id")
        if not isinstance(thread_id, str):
            continue
        if thread.get("isResolved"):
            lifecycle = "resolved"
        elif thread.get("isOutdated"):
            lifecycle = "outdated"
        else:
            lifecycle = "unresolved"
        comments = thread.get("comments") if isinstance(thread.get("comments"), dict) else {}
        comment_nodes = [node for node in comments.get("nodes", []) if isinstance(node, dict)]
        if isinstance(comments.get("pageInfo"), dict) and comments["pageInfo"].get("hasNextPage"):
            errors.append(
                error_record(
                    owner,
                    repo,
                    number,
                    "inline_comments",
                    "truncated",
                    f"thread {thread_id} exceeded the 100-comment cap",
                    retryable=False,
                )
            )
        root = next((node for node in comment_nodes if not node.get("replyTo")), comment_nodes[0] if comment_nodes else None)
        root_database_id = root.get("databaseId") if isinstance(root, dict) else None
        root_node_id = root.get("id") if isinstance(root, dict) else None
        self_flags = [author_fields(node.get("author"), viewer)[2] for node in comment_nodes]
        thread_has_self_reply = any(self_flags)
        for comment_index, comment in enumerate(comment_nodes):
            node_id = comment.get("id")
            if not isinstance(node_id, str):
                continue
            reply_to = comment.get("replyTo")
            role = "reply" if isinstance(reply_to, dict) else "root"
            targets = {
                "reply": {
                    "surface": "inline",
                    "commentId": root_database_id,
                    "commentNodeId": root_node_id,
                },
                "resolveThreadId": thread_id,
            }
            record = base_record(
                owner=owner,
                repo=repo,
                number=number,
                pr_url=pr_url,
                identity=f"inline:{node_id}",
                source="inline_review",
                role=role,
                author=comment.get("author"),
                viewer=viewer,
                body=comment.get("body"),
                created_at=comment.get("createdAt"),
                updated_at=comment.get("updatedAt"),
                lifecycle=lifecycle,
                review_state=None,
                path=thread.get("path"),
                line=thread.get("line") or thread.get("originalLine"),
                url=comment.get("url"),
                targets=targets,
                config=config,
            )
            record["nodeId"] = node_id
            record["databaseId"] = comment.get("databaseId")
            record["threadId"] = thread_id
            record["isResolved"] = bool(thread.get("isResolved"))
            record["isOutdated"] = bool(thread.get("isOutdated"))
            record["replyToNodeId"] = reply_to.get("id") if isinstance(reply_to, dict) else None
            record["replyToDatabaseId"] = reply_to.get("databaseId") if isinstance(reply_to, dict) else None
            record["hasLaterSelfReply"] = any(self_flags[comment_index + 1 :])
            record["threadHasSelfReply"] = thread_has_self_reply
            records.append(record)
    return records


def review_records(
    owner: str,
    repo: str,
    number: int,
    pr_url: str | None,
    viewer: str,
    reviews: list[dict],
    config: InventoryConfig,
) -> list[dict]:
    records = []
    for review in reviews:
        node_id = review.get("id")
        state = review.get("state")
        if not isinstance(node_id, str) or state == "PENDING":
            continue
        lifecycle = "dismissed" if state == "DISMISSED" else "active"
        record = base_record(
            owner=owner,
            repo=repo,
            number=number,
            pr_url=pr_url,
            identity=f"review:{node_id}",
            source="review_summary",
            role="summary",
            author=review.get("author"),
            viewer=viewer,
            body=review.get("body"),
            created_at=review.get("submittedAt"),
            updated_at=review.get("updatedAt") or review.get("submittedAt"),
            lifecycle=lifecycle,
            review_state=state,
            path=None,
            line=None,
            url=review.get("url"),
            targets={
                "reply": {"surface": "conversation", "prNumber": number},
                "resolveThreadId": None,
            },
            config=config,
        )
        record["nodeId"] = node_id
        record["databaseId"] = review.get("databaseId")
        records.append(record)
    return records


def conversation_records(
    owner: str,
    repo: str,
    number: int,
    pr_url: str | None,
    viewer: str,
    comments: list[dict],
    config: InventoryConfig,
) -> list[dict]:
    records = []
    for comment in comments:
        node_id = comment.get("id")
        if not isinstance(node_id, str):
            continue
        record = base_record(
            owner=owner,
            repo=repo,
            number=number,
            pr_url=pr_url,
            identity=f"conversation:{node_id}",
            source="conversation",
            role="comment",
            author=comment.get("author"),
            viewer=viewer,
            body=comment.get("body"),
            created_at=comment.get("createdAt"),
            updated_at=comment.get("updatedAt"),
            lifecycle="active",
            review_state=None,
            path=None,
            line=None,
            url=comment.get("url"),
            targets={
                "reply": {"surface": "conversation", "prNumber": number},
                "resolveThreadId": None,
            },
            config=config,
        )
        record["nodeId"] = node_id
        record["databaseId"] = comment.get("databaseId")
        records.append(record)
    return records


def rest_pages(
    client: object,
    endpoint_prefix: str,
    response_items: Any,
    cap: int,
) -> tuple[list[dict], bool]:
    items: list[dict] = []
    page = 1
    truncated = False
    while len(items) < cap:
        response = client.rest(f"{endpoint_prefix}{page}")
        page_items = response_items(response)
        if not isinstance(page_items, list):
            raise RuntimeError("REST response did not contain a list")
        dict_items = [item for item in page_items if isinstance(item, dict)]
        remaining = cap - len(items)
        items.extend(dict_items[:remaining])
        if len(dict_items) > remaining:
            truncated = True
            break
        if len(dict_items) < 100:
            break
        if len(items) >= cap:
            truncated = True
            break
        page += 1
    return items, truncated


def annotation_records(
    client: object,
    owner: str,
    repo: str,
    number: int,
    pr_url: str | None,
    head_sha: object,
    changed_files: set[str],
    config: InventoryConfig,
    errors: list[dict],
) -> list[dict]:
    if not isinstance(head_sha, str) or not head_sha:
        return []
    check_prefix = f"repos/{owner}/{repo}/commits/{head_sha}/check-runs?per_page=100&page="
    try:
        runs, runs_truncated = rest_pages(
            client,
            check_prefix,
            lambda response: response.get("check_runs") if isinstance(response, dict) else None,
            config.max_source_items,
        )
    except Exception as exception:
        errors.append(error_record(owner, repo, number, "check_runs", "api", str(exception), retryable=True))
        return []
    if runs_truncated:
        errors.append(
            error_record(
                owner,
                repo,
                number,
                "check_runs",
                "truncated",
                f"check runs exceeded the {config.max_source_items}-item cap",
                retryable=False,
            )
        )

    records = []
    for run in runs:
        run_id = run.get("id")
        if not run_id or not run.get("annotations_count"):
            continue
        annotation_prefix = f"repos/{owner}/{repo}/check-runs/{run_id}/annotations?per_page=100&page="
        try:
            annotations, annotations_truncated = rest_pages(
                client,
                annotation_prefix,
                lambda response: response,
                config.max_source_items,
            )
        except Exception as exception:
            errors.append(error_record(owner, repo, number, "check_annotations", "api", str(exception), retryable=True))
            continue
        if annotations_truncated:
            errors.append(
                error_record(
                    owner,
                    repo,
                    number,
                    "check_annotations",
                    "truncated",
                    f"check annotations exceeded the {config.max_source_items}-item cap",
                    retryable=False,
                )
            )
        for annotation in annotations:
            path = annotation.get("path")
            if path not in changed_files:
                continue
            raw_identity = "\0".join(
                str(value or "")
                for value in (
                    run_id,
                    path,
                    annotation.get("start_line"),
                    annotation.get("end_line"),
                    annotation.get("title"),
                    annotation.get("message"),
                )
            )
            digest = hashlib.sha256(raw_identity.encode()).hexdigest()[:24]
            record = base_record(
                owner=owner,
                repo=repo,
                number=number,
                pr_url=pr_url,
                identity=f"check_annotation:{run_id}:{digest}",
                source="check_annotation",
                role="annotation",
                author={"login": run.get("name"), "__typename": "Bot"},
                viewer="",
                body=annotation.get("message"),
                created_at=run.get("completed_at") or run.get("updated_at"),
                updated_at=run.get("updated_at") or run.get("completed_at"),
                lifecycle="active",
                review_state=None,
                path=path,
                line=annotation.get("start_line"),
                url=annotation.get("blob_href") or run.get("html_url"),
                targets={"reply": None, "resolveThreadId": None},
                config=config,
                annotation_level=annotation.get("annotation_level"),
            )
            record["nodeId"] = None
            record["databaseId"] = None
            record["annotationLevel"] = annotation.get("annotation_level")
            record["checkRunId"] = run_id
            record["checkName"] = run.get("name")
            record["identityBasis"] = "check run, location, title, and message digest"
            title, title_truncated = bounded_text(annotation.get("title"), config.body_limit)
            record["annotationTitle"] = title
            record["annotationTitleTruncated"] = title_truncated
            records.append(record)
    return records


def collect_inventory(
    client: object,
    owner: str,
    repo: str,
    numbers: list[int],
    config: InventoryConfig | None = None,
) -> dict:
    config = config or InventoryConfig()
    numbers = list(dict.fromkeys(numbers))
    errors: list[dict] = []
    records: list[dict] = []
    try:
        payload = client.fetch_initial(owner, repo, numbers, config.page_size)
    except Exception as exception:
        errors.append(error_record(owner, repo, None, "initial", "api", str(exception), retryable=True))
        return inventory_envelope(owner, repo, numbers, config, records, errors)

    graphql_errors = payload.get("errors") if isinstance(payload, dict) else None
    if isinstance(graphql_errors, list):
        for item in graphql_errors:
            message = item.get("message") if isinstance(item, dict) else str(item)
            errors.append(error_record(owner, repo, None, "initial", "api", message, retryable=True))
    data = payload.get("data") if isinstance(payload, dict) and isinstance(payload.get("data"), dict) else {}
    viewer_node = data.get("viewer") if isinstance(data.get("viewer"), dict) else {}
    viewer = viewer_node.get("login") if isinstance(viewer_node.get("login"), str) else ""
    if not viewer:
        errors.append(
            error_record(
                owner,
                repo,
                None,
                "viewer",
                "api",
                "viewer login unavailable; self-authored classification is incomplete",
                retryable=True,
            )
        )
    repository = data.get("repository") if isinstance(data.get("repository"), dict) else {}

    for index, number in enumerate(numbers):
        pr = repository.get(f"pr{index}")
        if not isinstance(pr, dict):
            errors.append(error_record(owner, repo, number, "initial", "not_found", "pull request unavailable", retryable=False))
            continue
        pr_url = pr.get("url") if isinstance(pr.get("url"), str) else None
        source_connections = {}
        for source in CONNECTION_FIELDS:
            source_connections[source] = collect_connection(
                client,
                owner,
                repo,
                number,
                source,
                pr.get(source),
                config,
                errors,
            )

        pr_records = []
        pr_records.extend(
            inline_records(owner, repo, number, pr_url, viewer, source_connections["reviewThreads"], config, errors)
        )
        pr_records.extend(review_records(owner, repo, number, pr_url, viewer, source_connections["reviews"], config))
        pr_records.extend(
            conversation_records(owner, repo, number, pr_url, viewer, source_connections["comments"], config)
        )
        changed_files = {
            node.get("path")
            for node in source_connections["files"]
            if isinstance(node.get("path"), str)
        }
        pr_records.extend(
            annotation_records(
                client,
                owner,
                repo,
                number,
                pr_url,
                pr.get("headRefOid"),
                changed_files,
                config,
                errors,
            )
        )

        deduplicated = {record["identity"]: record for record in pr_records}
        ordered = sorted(
            deduplicated.values(),
            key=lambda record: (
                SOURCE_ORDER[record["source"]],
                record.get("createdAt") or "",
                record["identity"],
            ),
        )
        if len(ordered) > config.max_records_per_pr:
            errors.append(
                error_record(
                    owner,
                    repo,
                    number,
                    "records",
                    "truncated",
                    f"records exceeded the {config.max_records_per_pr}-item per-PR cap",
                    retryable=False,
                )
            )
            ordered = ordered[: config.max_records_per_pr]
        records.extend(ordered)

    return inventory_envelope(owner, repo, numbers, config, records, errors)


def inventory_envelope(
    owner: str,
    repo: str,
    numbers: list[int],
    config: InventoryConfig,
    records: list[dict],
    errors: list[dict],
) -> dict:
    return {
        "schemaVersion": 1,
        "repository": f"{owner}/{repo}",
        "pullRequests": numbers,
        "partial": bool(errors),
        "errors": errors,
        "limits": {
            "bodyChars": config.body_limit,
            "sourceItems": config.max_source_items,
            "recordsPerPullRequest": config.max_records_per_pr,
        },
        "records": records,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("numbers", nargs="+", type=int)
    parser.add_argument("--body-limit", type=int, default=2_000)
    parser.add_argument("--max-source-items", type=int, default=200)
    parser.add_argument("--max-records-per-pr", type=int, default=500)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    config = InventoryConfig(
        body_limit=args.body_limit,
        max_source_items=args.max_source_items,
        max_records_per_pr=args.max_records_per_pr,
    )
    result = collect_inventory(GhClient(), args.owner, args.repo, args.numbers, config)
    json.dump(result, sys.stdout, indent=2 if args.pretty else None, sort_keys=args.pretty)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
