aude """
Hana's knowledge system — all note and question-queue access goes through here.
No other module writes to hana_notes or hana_question_queue directly.
"""

import os
import re
from datetime import datetime, timedelta, timezone

from google.cloud import firestore as _firestore

_PROJECT = 'mediationmate'
_NOTES_COLLECTION = 'hana_notes'
_QUEUE_DOC = 'queue'
_QUEUE_COLLECTION = 'hana_question_queue'


def _db():
    return _firestore.Client(project=_PROJECT)


def _slugify(topic: str) -> str:
    slug = topic.strip().lower()
    slug = re.sub(r'[^a-z0-9]+', '-', slug)
    return slug.strip('-')


def _now():
    return datetime.now(timezone.utc)


def _gemini_merge(existing_content: str, new_content: str, topic: str) -> str:
    """Use Gemini to intelligently merge existing note content with new information."""
    try:
        import google.generativeai as genai
        # Use an isolated client — do NOT call genai.configure() here, as it mutates
        # global state and can corrupt any parent Gemini chat session calling this tool.
        client = genai.GenerativeModel(
            'gemini-2.5-flash',
            client_options={"api_key": os.environ.get("GOOGLE_API_KEY")},
        )
        prompt = f"""You are merging two sets of notes about "{topic}" written by Hana, a household assistant.

EXISTING NOTE:
{existing_content}

NEW INFORMATION TO INCORPORATE:
{new_content}

Merge these into a single cohesive note. Rules:
- Keep all facts from the existing note that are still valid
- Add new facts from the new information
- Update any facts that have changed (use the newer version)
- Do not duplicate information
- Write as direct factual statements — never narrate the note's existence
  Right: "Dan is allergic to shellfish and gluten."
  Wrong: "My note about Dan's allergies is that he's allergic to shellfish and gluten."
- Do not mention that this is a merge — just write the facts naturally
- Keep it reasonably concise

Return only the merged note text, nothing else."""
        response = client.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        print(f"[memory] gemini merge failed: {e}")
        # Fallback: append with separator
        return existing_content.rstrip() + "\n\n" + new_content.strip()


def save_note(topic: str, content: str) -> dict:
    """Create or update a note for the given topic.

    If a note already exists, merges new content intelligently — appends new
    facts, updates changed ones, avoids duplication. Topic is freeform.
    Returns {"status": "ok", "topic": topic, "action": "created" | "updated"}.
    """
    db = _db()
    slug = _slugify(topic)
    ref = db.collection(_NOTES_COLLECTION).document(slug)
    doc = ref.get()
    now = _now()

    if doc.exists:
        data = doc.to_dict()
        existing_content = data.get('content', '')
        existing_updated_at = data.get('updated_at')
        merged = _gemini_merge(existing_content, content, topic)
        ref.update({
            'content': merged,
            'updated_at': now,
            'previous_content': existing_content,
            'previous_updated_at': existing_updated_at,
        })
        return {"status": "ok", "topic": topic, "action": "updated"}
    else:
        ref.set({
            'topic': topic,
            'content': content,
            'created_at': now,
            'updated_at': now,
            'created_by': 'hana',
        })
        return {"status": "ok", "topic": topic, "action": "created"}


def revert_note(topic: str) -> dict:
    """Swap current note content with its previous version (one-step undo).

    Idempotent — calling twice returns to the original state.
    Returns {"status": "ok"} or {"status": "no_previous_version"} or {"status": "not_found"}.
    """
    db = _db()
    slug = _slugify(topic)
    ref = db.collection(_NOTES_COLLECTION).document(slug)
    doc = ref.get()
    if not doc.exists:
        return {"status": "not_found"}
    data = doc.to_dict()
    previous_content = data.get('previous_content')
    if not previous_content:
        return {"status": "no_previous_version"}
    previous_updated_at = data.get('previous_updated_at')
    current_content = data.get('content', '')
    current_updated_at = data.get('updated_at')
    now = _now()
    ref.update({
        'content': previous_content,
        'updated_at': now,
        'previous_content': current_content,
        'previous_updated_at': current_updated_at,
    })
    return {"status": "ok", "topic": topic, "action": "reverted"}


def get_note(topic: str) -> dict | None:
    """Retrieve a note by topic name (fuzzy match — 'kids' will find 'kids routines').

    Returns the full note dict or None if not found.
    """
    db = _db()
    query = topic.strip().lower()

    # Try exact slug first
    slug = _slugify(topic)
    doc = db.collection(_NOTES_COLLECTION).document(slug).get()
    if doc.exists:
        return doc.to_dict()

    # Fuzzy: scan all docs for a topic that contains or is contained by the query
    for doc in db.collection(_NOTES_COLLECTION).stream():
        data = doc.to_dict()
        stored_topic = data.get('topic', '').lower()
        if query in stored_topic or stored_topic in query:
            return data

    return None


