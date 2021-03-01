import json
import base64
import os

from google_auth_oauthlib.flow import InstalledAppFlow

OAUTH_CLIENT_ID = os.getenv("OAUTH_CLIENT_ID", "")
OAUTH_CLIENT_SECRET = os.getenv("OAUTH_CLIENT_SECRET", "")
OAUTH_PROJECT_ID = os.getenv("OAUTH_PROJECT_ID", "")
OAUTH_SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
OAUTH_CONFIG = f"""
    {{
        "installed": {{
            "client_id": "{OAUTH_CLIENT_ID}",
            "project_id": "{OAUTH_PROJECT_ID}",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": "{OAUTH_CLIENT_SECRET}",
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"]
        }}
    }}
"""


def main():
    client_config = json.loads(OAUTH_CONFIG)
    flow = InstalledAppFlow.from_client_config(
        client_config, scopes=OAUTH_SCOPES
    )
    creds = flow.run_local_server(port=0)
    print("Set this token as OAUTH_TOKEN_B64 env variable")
    print(base64.encode(creds))


if __name__ == "__main__":
    main()
