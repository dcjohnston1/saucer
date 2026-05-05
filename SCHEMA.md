# Saucer — Firestore Schema

## Implemented

### `settings/` (existing)
| Document | Fields | Notes |
|---|---|---|
| `email_filters` | `addresses: string[]` | Gmail sender allow-list |
| `keyword_filters` | `keywords: string[]` | Gmail subject/body include keywords |
| `exclude_keyword_filters` | `keywords: string[]` | Hidden from email list if matched |

### `user_settings/` (added Phase 1)
Document ID = user's email address (e.g., `dcjohnston1@gmail.com`).

```
user_settings/{email}
  roles:       string[]   — free-text role descriptions
  preferences: string[]   — free-text preference descriptions
```

Example:
```json
{
  "roles": ["I handle school stuff", "I handle logistics"],
  "preferences": ["I prefer brief summaries", "I handle weekday scheduling"]
}
```

Gemini receives this as a `HOUSEHOLD MEMBER CONTEXT` block in the system prompt on every chat message, enabling smart task routing.

---

## Planned (not yet implemented)

### `conversation_history/`
Stores per-session chat logs for future context retrieval.

```
conversation_history/{session_id}
  user:       string      — email of user who started the session
  messages:   array
    role:     "user" | "assistant"
    content:  string
    timestamp: Timestamp
  created_at: Timestamp
```

Index: `(user, created_at DESC)` for "recent conversations by user" queries.

### `decision_rules/`
If/then routing rules created by the bot or users. Example: "if sender is Glenwood, assign to Emily."

```
decision_rules/{rule_id}
  condition:    string     — natural-language condition (e.g., "sender contains Glenwood")
  action:       string     — resulting action (e.g., "assign to emily.osteen.johnston@gmail.com")
  created_at:   Timestamp
  created_by:   string     — email of user who created the rule
  active:       boolean
```

Index: `(active, created_at DESC)`.

### `feedback_log/`
Thumbs-up / thumbs-down on proposal decisions, for future model tuning or rule refinement.

```
feedback_log/{entry_id}
  email_id:     string     — source email
  proposal_id:  string     — the proposal that was rated
  rating:       "up" | "down"
  user:         string     — email of user who rated
  timestamp:    Timestamp
  notes:        string?    — optional free-text reason
```

Index: `(rating, timestamp DESC)` for "recent negative feedback" queries.

---

## Context Access Pattern (Phase 3 Decision)

**Chosen: pre-load hybrid.** Roles and preferences (~100 tokens) are fetched from Firestore at the start of every `process_message()` call and injected directly into the Gemini system prompt.

Rationale:
- Data is tiny — pre-loading has zero cost penalty.
- No new infrastructure required (vs. MCP server, which adds a separate process + auth layer).
- Follows the existing pattern already used for doc contents and recent emails.
- An MCP server would be worth building if data volume exceeded ~10K tokens or required per-query dynamic retrieval (e.g., semantic search over conversation history). We're not there yet.

If conversation history is later added to context, the plan is: load the most recent 10 messages from `conversation_history/` and include them in the prompt alongside roles/prefs.