def list_notes() -> list[dict]:
    """Return all notes sorted by updated_at descending."""
    db = _db()
    docs = db.collection(_NOTES_COLLECTION).order_by(
        'updated_at', direction=_firestore.Query.DESCENDING
    ).stream()
    results = []
    for doc in docs:
        data = doc.to_dict()
        slug = doc.id
        updated = data.get('updated_at')
        if hasattr(updated, 'isoformat'):
            updated_str = updated.isoformat()
        else:
            updated_str = str(updated) if updated else ''
        results.append({
            'slug': slug,
            'topic': data.get('topic', ''),
            'content': data.get('content', ''),
            'updated_at': updated_str,
        })
    return results


def search_memory(query: str) -> list[dict]:
    """Return notes relevant to the query (up to 3), each truncated to 1000 chars.

    Matches if any word in the query appears in the topic name or content.
    """
    db = _db()
    words = [w.lower() for w in query.strip().split() if len(w) > 1]
    if not words:
        return []

    scored = []
    for doc in db.collection(_NOTES_COLLECTION).stream():
        data = doc.to_dict()
        topic_lower = data.get('topic', '').lower()
        content_lower = data.get('content', '').lower()
        haystack = topic_lower + ' ' + content_lower
        score = sum(1 for w in words if w in haystack)
        if score > 0:
            # Topic matches count double
            topic_score = sum(2 for w in words if w in topic_lower)
            scored.append((score + topic_score, data))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for _, data in scored[:3]:
        updated = data.get('updated_at')
        results.append({
            'topic': data.get('topic', ''),
            'content': data.get('content', '')[:1000],
            'updated_at': updated.isoformat() if hasattr(updated, 'isoformat') else str(updated or ''),
        })
    return results


def queue_question(question: str, context: str, priority: str = "normal") -> dict:
    """Queue a question for Hana to ask the user.

    Max 1 queued question at a time. Replaces existing only if new priority is
    higher OR existing is older than 7 days. Returns {"status": "ok"|"skipped"}.
    """
    db = _db()
    ref = db.collection(_QUEUE_COLLECTION).document(_QUEUE_DOC)
    doc = ref.get()
    now = _now()

    if doc.exists:
        existing = doc.to_dict()
        existing_priority = existing.get('priority', 'normal')
        queued_at = existing.get('queued_at')

        # Replace if new priority is higher
        priority_rank = {'high': 1, 'normal': 0}
        new_rank = priority_rank.get(priority, 0)
        old_rank = priority_rank.get(existing_priority, 0)

        # Replace if existing is older than 7 days
        is_stale = False
        if queued_at:
            if hasattr(queued_at, 'replace'):
                if queued_at.tzinfo is None:
                    queued_at = queued_at.replace(tzinfo=timezone.utc)
            is_stale = (now - queued_at).days >= 7

        if new_rank <= old_rank and not is_stale:
            return {"status": "skipped", "reason": "lower_priority_and_not_stale"}

    ref.set({
        'question': question,
        'context': context,
        'priority': priority,
        'queued_at': now,
        'last_pulsed_at': None,
        'snoozed_until': None,
    })
    return {"status": "ok", "reason": "queued"}


def get_queued_question() -> dict | None:
    """Return the current queued question if one exists and is not snoozed."""
    db = _db()
    doc = db.collection(_QUEUE_COLLECTION).document(_QUEUE_DOC).get()
    if not doc.exists:
        return None

    data = doc.to_dict()
    if not data.get('question'):
        return None

    snoozed_until = data.get('snoozed_until')
    if snoozed_until:
        if hasattr(snoozed_until, 'replace') and snoozed_until.tzinfo is None:
            snoozed_until = snoozed_until.replace(tzinfo=timezone.utc)
        if snoozed_until > _now():
            return None

    return data


def snooze_question(days: int = 3) -> dict:
    """Snooze the current queued question for the given number of days."""
    db = _db()
    ref = db.collection(_QUEUE_COLLECTION).document(_QUEUE_DOC)
    doc = ref.get()
    if not doc.exists:
        return {"status": "no_question"}
    ref.update({'snoozed_until': _now() + timedelta(days=days)})
    return {"status": "ok", "snoozed_days": days}


def clear_question() -> dict:
    """Remove the current queued question. Called when Hana gets her answer."""
    db = _db()
    ref = db.collection(_QUEUE_COLLECTION).document(_QUEUE_DOC)
    if ref.get().exists:
        ref.delete()
    return {"status": "ok"}


def delete_note(topic: str) -> dict:
    """Delete a note by topic name or slug. Called from user-facing delete action."""
    db = _db()
    slug = _slugify(topic)
    ref = db.collection(_NOTES_COLLECTION).document(slug)
    if ref.get().exists:
        ref.delete()
        return {"status": "ok", "deleted": slug}

    # Try scanning for a match
    for doc in db.collection(_NOTES_COLLECTION).stream():
        if doc.id == slug or _slugify(doc.to_dict().get('topic', '')) == slug:
            doc.reference.delete()
            return {"status": "ok", "deleted": doc.id}

    return {"status": "not_found", "slug": slug}
