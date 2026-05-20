import json
import re
import uuid
import os
from google import genai
from google.genai import types as genai_types

# Lazy client — instantiated on first use so the module can be imported even
# when GOOGLE_API_KEY is not set (e.g. in test environments or on import checks).
_genai_client = None


def _get_client():
    global _genai_client
    if _genai_client is None:
        _genai_client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))
    return _genai_client

# Shared verdict rules injected into both evaluate_email_intent() and
# batch_evaluate_emails_intent(). Update here to change behavior in both paths.
_INTENT_VERDICT_RULES = (
    'Verdict rules — apply in this order:\n'
    '1. Content clearly matches intent → "permitted". Reason: one sentence naming the specific intent category.\n'
    '   Special case: if the sender and recipient are the same address (a self-email / note-to-self), '
    '   and the body contains a list of tasks, to-dos, action items, reminders, or structured notes, '
    '   treat it as "permitted" regardless of the intent description. '
    '   A person emailing themselves a task list is the clearest possible household action signal. '
    '   Only block a self-email if it has an empty body, a single word subject and no substantive content, '
    '   or is clearly a test message (e.g. subject "test", body "test" or blank).\n'
    '2. Content genuinely ambiguous — email mentions a relevant topic but primary purpose is unclear or mixed → "uncertain". '
    'Use sparingly; only when you truly cannot tell. '
    'Example: a school email that also promotes a fundraiser. '
    'Reason: one specific sentence naming the sender, topic, and the exact tension. '
    'Good: "City of Decatur email promoting a summer concert series — could relate to family activities but appears to be a general public event." '
    'Bad: "Not sure if this matches." "Could be relevant."\n'
    '3. Content clearly does not match intent → "blocked". '
    'Includes ALL promotional/retail/marketing emails, professional newsletters, and industry digests, even from trusted senders. '
    'When in doubt between "uncertain" and "blocked" for off-topic content: choose "blocked." '
    'Reason: one sentence naming what the email was about and which intent it failed to match.\n'
    '\n'
    'matched_topic field — only set when verdict is "permitted". '
    'Echo the user\'s own phrasing from the intent description that this email matched — '
    'e.g. if the user wrote "school activities, Cub Scouts, permission slips" and the email is about a Cub Scouts meeting, '
    'matched_topic must be "Cub Scouts" (their exact phrase, not "scouting" or "kids activities"). '
    'Keep it short — ideally 1–3 words from the user\'s text. '
    'For "uncertain" and "blocked" verdicts, set matched_topic to null.\n'
)


def _addr(sender_str: str) -> str:
    m = re.search(r'<([^>]+)>', sender_str)
    return m.group(1).strip().lower() if m else sender_str.strip().lower()


