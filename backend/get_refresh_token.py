import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

def main():
    client_secrets_file = 'client_secret.json'

    if not os.path.exists(client_secrets_file):
        print(f"Error: {client_secrets_file} not found.")
        return

    flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, SCOPES)
    flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'

    auth_url, _ = flow.authorization_url(prompt='consent')
    print("\nOpen this URL in your browser:\n")
    print(auth_url)
    print()

    code = input("Paste the authorization code here: ").strip()
    flow.fetch_token(code=code)
    creds = flow.credentials

    print("\nSuccessfully obtained credentials!")
    print(f"GMAIL_CLIENT_ID: {creds.client_id}")
    print(f"GMAIL_CLIENT_SECRET: {creds.client_secret}")
    print(f"GMAIL_REFRESH_TOKEN: {creds.refresh_token}")

if __name__ == '__main__':
    main()
