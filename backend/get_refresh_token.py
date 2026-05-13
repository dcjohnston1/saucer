import json
import os
import urllib.parse
import urllib.request

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']


def main():
    client_secrets_file = 'client_secret.json'
    if not os.path.exists(client_secrets_file):
        print(f"Error: {client_secrets_file} not found.")
        return

    with open(client_secrets_file) as f:
        client_data = json.load(f)['installed']

    client_id = client_data['client_id']
    client_secret = client_data['client_secret']
    redirect_uri = 'http://localhost'

    auth_url = 'https://accounts.google.com/o/oauth2/auth?' + urllib.parse.urlencode({
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'scope': ' '.join(SCOPES),
        'access_type': 'offline',
        'prompt': 'consent',
    })

    print("\nOpen this URL in your browser (sign in as dcjohnston1@gmail.com):\n")
    print(auth_url)
    print()
    print("After granting access, the browser will show an error page (can't connect).")
    print("That's normal. Copy the FULL URL from the address bar and paste it below.\n")

    response_url = input("Paste the full redirect URL here: ").strip()

    parsed = urllib.parse.urlparse(response_url)
    code = urllib.parse.parse_qs(parsed.query).get('code', [response_url])[0]

    data = urllib.parse.urlencode({
        'code': code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code',
    }).encode()

    req = urllib.request.Request('https://oauth2.googleapis.com/token', data=data)
    with urllib.request.urlopen(req) as resp:
        token_data = json.loads(resp.read())

    if 'refresh_token' not in token_data:
        print(f"\nError getting token: {token_data}")
        return

    refresh_token = token_data['refresh_token']
    print(f"\nSuccess! Your new refresh token:\n\n{refresh_token}\n")
    print("Now run this to update the secret:")
    print(f"\necho -n '{refresh_token}' | gcloud secrets versions add GMAIL_REFRESH_TOKEN --project=mediationmate --data-file=-\n")


if __name__ == '__main__':
    main()