def evaluate_email_intent(email, email_intent, blocked_senders=None, permitted_senders=None, excluded_keywords=None):
    """Evaluate an email against the household intent description.

    Returns dict: {verdict: 'permitted'|'uncertain'|'blocked', confidence: float, reason: str}
    Priority order: blocked sender > excluded keywords > content-based intent check.
    Permitted sender status prevents blocking on identity alone; content evaluation applies normally.
    """
    sender_addr = _addr(email.get('sender', ''))
    blocked_set = {s.lower() for s in (blocked_senders or [])}
    permitted_set = {s.lower() for s in (permitted_senders or [])}
    excl_lower = [kw.lower() for kw in (excluded_keywords or [])]

    if sender_addr in blocked_set:
        return {'verdict': 'blocked', 'confidence': 1.0, 'reason': 'Sender is on the blocked list'}

    if excl_lower:
        subject_lower = email.get('subject', '').lower()
        snippet_lower = (email.get('body') or email.get('snippet', ''))[:500].lower()
        if any(kw in subject_lower or kw in snippet_lower for kw in excl_lower):
            return {'verdict': 'blocked', 'confidence': 1.0, 'reason': 'Matches excluded subject or keyword'}

    if not email_intent:
        if sender_addr in permitted_set:
            return {'verdict': 'permitted', 'confidence': 1.0, 'reason': 'Sender is on the permitted list'}
        return {'verdict': 'permitted', 'confidence': 0.5, 'reason': 'No intent description set'}

    body = (email.get('body') or email.get('snippet', ''))[:1000]
    subject = email.get('subject', '')
    sender = email.get('sender', '')

    prompt = (
        f'The user has described the emails that belong in their space as: "{email_intent}"\n\n'
        f'Evaluate this email and return a JSON object:\n'
        f'{{"verdict": "permitted" | "uncertain" | "blocked", "confidence": 0.0-1.0, "reason": "one specific sentence", "matched_topic": "<short phrase from user intent or null>"}}\n\n'
        f'SELF-EMAIL RULE (highest priority, checked first): If the From address and the To/recipient address '
        f'are the same (the person emailed themselves), AND the body contains tasks, to-dos, action items, '
        f'reminders, or structured notes, verdict MUST be "permitted". '
        f'A self-email task list is the strongest possible household action signal — never block it. '
        f'Only block a self-email if it has an empty body or is clearly a test (e.g. subject "test", body blank or "test").\n\n'
        f'PERMITTED SENDER RULE: A permitted sender means do not block based on sender identity alone. '
        f'It does NOT mean default to "uncertain" when content fails the intent test. '
        f'Evaluate ALL emails on content — a data viz newsletter, retail promotion, or professional digest is "blocked" even if sent by a household member or trusted address. '
        f'Exception: self-emails (sender == recipient) with action-item content follow the SELF-EMAIL RULE above.\n\n'
        + _INTENT_VERDICT_RULES +
        f'\nEmail:\nFrom: {sender}\nSubject: {subject}\nBody: {body}'
    )

    try:
        response = _get_client().models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=genai_types.GenerateContentConfig(response_mime_type='application/json'),
        )
        result = json.loads(response.text)
        verdict = result.get('verdict', 'uncertain')
        if verdict not in ('permitted', 'uncertain', 'blocked'):
            verdict = 'uncertain'
        matched_topic = result.get('matched_topic') if verdict == 'permitted' else None
        if isinstance(matched_topic, str):
            matched_topic = matched_topic.strip() or None
        else:
            matched_topic = None
        return {
            'verdict': verdict,
            'confidence': float(result.get('confidence', 0.5)),
            'reason': result.get('reason', ''),
            'matched_topic': matched_topic,
        }
    except Exception as e:
        print(f"Intent eval error: {e}")
        return {'verdict': 'uncertain', 'confidence': 0.5, 'reason': 'Evaluation error — showing as uncertain', 'matched_topic': None}


