#!/usr/bin/env python3
"""
Migrate saucer-emails.json → Firestore emails collection + GCS email-bodies/.

Usage (from saucer/backend/):
    python migrations/migrate_emails_to_firestore.py

Re-runnable: overwrites Firestore docs and body blobs idempotently.
Does NOT delete saucer-emails.json (kept as 30-day backup).

Exit 0 on full success, exit 1 on any mismatch.
"""

import os
import sys

# Allow running from backend/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gcs import read_json
from email_store import upsert_emails_batch, get_email


def _compare(source: dict, fetched: dict, email_id: str) -> list:
    """Return list of mismatch strings for key fields."""
    mismatches = []
    for field in ('id', 'sender', 'subject', 'date', 'verdict', 'verdict_reason'):
        sv = source.get(field)
        fv = fetched.get(field)
        if sv != fv:
            mismatches.append(f"  {field}: source={sv!r} vs fetched={fv!r}")

    # Body length (10-char tolerance for whitespace normalization)
    src_body = source.get('body') or ''
    ftch_body = fetched.get('body') or ''
    if abs(len(src_body) - len(ftch_body)) > 10:
        mismatches.append(
            f"  body length: source={len(src_body)} vs fetched={len(ftch_body)}"
        )

    src_html = source.get('html_body') or ''
    ftch_html = fetched.get('html_body') or ''
    if abs(len(src_html) - len(ftch_html)) > 10:
        mismatches.append(
            f"  html_body length: source={len(src_html)} vs fetched={len(ftch_html)}"
        )

    src_att = len(source.get('attachments') or [])
    ftch_att = len(fetched.get('attachments') or [])
    if src_att != ftch_att:
        mismatches.append(f"  attachment count: source={src_att} vs fetched={ftch_att}")

    return mismatches


def main():
    print("Reading saucer-emails.json from GCS...")
    emails = read_json('saucer-emails.json', None)
    if emails is None:
        print("ERROR: saucer-emails.json not found in GCS.")
        sys.exit(1)
    if not isinstance(emails, list):
        print(f"ERROR: expected list, got {type(emails)}")
        sys.exit(1)

    total = len(emails)
    print(f"Source email count: {total}")

    print(f"\nWriting {total} emails to Firestore + GCS email-bodies/...")
    upsert_emails_batch(emails)
    print("Writes complete.")

    print("\nVerifying...")
    verified = 0
    all_mismatches = []

    for email in emails:
        email_id = email.get('id', '')
        fetched = get_email(email_id)
        if fetched is None:
            all_mismatches.append(f"  {email_id}: NOT FOUND after migration")
            continue
        mismatches = _compare(email, fetched, email_id)
        if mismatches:
            all_mismatches.append(f"  {email_id}:")
            all_mismatches.extend(mismatches)
        else:
            verified += 1

    print(f"\n{'='*60}")
    print(f"Total emails in source: {total}")
    print(f"Successfully verified:  {verified}")
    print(f"Mismatches:             {total - verified}")

    if all_mismatches:
        print("\nMismatch details:")
        for line in all_mismatches:
            print(line)
        print("\nMigration FAILED — do not deploy. Fix mismatches and re-run.")
        sys.exit(1)
    else:
        print("\nAll emails verified. Migration successful.")
        print("saucer-emails.json has NOT been deleted (30-day backup).")
        sys.exit(0)


if __name__ == '__main__':
    main()
