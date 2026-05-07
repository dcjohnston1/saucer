import os
import threading
from datetime import datetime, timezone, timedelta
from google.cloud import firestore


def _get_db():
    return firestore.Client(project='mediationmate')


def log_conversation(user_email: str, message: str, bot_response: str, conversation_id: str):
    try:
        db = _get_db()
        db.collection('conversation_history').add({
            'user_email': user_email,
            'message': message,
            'bot_response': bot_response,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'conversation_id': conversation_id,
            'archived': False,
            'summary': None,
        })
        _enforce_cap(db, user_email)
    except Exception as e:
        print(f"[conversation_history] log error: {e}")


def _enforce_cap(db, user_email, cap=50):
    docs = list(db.collection('conversation_history').where('user_email', '==', user_email).stream())
    if len(docs) <= cap:
        return
    docs.sort(key=lambda d: d.to_dict().get('timestamp', ''), reverse=True)
    for doc in docs[cap:]:
        try:
            doc.reference.delete()
        except Exception:
            pass


def get_recent_history(user_email: str, limit: int = 5) -> list:
    try:
        db = _get_db()
        docs = list(db.collection('conversation_history').where('user_email', '==', user_email).stream())
        convos = [d.to_dict() for d in docs]
        convos.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return list(reversed(convos[:limit]))
    except Exception as e:
        print(f"[conversation_history] get_recent error: {e}")
        return []


def search_history(user_email: str, keyword: str, days_back: int = 30, limit: int = 5) -> list:
    try:
        db = _get_db()
        since = (datetime.now(timezone.utc) - timedelta(days=days_back)).isoformat()
        docs = list(db.collection('conversation_history').where('user_email', '==', user_email).stream())
        kw = keyword.lower()
        matches = []
        for doc in docs:
            d = doc.to_dict()
            if d.get('timestamp', '') < since:
                continue
            text = ' '.join([
                d.get('message', ''),
                d.get('bot_response', '') if not d.get('archived') else '',
                d.get('summary', '') or '',
            ]).lower()
            if kw in text:
                matches.append(d)
        matches.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return matches[:limit]
    except Exception as e:
        print(f"[conversation_history] search error: {e}")
        return []


def summarize_old_conversations() -> int:
    import google.generativeai as genai
    genai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
    model = genai.GenerativeModel('gemini-2.5-flash')

    db = _get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    docs = list(db.collection('conversation_history').stream())

    count = 0
    for doc in docs:
        d = doc.to_dict()
        if d.get('archived'):
            continue
        if d.get('timestamp', '') >= cutoff:
            continue
        message = d.get('message', '')
        bot_response = d.get('bot_response', '')
        if not message and not bot_response:
            doc.reference.update({'archived': True})
            continue
        text = f"User: {message}\nAssistant: {bot_response}"
        try:
            response = model.generate_content(
                f"Summarize this conversation in 1-2 sentences focusing on decisions and actions taken:\n\n{text}"
            )
            doc.reference.update({
                'summary': response.text.strip(),
                'archived': True,
            })
            count += 1
        except Exception as e:
            print(f"[conversation_history] summarize error for {doc.id}: {e}")

    return count