def batch_evaluate_emails_intent(emails, email_intent, excluded_keywords=None, blocked_senders=None, permitted_senders=None, keyword_filters=None):
    """Batch-evaluate emails against intent using up to 20 emails per Gemini call.

    Returns dict: email_id -> {verdict, reason}
    Priority order: blocked sender > excluded keywords > permitted sender > keyword filter > content-based intent check.
    Permitted senders and keyword-matched emails short-circuit Gemini evaluation entirely.
    """
    results = {}
    blocked_set = {s.lower() for s in (blocked_senders or [])}
    permitted_set = {s.lower() for s in (permitted_senders or [])}
    excl_lower = [kw.lower() for kw in (excluded_keywords or [])]
    keyword_originals = list(keyword_filters or [])
    kw_lower = [kw.lower() for kw in keyword_originals]
    excl_str = ', '.join(excl_lower) if excl_lower else 'none'

    to_evaluate = []
    for e in emails:
        email_id = e.get('id', '')
        sender_addr = _addr(e.get('sender', ''))
        subject_lower = e.get('subject', '').lower()
        snippet_lower = (e.get('body') or e.get('snippet', ''))[:500].lower()

        if sender_addr in blocked_set:
            results[email_id] = {'verdict': 'blocked', 'reason': 'Sender is on the blocked list'}
            continue

        if excl_lower and any(kw in subject_lower or kw in snippet_lower for kw in excl_lower):
            results[email_id] = {'verdict': 'blocked', 'reason': 'Matches excluded subject or keyword'}
            continue

        if sender_addr in permitted_set:
            # Explicit sender allowlist — authoritative, skip Gemini.
            results[email_id] = {'verdict': 'permitted', 'reason': 'Sender is on the permitted list'}
            continue

        if kw_lower:
            haystack = ' '.join([
                e.get('subject', ''),
                (e.get('body', '') or e.get('snippet', ''))[:2000],
            ]).lower()
            matched_kw = next((orig for orig, low in zip(keyword_originals, kw_lower) if low in haystack), None)
            if matched_kw:
                results[email_id] = {
                    'verdict': 'permitted',
                    'reason': 'Matches user keyword filter',
                    'matched_topic': matched_kw,
                }
                continue

        if not email_intent:
            results[email_id] = {'verdict': 'permitted', 'reason': 'No intent description set'}
            continue

        to_evaluate.append(e)

    if not to_evaluate:
        return results

    BATCH_SIZE = 20
    for i in range(0, len(to_evaluate), BATCH_SIZE):
        batch = to_evaluate[i:i + BATCH_SIZE]
        lines = []
        for idx, e in enumerate(batch, 1):
            sender = e.get('sender', '')
            subject = e.get('subject', '')
            snippet = (e.get('body') or e.get('snippet', ''))[:300]
            lines.append(f"{idx}. From: {sender} | Subject: {subject} | Snippet: {snippet}")

        prompt = (
            f'The household\'s email intent is: "{email_intent}"\n'
            f'Excluded subjects/keywords (always block, even from permitted senders): {excl_str}\n\n'
            f'Evaluate each of the following emails and return ONLY a JSON array of verdict objects in the same order.\n'
            f'Each object: {{"verdict": "permitted"|"uncertain"|"blocked", "reason": "one specific sentence", "matched_topic": "<short phrase from user intent or null>"}}\n\n'
            f'PERMITTED SENDER RULE: A permitted sender means do not block based on sender identity alone. '
            f'It does NOT mean default to "uncertain" when content fails the intent test. '
            f'Evaluate ALL emails on content — a data viz newsletter, retail promotion, or professional digest is "blocked" even if sent by a household member or trusted address.\n\n'
            + _INTENT_VERDICT_RULES +
            f'\nEmails:\n' + '\n'.join(lines)
        )

        try:
            response = _get_client().models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt,
                config=genai_types.GenerateContentConfig(response_mime_type='application/json'),
            )
            verdicts = json.loads(response.text)
            for j, e in enumerate(batch):
                email_id = e.get('id', '')
                sender_addr = _addr(e.get('sender', ''))
                if j < len(verdicts):
                    v = verdicts[j]
                    verdict = v.get('verdict', 'uncertain')
                    if verdict not in ('permitted', 'uncertain', 'blocked'):
                        verdict = 'uncertain'
                    matched_topic = v.get('matched_topic') if verdict == 'permitted' else None
                    if isinstance(matched_topic, str):
                        matched_topic = matched_topic.strip() or None
                    else:
                        matched_topic = None
                    results[email_id] = {
                        'verdict': verdict,
                        'reason': v.get('reason', ''),
                        'matched_topic': matched_topic,
                    }
                else:
                    results[email_id] = {'verdict': 'uncertain', 'reason': 'Evaluation incomplete'}
        except Exception as ex:
            print(f"[batch_eval] batch {i} error: {ex}")
            for e in batch:
                results[e.get('id', '')] = {'verdict': 'uncertain', 'reason': 'Evaluation error — showing as uncertain'}

    return results


def extract_topic_noun_phrase(email):
    """Extract a 2-4 word noun phrase from an email for the dismissal reason UI."""
    subject = email.get('subject', '')
    body = (email.get('body') or email.get('snippet', ''))[:400]
    prompt = (
        'In 2-4 words, what is the main topic or service mentioned in this email? '
        'Return only the lowercase noun phrase. Examples: "swim school", "piano lessons", "dental cleanings".\n\n'
        f'Subject: {subject}\nBody preview: {body[:300]}'
    )
    try:
        response = _get_client().models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        return response.text.strip().lower()[:60]
    except Exception as e:
        print(f"Topic extraction error: {e}")
        return 'this type of email'


