import threading
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from google.cloud import firestore as _firestore

_PROJECT = 'mediationmate'

_NAME_MAP = {
    'dcjohnston1@gmail.com': 'Dan',
    'emily.osteen.johnston@gmail.com': 'Emily',
}

_ACTION_LABELS = {
    'email_dismissed':            ('dismissed',   'email',               'emails'),
    'email_reviewed':             ('reviewed',    'email',               'emails'),
    'task_completed':             ('completed',   'task',                'tasks'),
    'task_added':                 ('added',       'task',                'tasks'),
    'task_swiped_to_calendar':    ('added',       'task to calendar',    'tasks to calendar'),
    'task_reassigned':            ('reassigned',  'task',                'tasks'),
    'proposal_accepted':          ('accepted',    'proposal',            'proposals'),
    'proposal_dismissed':         ('dismissed',   'proposal',            'proposals'),
    'calendar_event_added':       ('added',       'calendar event',      'calendar events'),
    'calendar_event_edited':      ('edited',      'calendar event',      'calendar events'),
    'calendar_event_deleted':     ('deleted',     'calendar event',      'calendar events'),
    'sender_filter_added':        ('added',       'sender filter',       'sender filters'),
    'sender_filter_removed':      ('removed',     'sender filter',       'sender filters'),
    'keyword_filter_added':       ('added',       'keyword filter',      'keyword filters'),
    'keyword_filter_removed':     ('removed',     'keyword filter',      'keyword filters'),
    'exclude_keyword_filter_added':   ('added',   'exclude-keyword filter',  'exclude-keyword filters'),
    'exclude_keyword_filter_removed': ('removed', 'exclude-keyword filter',  'exclude-keyword filters'),
    'profile_updated':            ('updated',     'profile',             'profiles'),
}


def log_action(user: str, action_type: str, metadata: dict = None,
               actor: str = 'user', reasoning: str = None):
    """Fire-and-forget write to Firestore user_actions collection."""
    def _write():
        try:
            db = _firestore.Client(project=_PROJECT)
            doc = {
                'user': user or 'unknown',
                'action_type': action_type,
                'actor': actor,
                'timestamp': datetime.now(timezone.utc),
            }
            if metadata:
                doc.update(metadata)
            if reasoning:
                doc['reasoning'] = reasoning
            db.collection('user_actions').add(doc)
        except Exception as e:
            print(f'[logger] log_action failed: {e}')
    threading.Thread(target=_write, daemon=True).start()


def log_gemini_decision(action_type: str, input_context: str, context_consulted: str,
                        decision_made: str, reasoning: str, confidence: str = 'medium',
                        user_email: str = None):
    """Fire-and-forget write to Firestore gemini_decisions collection."""
    def _write():
        try:
            db = _firestore.Client(project=_PROJECT)
            doc = {
                'action_type': action_type,
                'input_context': input_context,
                'context_consulted': context_consulted,
                'decision_made': decision_made,
                'reasoning': reasoning,
                'confidence': confidence,
                'actor': 'gemini',
                'timestamp': datetime.now(timezone.utc),
            }
            if user_email:
                doc['user_email'] = user_email
            db.collection('gemini_decisions').add(doc)
        except Exception as e:
            print(f'[logger] log_gemini_decision failed: {e}')
    threading.Thread(target=_write, daemon=True).start()


def get_recent_decisions(user_email=None, action_type=None, limit=20, since=None):
    """Return recent Gemini decisions from Firestore gemini_decisions collection."""
    db = _firestore.Client(project=_PROJECT)

    if since:
        since_dt = datetime.fromisoformat(since.replace('Z', '+00:00')) if isinstance(since, str) else since
    else:
        since_dt = datetime.now(timezone.utc) - timedelta(days=7)

    q = (db.collection('gemini_decisions')
           .where('timestamp', '>=', since_dt)
           .order_by('timestamp', direction=_firestore.Query.DESCENDING))

    decisions = []
    for doc in q.stream():
        d = doc.to_dict()
        d['id'] = doc.id
        if user_email and d.get('user_email') != user_email:
            continue
        if action_type and d.get('action_type') != action_type:
            continue
        if 'timestamp' in d:
            d['timestamp'] = d['timestamp'].isoformat()
        decisions.append(d)
        if len(decisions) >= limit:
            break
    return decisions


def get_recent_actions(user=None, action_type=None, limit=20, since=None):
    """Return a list of recent actions from Firestore, filtered in Python."""
    db = _firestore.Client(project=_PROJECT)

    if since:
        since_dt = datetime.fromisoformat(since.replace('Z', '+00:00')) if isinstance(since, str) else since
    else:
        since_dt = datetime.now(timezone.utc) - timedelta(days=7)

    q = (db.collection('user_actions')
           .where('timestamp', '>=', since_dt)
           .order_by('timestamp', direction=_firestore.Query.DESCENDING))

    actions = []
    for doc in q.stream():
        d = doc.to_dict()
        d['id'] = doc.id
        if user and d.get('user') != user:
            continue
        if action_type and d.get('action_type') != action_type:
            continue
        if 'timestamp' in d:
            d['timestamp'] = d['timestamp'].isoformat()
        actions.append(d)
        if len(actions) >= limit:
            break
    return actions


def get_action_summary(days=7):
    """Return a short human-readable paragraph summarising recent household activity."""
    try:
        db = _firestore.Client(project=_PROJECT)
        since_dt = datetime.now(timezone.utc) - timedelta(days=days)
        q = (db.collection('user_actions')
               .where('timestamp', '>=', since_dt)
               .order_by('timestamp', direction=_firestore.Query.DESCENDING))

        counts = defaultdict(lambda: defaultdict(int))
        for doc in q.stream():
            d = doc.to_dict()
            u = d.get('user', 'unknown')
            at = d.get('action_type', 'unknown')
            counts[u][at] += 1

        if not counts:
            return f'No activity logged in the last {days} days.'

        sentences = []
        for user_email in sorted(counts):
            name = _NAME_MAP.get(user_email, user_email)
            type_counts = counts[user_email]
            parts = []
            for at, n in type_counts.items():
                if at in _ACTION_LABELS:
                    verb, singular, plural = _ACTION_LABELS[at]
                    noun = singular if n == 1 else plural
                    parts.append(f'{verb} {n} {noun}')
            if parts:
                sentences.append(f'{name} has {", ".join(parts)} in the last {days} days.')

        return ' '.join(sentences) if sentences else f'No significant activity in the last {days} days.'
    except Exception as e:
        print(f'[logger] get_action_summary failed: {e}')
        return ''
