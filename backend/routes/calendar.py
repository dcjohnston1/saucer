from flask import Blueprint, request, jsonify
from logger import log_action

calendar_bp = Blueprint('calendar', __name__)


def _req_user(data=None):
    if data:
        v = data.get('user', '')
        if v:
            return v
    return request.args.get('user', 'unknown')


@calendar_bp.route('/calendar/events', methods=['GET'])
def get_calendar_events():
    from gcalendar import get_events
    start = request.args.get('start')
    end = request.args.get('end')
    if not start or not end:
        return jsonify({'error': 'Missing start or end'}), 400
    try:
        events = get_events(start, end)
        return jsonify({'events': events})
    except Exception as e:
        import traceback
        print(f"[calendar/events] get_events raised: {e}")
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@calendar_bp.route('/calendar/events', methods=['POST'])
def create_calendar_event():
    from gcalendar import create_event_direct
    data = request.get_json()
    title = (data.get('title') or '').strip()
    date_str = data.get('date')
    time_str = data.get('time') or None
    notes = data.get('notes') or None
    if not title or not date_str:
        return jsonify({'error': 'Missing title or date'}), 400
    try:
        event_id = create_event_direct(title, date_str, time_str, notes=notes)
        user = _req_user(data)
        log_action(user, 'calendar_event_added', {'title': title, 'date': date_str}, actor='user')
        return jsonify({'ok': True, 'id': event_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@calendar_bp.route('/calendar/events/<event_id>', methods=['PUT'])
def update_calendar_event(event_id):
    from gcalendar import update_event
    data = request.get_json()
    try:
        update_event(
            event_id,
            title=data.get('title') or None,
            start_date=data.get('start_date') or None,
            end_date=data.get('end_date') or None,
            time_str=data.get('time') or None,
            notes=data.get('notes'),
        )
        user = _req_user(data)
        log_action(user, 'calendar_event_edited', {'event_id': event_id, 'title': data.get('title')}, actor='user')
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@calendar_bp.route('/calendar/events/<event_id>/assignee', methods=['PATCH'])
def patch_calendar_event_assignee(event_id):
    from gcalendar import update_event_assignee
    data = request.get_json() or {}
    assignee_label = data.get('assignee_label')
    try:
        update_event_assignee(event_id, assignee_label)
        user = _req_user(data)
        log_action(user, 'calendar_event_edited',
                   {'event_id': event_id, 'assignee_label': assignee_label}, actor='user')
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@calendar_bp.route('/calendar/events/<event_id>', methods=['DELETE'])
def delete_calendar_event(event_id):
    from gcalendar import delete_event
    try:
        delete_event(event_id)
        user = _req_user()
        log_action(user, 'calendar_event_deleted', {'event_id': event_id}, actor='user')
        return jsonify({'ok': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