def scan_emails_for_todos(emails):
    """
    Scan a list of email objects for household action items.
    Returns dict keyed by email_id -> list of proposal dicts.
    """
    if not emails:
        return {}

    blocks = []
    for e in emails:
        body = (e.get('body') or e.get('snippet', ''))[:2000]
        block = f"EMAIL_ID: {e['id']}\nFrom: {e['sender']}\nSubject: {e['subject']}\nBody: {body}"
        for a in e.get('attachments', []):
            if a.get('extracted_text'):
                block += f"\nAttachment ({a['filename']}): {a['extracted_text'][:2000]}"
        blocks.append(block)

    prompt = """You are a household assistant. Review the following emails and identify genuine action items for the household. Cast a wide net — include: bills to pay, appointments to schedule, renewals, school events, service reminders, permission slips, RSVPs, follow-ups, items to bring or wear on a specific day (spirit days, dress-up days, show-and-share), deadlines to sign up for something, testing dates that require preparation, and any other task that requires the family to do or remember something. If it requires a person to act or remember, flag it. Skip pure marketing, generic newsletters with no specific ask, and receipts for things already completed.

For each action item found, return a JSON array. Return ONLY valid JSON, no other text.

Format:
[
  {
    "email_id": "<the EMAIL_ID value from the email>",
    "title": "<concise action item, under 60 chars>",
    "notes": "<brief context, or null>",
    "date_expression": "<natural language date if mentioned, e.g. 'May 15' or 'this month', or null>",
    "source_spans": ["<verbatim sentence or short phrase from the email body that this to-do is based on>"]
  }
]

source_spans must be exact substrings copied verbatim from the email body — do not paraphrase. Include 1-2 spans per item maximum.

If no action items are found, return [].

Emails to review:

""" + "\n\n---\n\n".join(blocks)

    try:
        response = _get_client().models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=genai_types.GenerateContentConfig(response_mime_type='application/json'),
        )
        items = json.loads(response.text)

        result = {}
        for item in items:
            eid = item.get('email_id')
            if not eid:
                continue
            spans = item.get('source_spans')
            if not isinstance(spans, list):
                spans = []
            result.setdefault(eid, []).append({
                'id': str(uuid.uuid4()),
                'title': item.get('title', ''),
                'notes': item.get('notes') or '',
                'date_expression': item.get('date_expression') or '',
                'source_spans': spans,
                'dismissed': False,
                'accepted': False,
            })
        return result
    except Exception as e:
        print(f"Email scan error: {e}")
        return {}


def summarize_emails(emails):
    """Generate max-140-char summaries for a list of emails. Returns dict email_id -> summary."""
    if not emails:
        return {}

    blocks = []
    for e in emails:
        body = (e.get('body') or e.get('snippet', ''))[:1500]
        if not body.strip():
            print(f"[summarize] email {e.get('id')} has empty body — skipping")
            continue
        blocks.append(f"EMAIL_ID: {e['id']}\nSubject: {e['subject']}\nFrom: {e['sender']}\nBody: {body}")

    if not blocks:
        return {}

    prompt = """Summarize each email in up to 140 characters. Lead with the main point or action required — not who sent it. Be specific: mention dates, amounts, deadlines, or events by name. Never start with "Email from" or the sender's name.

Bad: "Email from Atlanta Area Council, Scouting America"
Good: "Scouts baseball game June 3 at 6pm — permission slip due May 20"

Return ONLY valid JSON: [{"email_id": "<id>", "summary": "<summary>"}]

Emails:

""" + "\n\n---\n\n".join(blocks)

    try:
        response = _get_client().models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=genai_types.GenerateContentConfig(response_mime_type='application/json'),
        )
        raw = response.text
        print(f"[summarize] raw response (first 200 chars): {raw[:200]}")
        items = json.loads(raw)
        result = {}
        for item in items:
            if 'email_id' in item and 'summary' in item:
                s = item['summary']
                if s and len(s) >= 10:
                    result[item['email_id']] = s[:140]
                else:
                    print(f"[summarize] email {item.get('email_id')} got unusable summary: {repr(s)}")
        return result
    except Exception as e:
        print(f"[summarize] error generating summaries: {e}")
        import traceback; traceback.print_exc()
        return {}
