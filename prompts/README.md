# Prompt templates

Shared slash-command templates for Pi and Claude Code, installed by `make apply`:

- [`/about <id-or-name>`](about.md) — orient on an issue, pull request, branch, worktree, Git ref, or stash
- [`/ask-astra <question>`](ask-astra.md) — ask Codex Astra for a repository-grounded review or second opinion
- [`/ask-claude <question>`](ask-claude.md) — ask Claude for a repository-grounded second opinion
- [`/ask-fable <question>`](ask-fable.md) — ask Claude Fable for a repository-grounded second opinion
- [`/ask-peer <question>`](ask-peer.md) — ask an independent peer for a repository-grounded second opinion
- [`/ask-premium <question>`](ask-premium.md) — ask the premium multi-provider quorum for a second opinion
- [`/ask-quorum <question>`](ask-quorum.md) — ask the default multi-provider quorum for a repository-grounded second opinion
- [`/ask-sol <question>`](ask-sol.md) — ask Codex Sol for a repository-grounded second opinion
- [`/discuss <question>`](discuss.md) — inspect and research without changing files or external state
- [`/plain <topic-or-text>`](plain.md) — explain a topic clearly for a smart non-specialist
- [`/quota`](quota.md) — report Codex and Claude usage windows plus OpenRouter account credits, via the independent ai-tools `codex-quota`, `claude-quota` and `openrouter-quota` helpers
- [`/squash-msg [PR-number]`](squash-msg.md) — draft a squash-merge commit message for approval
- [`/trim-comments [file-or-PR]`](trim-comments.md) — remove redundant inline comments and docblocks
- [`/watch-landscape [minutes]`](watch-landscape.md) — refresh `/landscape quick` on a fixed cadence until end of day
- [`/yesterday`](yesterday.md) — run the canonical `/today --previous-workday` recap in Pi or Claude Code

Codex uses `/today --previous-workday` directly because repository prompt templates are not installed there.
See [installation and configuration](../docs/installation.md#prompt-templates) for client setup.

## Quota report notes

`/quota` keeps routine output to figures, resets and retrieval times. Unknown values, stale windows
and provider errors remain visible, but standing caveats and the cost reminder are not repeated:

- Values describe the accounts signed in to the Codex CLI and Claude Code; alignment with Pi's
  active accounts is not verified. A snapshot does not guarantee future requests.
- Codex credits are ChatGPT/Codex capacity, not API dollars, extra weekly allowance or request counts.
- Claude Code's usage panel is undocumented human-readable text. Unrecognised or missing values are
  unknown, never zero. Its approximate, local-only "What's contributing" breakdown is excluded.
- Claude Code prints reset dates without a year; the helper resolves the first matching time after
  retrieval in the reported zone. Unrecognised times or zones remain unknown.
- OpenRouter credits describe the account of the management key stored as `openrouter_management`
  under the explicitly configured `SECRET_API_KEY_PROJECT`. Its alignment with inference keys or
  Pi's active account is not verified; no account is discovered or switched automatically.
- OpenRouter totals are canonical decimal strings of the parsed API numbers; remaining is a
  separately labelled derived decimal difference. The helper adds no binary-subtraction noise,
  does not round the reported totals, and retains zero/negative remaining. The API schema calls
  the unit credits, so the report does not assume USD. It is not a subscription window or reset.
- `/quota` uses a model turn. Running any of the three helpers directly does not.

The helpers retain their full `caveats` arrays in JSON. See the
[quota helper documentation](https://github.com/flurdy/ai-tools/tree/main/pi/quota) for source and
parsing details.
