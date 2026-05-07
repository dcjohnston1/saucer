import json
import uuid
import os
import google.generativeai as genai

genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))


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
    "date_expression": "<natural language date if mentioned, e.g. 'May 15' or 'this month', or null>"
  }
]

If no action items are found, return [].

Emails to review:

""" + "\n\n---\n\n".join(blocks)

    try:
        model = genai.GenerativeModel(
            model_name='gemini-2.5-flash',
            generation_config={'response_mime_type': 'application/json'}
        )
        response = model.generate_content(prompt)
        items = json.loads(response.text)

        result = {}
        for item in items:
            eid = item.get('email_id')
            if not eid:
                continue
            result.setdefault(eid, []).append({
                'id': str(uuid.uuid4()),
                'title': item.get('title', ''),
                'notes': item.get('notes') or '',
                'date_expression': item.get('date_expression') or '',
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
        body = (e.get('body') or e.get('snippet', ''))[:600]
        blocks.append(f"EMAIL_ID: {e['id']}\nSubject: {e['subject']}\nFrom: {e['sender']}\nBody: {body}")

    prompt = """Summarize each email in up to 140 characters. Lead with the main point or action required — not who sent it. Be specific: mention dates, amounts, deadlines, or events by name. Never start with "Email from" or the sender's name.

Bad: "Email from Atlanta Area Council, Scouting America"
Good: "Scouts baseball game June 3 at 6pm — permission slip due May 20"

Return ONLY valid JSON: [{"email_id": "<id>", "summary": "<summary>"}]

Emails:

""" + "\n\n---\n\n".join(blocks)

    try:
        model = genai.GenerativeModel(
            model_name='gemini-2.5-flash',
            generation_config={'response_mime_type': 'application/json'}
        )
        response = model.generate_content(prompt)
        items = json.loads(response.text)
        return {item['email_id']: item['summary'][:140] for item in items if 'email_id' in item and 'summary' in item}
    except Exception as e:
        print(f"Summarize error: {e}")
        return {}
