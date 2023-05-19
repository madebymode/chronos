import datetime
import os
import string
from difflib import SequenceMatcher

import arrow
import requests
from icalendar import Calendar
from slack_sdk import WebClient

# Set up the Slack app
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
client = WebClient(token=SLACK_BOT_TOKEN)

# Define the ICS file URLs and local file paths
GUSTO_ICS_URL = os.getenv("GUSTO_ICS_URL")
KINHR_LOCAL_ICS_PATH = os.getenv("KINHR_ICS_PATH")

# Define the target Slack channel
SLACK_CHANNEL = os.environ["SLACK_CHANNEL"]


def fetch_calendar(source, is_url=True):
    try:
        if is_url:
            response = requests.get(source)
            response.raise_for_status()
            calendar = Calendar.from_ical(response.text)
        else:  # If the source is a local file path
            with open(source, 'r') as file:
                calendar = Calendar.from_ical(file.read())
        return calendar
    except Exception as e:
        print(f"Failed to fetch calendar from source: {source}, due to {e}")
        return None


def get_events(calendar):
    if not calendar:
        return []

    events = []
    for component in calendar.walk():
        if component.name == "VEVENT":
            start = arrow.get(component.get("dtstart").dt)
            end = component.get("dtend")

            # Check if the events have a time, if so, convert to 'US/Eastern' timezone
            if isinstance(component.get('dtstart').dt, datetime.datetime):
                start = start.to('US/Eastern')

            if end:
                end = arrow.get(end.dt)
                if isinstance(end.datetime, datetime.datetime):
                    end = end.to('US/Eastern')

                if "VALUE=DATE" in component.get("dtend").to_ical().decode():
                    # If end is a date (but not a datetime), subtract one day
                    end = end.shift(days=-1)
            else:
                end = start

            summary = component.get("summary")
            events.append({"start": start, "end": end, "summary": summary})
    return events


def normalize_string(s):
    """
    Removes punctuation and converts string to lower case
    """
    s = s.lower()
    s = s.translate(str.maketrans('', '', string.punctuation))
    return s


def similarity(a, b):
    """
    Returns a measure of the sequences' similarity as a float in the range [0, 1].
    """
    return SequenceMatcher(None, a, b).ratio()


def first_word(a, b):
    """
    Checks if the first words of two strings are identical
    """
    return a.split()[0] == b.split()[0]


def remove_duplicates(events):
    """
    Removes duplicates based on start/end times and similar summary descriptions.
    """
    unique_events = []

    for event in events:
        if not any(e for e in unique_events if e['start'] == event['start'] and
                                               e['end'] == event['end'] and
                                               first_word(normalize_string(e['summary']),
                                                          normalize_string(event['summary'])) and
                                               similarity(normalize_string(e['summary']),
                                                          normalize_string(event['summary'])) > 0.6):
            unique_events.append(event)

    return unique_events


def post_todays_events_to_slack(events):
    if not events:
        return

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Today's events:"
            }
        }
    ]

    for event in events:
        start = event["start"]
        end = event["end"]
        summary = event["summary"]

        if start.date() == end.date():  # the event occurs within a single day
            if start.time() == end.time() and start.time().hour == 0 and start.time().minute == 0:  # all-day event
                time_range = "\n all-day"
            else:  # event with start and end times
                start_str = start.format('hh:mm A')
                end_str = end.format('hh:mm A')
                time_range = f"\n{start_str} - {end_str}"
        else:  # event spans multiple days
            start_str = start.format('YYYY-MM-DD')
            end_str = end.format('YYYY-MM-DD')
            time_range = f"\nfrom {start_str} to {end_str}"

        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{summary}*{time_range}"
            }
        })

    blocks.append({"type": "divider"})

    client.chat_postMessage(channel=SLACK_CHANNEL, blocks=blocks)


def post_weekly_summary_to_slack(events):
    if not events:
        return

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "This week's events:"
            }
        }
    ]

    for event in events:
        start = event["start"]
        end = event["end"]
        summary = event["summary"]

        if start.date() == end.date():  # the event occurs within a single day
            if start.time() == end.time() and start.time().hour == 0 and start.time().minute == 0:  # all-day event
                date_str = start.format('YYYY-MM-DD')
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{summary}* on {date_str}"
                    }
                })
            else:
                date_str = start.format('YYYY-MM-DD')
                start_str = start.format('hh:mm A')
                end_str = end.format('hh:mm A')
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{summary}* on {date_str} from {start_str} to {end_str}"
                    }
                })
        else:  # event spans multiple days
            start_str = start.format('YYYY-MM-DD')
            end_str = end.format('YYYY-MM-DD')
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*{summary}* from {start_str} to {end_str}"
                }
            })

    blocks.append({"type": "divider"})

    client.chat_postMessage(channel=SLACK_CHANNEL, blocks=blocks)


def daily_job():
    gusto_calendar = fetch_calendar(GUSTO_ICS_URL)
    gusto_events = get_events(gusto_calendar)

    kinhr_calendar = fetch_calendar(KINHR_LOCAL_ICS_PATH, is_url=False)
    kinhr_events = get_events(kinhr_calendar)

    # Combine events from both calendars and remove duplicates
    combined_events = remove_duplicates(gusto_events + kinhr_events)

    # Post today's events
    now = arrow.now('US/Eastern')
    events_today = [event for event in combined_events if (event['start'].date() <= now.date() <= event['end'].date())]

    # If today is Monday, post a summary of this week's events and anniversary events from the weekend
    if now.format('dddd') == 'Monday':
        # Fetch events from this week
        end_of_week = now.shift(days=+6)
        events_this_week = [event for event in combined_events if
                            now.date() <= event['start'].date() <= end_of_week.date()]
        post_weekly_summary_to_slack(events_this_week)

        # post today AFTER our summary
        post_todays_events_to_slack(events_today)
    else:
        post_todays_events_to_slack(events_today)




if __name__ == "__main__":
    daily_job()
