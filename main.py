import hashlib
import json
import os
import pickle
import time
from datetime import date, datetime, timedelta

import boto3
from dateutil import parser
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

BASE_DIR = "/tmp"

AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY", "")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY", "")
AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET", "")

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
CALENDAR_NAME = os.getenv("CALENDAR_NAME", "")

JOPLIN_ID_LEN = 32
JOPLIN_NOTEBOOK_ID = os.getenv("JOPLIN_NOTEBOOK_ID", "")
JOPLIN_TODO_TEMPLATE = """{name}

{description}

id: {id}
parent_id: {parent_id}
created_time: {created_time}
updated_time: {updated_time}
is_conflict: 0
latitude: {latitude}
longitude: {longitude}
altitude: 72.0910
author:
source_url: {source_url}
is_todo: 1
todo_due: 0
todo_completed: 0
source: joplin
source_application: net.cozic.joplin-mobile
application_data:
order: 1614010160303
user_created_time: {user_created_time}
user_updated_time: {user_updated_time}
encryption_cipher_text:
encryption_applied: 0
markup_language: 1
is_shared: 0
type_: 1
"""


def fetch_calendar_events():
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    token_path = f"{BASE_DIR}/token.pickle"
    if os.path.exists(token_path):
        with open(token_path, "rb") as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            client_config = json.loads(OAUTH_CONFIG)
            flow = InstalledAppFlow.from_client_config(
                client_config, scopes=OAUTH_SCOPES
            )
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open(token_path, "wb") as token:
            pickle.dump(creds, token)
    service = build("calendar", "v3", credentials=creds)
    # 'Z' indicates UTC time
    now = datetime.utcnow()
    since = datetime.combine(date.today(), datetime.min.time()).isoformat() + "Z"
    until = (now + timedelta(minutes=1)).isoformat() + "Z"
    cal_id = None
    for cal in service.calendarList().list().execute()["items"]:
        if cal["summary"] == CALENDAR_NAME:
            cal_id = cal["id"]
    events_result = (
        service.events()
        .list(
            calendarId=cal_id,
            timeMin=since,
            timeMax=until,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    events = events_result.get("items", [])
    if not events:
        return
    return events


def create_joplin_entries(events):
    client = boto3.client(
        "s3", aws_access_key_id=AWS_ACCESS_KEY, aws_secret_access_key=AWS_SECRET_KEY
    )
    for event in events:
        due = event["start"].get("dateTime", event["start"].get("date"))
        if "T" not in due:
            due += "T00:00Z"
        name = f'{event["summary"]} (due {due.replace("T", " ").split("+")[0]})'
        description = (
            f"{event.get('description', '')}"
            "\n---\n"
            f"Synced from your [calendar]({event['htmlLink']})"
        )
        id = hashlib.sha256(event["id"].encode("utf8")).hexdigest()[:JOPLIN_ID_LEN]
        s3key = f"{id}.md"
        iso_now = datetime.utcnow().isoformat() + "Z"
        try:
            existing = client.get_object(Bucket=AWS_S3_BUCKET, Key=s3key)
            content = existing["Body"].read().decode("utf8")
            recombined = []
            should_update = False
            # Must update update_time to force resync
            for idx, line in enumerate(content.split("\n")):
                if "updated_time" in line:
                    field, value = line.split(" ")
                    last_update = parser.parse(value)
                    event_due = parser.parse(due)
                    if last_update <= event_due:
                        line = f"{field} {iso_now}"
                        should_update = True
                if "todo_completed" in line:
                    line = "todo_completed: 0"
                if idx == 0:
                    line = name
                recombined.append(line)
            if not should_update:
                continue
            content = "\n".join(recombined)
            content = content.encode("utf8")
            print(f"Updating task {s3key} for event {name}")
        except client.exceptions.NoSuchKey:
            todo = JOPLIN_TODO_TEMPLATE.format(
                name=name,
                description=description,
                id=id,
                parent_id=JOPLIN_NOTEBOOK_ID,
                created_time=iso_now,
                updated_time=iso_now,
                latitude="",
                longitude="",
                source_url="https://google.com",
                user_created_time=iso_now,
                user_updated_time=iso_now,
            ).strip("\n")
            content = todo.encode("utf8")
            print(f"Creating task {s3key} for event {name}")
        client.put_object(Body=content, Bucket=AWS_S3_BUCKET, Key=s3key)


def main():
    while True:
        events = fetch_calendar_events()
        if events:
            create_joplin_entries(events)
        time.sleep(30)


if __name__ == "__main__":
    main()
