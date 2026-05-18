import os
import uuid
from flask import Blueprint, request, jsonify, Response
from lib.firestore_client import get_db
from logger import log_action

files_bp = Blueprint('files', __name__)

_ALLOWED_FILE_TYPES = {
    'application/pdf': '.pdf',
    'image/jpeg': '.jpg',
    'image/png': '.png',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
}
_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB


def _req_user(data=None):
    """Extract the acting user's email from request body or query param."""
    if data:
        v = data.get('user', '')
        if v:
            return v
    return request.args.get('user', 'unknown')


@files_bp.route('/files', methods=['GET'])
def list_files():
    from google.cloud import firestore
    db = get_db()
    docs = db.collection('hana_files').order_by('uploaded_at', direction=firestore.Query.DESCENDING).stream()
    files = []
    for doc in docs:
        d = doc.to_dict()
        d['file_id'] = doc.id
        d.pop('content_text', None)  # don't send full text in list view
        files.append(d)
    return jsonify({'files': files})


@files_bp.route('/files/upload', methods=['POST'])
def upload_file_endpoint():
    from gcs import upload_file
    from datetime import datetime, timezone
    import uuid as _uuid

    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'No file provided'}), 400

    content_type = f.content_type or 'application/octet-stream'
    if content_type not in _ALLOWED_FILE_TYPES:
        # Try to guess from filename
        fname = f.filename or ''
        ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
        type_map = {'pdf': 'application/pdf', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
                    'png': 'image/png', 'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}
        content_type = type_map.get(ext, content_type)
        if content_type not in _ALLOWED_FILE_TYPES:
            return jsonify({'error': f'File type not allowed. Supported: PDF, JPG, PNG, DOCX'}), 400

    file_bytes = f.read()
    if len(file_bytes) > _MAX_FILE_BYTES:
        return jsonify({'error': 'File exceeds 10 MB limit'}), 400

    file_id = str(_uuid.uuid4())
    filename = f.filename or f'upload_{file_id}'
    gcs_path = f"files/{file_id}_{filename}"

    if not upload_file(file_bytes, gcs_path, content_type):
        return jsonify({'error': 'Upload failed'}), 500

    # Extract text for PDFs
    content_text = ''
    if content_type == 'application/pdf':
        try:
            import pdfplumber, io as _io
            with pdfplumber.open(_io.BytesIO(file_bytes)) as pdf:
                for page in pdf.pages:
                    content_text += (page.extract_text() or '') + '\n'
            content_text = content_text[:8000]
        except Exception as e:
            print(f"[files] PDF text extraction error: {e}")

    db = get_db()
    db.collection('hana_files').document(file_id).set({
        'file_id': file_id,
        'filename': filename,
        'source': 'upload',
        'uploaded_at': datetime.now(timezone.utc).isoformat(),
        'size_bytes': len(file_bytes),
        'gcs_path': gcs_path,
        'content_text': content_text,
    })

    user = _req_user()
    log_action(user, 'file_uploaded', {'filename': filename, 'size': len(file_bytes)}, actor='user')
    return jsonify({'ok': True, 'file_id': file_id, 'filename': filename})


@files_bp.route('/files/<file_id>/download', methods=['GET'])
def download_file_endpoint(file_id):
    """Proxy file bytes from GCS directly to the browser."""
    from gcs import download_file
    db = get_db()
    doc = db.collection('hana_files').document(file_id).get()
    if not doc.exists:
        return jsonify({'error': 'File not found'}), 404
    d = doc.to_dict()
    gcs_path = d.get('gcs_path', '')
    filename = d.get('filename', 'file')
    file_bytes, content_type = download_file(gcs_path)
    if file_bytes is None:
        return jsonify({'error': 'Could not retrieve file'}), 500
    return Response(
        file_bytes,
        status=200,
        mimetype=content_type,
        headers={
            'Content-Disposition': f'inline; filename="{filename}"',
            'Content-Length': str(len(file_bytes)),
        }
    )


@files_bp.route('/files/<file_id>', methods=['DELETE'])
def delete_file_endpoint(file_id):
    from gcs import delete_file
    db = get_db()
    doc = db.collection('hana_files').document(file_id).get()
    if not doc.exists:
        return jsonify({'error': 'File not found'}), 404
    gcs_path = doc.to_dict().get('gcs_path', '')
    delete_file(gcs_path)
    db.collection('hana_files').document(file_id).delete()
    user = _req_user()
    log_action(user, 'file_deleted', {'file_id': file_id}, actor='user')
    return jsonify({'ok': True})
