import base64
import hashlib
import os
import pickle
import re
import time
import traceback
from datetime import date, datetime, timedelta

import boto3
from dateutil import parser
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

BASE_DIR = "/tmp"

AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY", "")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY", "")
AWS_S3_BUCKET = os.getenv("AWS_S3_BUCKET", "")

OAUTH_TOKEN_B64 = os.getenv("OAUTH_TOKEN_B64", "")
CALENDAR_NAME = os.getenv("CALENDAR_NAME", "")
UTC_UNIX_EPOCH = datetime.utcfromtimestamp(0)

JOPLIN_ID_LEN = 32
JOPLIN_NOTEBOOK_ID = os.getenv("JOPLIN_NOTEBOOK_ID", "")
JOPLIN_TODO_TEMPLATE = """🗓 {name}

{description}

id: {id}
parent_id: {parent_id}
is_conflict: 0
latitude: {latitude}
longitude: {longitude}
altitude: 72.0910
author:
source_url: {source_url}
is_todo: 1
todo_due: {todo_due}
todo_completed: 0
source: joplin
source_application: net.cozic.joplin-mobile
application_data:
order: 1614010160303
created_time: {created_time}
updated_time: {updated_time}
user_created_time: {user_created_time}
user_updated_time: {user_updated_time}
encryption_cipher_text:
encryption_applied: 0
markup_language: 1
is_shared: 0
type_: 1
"""

POLL_SECONDS = int(os.getenv("POLL_SECONDS", "60"))
LOOKAHEAD_SECONDS = int(os.getenv("LOOKAHEAD_SECONDS", "60"))

s3client = boto3.client(
    "s3", aws_access_key_id=AWS_ACCESS_KEY, aws_secret_access_key=AWS_SECRET_KEY
)
t2d = datetime.utcfromtimestamp


def main():
    if not OAUTH_TOKEN_B64:
        print("Please run gimme_token.py where there's a browser :(")
        return
    while True:
        events = fetch_calendar_events()
        if events:
            create_joplin_entries(events)
        time.sleep(POLL_SECONDS)


def fetch_calendar_events():
    token = base64.decodebytes(OAUTH_TOKEN_B64.encode("utf8"))
    creds = pickle.loads(token)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            raise ValueError("Invalid OAuth token")
    service = build("calendar", "v3", credentials=creds)
    # 'Z' indicates UTC time
    now = datetime.utcnow()
    since = datetime.combine(date.today(), datetime.min.time()).isoformat() + "Z"
    until = (now + timedelta(seconds=LOOKAHEAD_SECONDS)).isoformat() + "Z"
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
    iso_now = datetime.utcnow().isoformat() + "Z"
    for event in events:
        due = event["start"].get("dateTime", event["start"].get("date"))
        if "T" not in due:
            due += "T00:00Z"
        due = parser.parse(due)
        name = f'{event["summary"]}'
        description = (
            f"{event.get('description', '')}"
            "\n\n---\n"
            f"<sup>Synced from your [calendar]({event['htmlLink']})</sup>"
        )
        id = hashlib.sha256(event["id"].encode("utf8")).hexdigest()[:JOPLIN_ID_LEN]
        s3key = f"{id}.md"
        try:
            content = _update_entry(s3key, name, iso_now, due)
            if not content:
                continue
            print(f"Updating task {s3key} for event {name}")
        except Exception as e:
            traceback.print_exc()
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
                todo_due=int(
                    (due - due.utcoffset()).replace(tzinfo=None).timestamp() * 1000
                ),
            ).strip("\n")
            content = todo.encode("utf8")
            print(f"Creating task {s3key} for event {name}")
        s3client.put_object(Body=content, Bucket=AWS_S3_BUCKET, Key=s3key)


def _update_entry(s3key, name, iso_now, due):
    existing = s3client.get_object(Bucket=AWS_S3_BUCKET, Key=s3key)
    original_content = existing["Body"].read().decode("utf8")
    content = original_content
    # TODO this could just be one search
    todo_due = t2d(int(re.search(r"todo_due: (?P<v>.*)\n", content).group("v")) / 1000)
    todo_completed = t2d(
        int(re.search(r"todo_completed: (?P<v>.*)\n", content).group("v")) / 1000
    )
    utc_due = (due - due.utcoffset()).replace(tzinfo=None)
    if todo_completed > utc_due or utc_due < datetime.utcnow():
        return
    recombined = []
    # Must update update_time to force resync
    for idx, line in enumerate(content.split("\n")):
        if "todo_due" in line:
            line = f"todo_due: {int(utc_due.timestamp() * 1000)}"
        if "todo_completed" in line and utc_due != todo_due:
            line = "todo_completed: 0"
        if idx == 0:
            line = f"🗓 {name}"
        recombined.append(line)
    if original_content == "\n".join(recombined):
        return
    for idx, line in enumerate(recombined):
        if "updated_time" in line:
            field, _ = line.split(" ")
            recombined[idx] = f"{field} {iso_now}"
            break
    return "\n".join(recombined).encode("utf8")


if __name__ == "__main__":
    main()
