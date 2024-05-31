import datetime
import logging
import os
import re
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

# Read the 'LOG_LEVEL' environment variable
log_level_str = os.environ.get('LOG_LEVEL', 'INFO')  # Default to 'INFO' if not found

# Convert the log level string to the corresponding logging level
log_level = getattr(logging, log_level_str.upper(), logging.INFO)

# Set the logging level
logging.basicConfig(level=log_level)


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


def is_similar(a, b, threshold=0.8):
    """
    Check if two strings are similar above a certain threshold.

    Args:
        a (str): First string to compare.
        b (str): Second string to compare.
        threshold (float): The similarity threshold.

    Returns:
        bool: True if the similarity is above the threshold, False otherwise.
    """
    ratio = SequenceMatcher(None, a.lower(), b.lower()).ratio()
    return ratio > threshold

def get_events(calendar):
    if not calendar:
        return []

    # Read the 'CALENDAR_OWNER' environment variable
    calendar_owner = os.environ.get('CALENDAR_OWNER', 'Calendar Owner').replace('"',
                                                                                '')  # Default to 'Calendar Owner' if not found

    events = []
    for component in calendar.walk():
        if component.name == "VEVENT":

            summary = component.get("summary")
            description = component.get("description", "")

            # Check for "anniversary" in summary or description
            if is_similar(summary, "anniversary") or is_similar(description, "anniversary"):
                continue  # Skip adding this event


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
            description = component.get("description", "")  # Get the description, if available

            # Replace 'Your' with the value of 'CALENDAR_OWNER' and 'Paid Time Off time' with ' - OOO' in the summary
            modified_summary = summary.replace("Your", calendar_owner).replace("Paid Time Off time", " - OOO")

            events.append({"start": start, "end": end, "summary": modified_summary, "description": description})

    return events


def extract_hours(description):
    """
    Extracts hours from the event description.

    Args:
        description (str): The description of the event.

    Returns:
        str: The formatted hours string if hours are found and are less than 8, otherwise None.
    """
    match = re.search(r"\((\d+) hrs\)", description)
    if match:
        hours = int(match.group(1))
        if hours < 8:
            return f"\n{hours} hrs"
    return None


def format_time_range(start, end):
    """
    Formats the time range based on the start and end times of the event.

    Args:
        start (object): The start time of the event.
        end (object): The end time of the event.

    Returns:
        str: The formatted time range string.
    """
    if start.date() == end.date():
        if start.time() == end.time() and start.time().hour == 0 and start.time().minute == 0:
            return "\n all-day"
        else:
            start_str = start.format('hh:mm A')
            end_str = end.format('hh:mm A')
            return f"\n{start_str} - {end_str}"
    else:
        start_str = start.format('YYYY-MM-DD')
        end_str = end.format('YYYY-MM-DD')
        return f"\nfrom {start_str} to {end_str}"


def calculate_time_range(start, end, description):
    """
    Calculates the time range for the event, prioritizing the hours extracted from the description.

    Args:
        start (object): The start time of the event.
        end (object): The end time of the event.
        description (str): The description of the event.

    Returns:
        str: The calculated time range string.
    """
    time_range = extract_hours(description)
    if time_range is None:
        time_range = format_time_range(start, end)
    return time_range


def post_todays_events_to_slack(events):
    if not events:
        return

    # Sort events by start date and then by summary
    events.sort(key=lambda x: (x['start'], x['summary']))

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
        description = event.get("description", "")

        logging.debug(f"Event Description: {description}")

        time_range = calculate_time_range(start, end, description)

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

    # Sort events by start date and then by summary
    events.sort(key=lambda x: (x['start'], x['summary']))

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
        description = event.get("description", "")

        hours_str = extract_hours(description)

        if hours_str:
            # Extracting integer hours from the string.
            hours = int(re.search(r"\d+", hours_str).group())

            if hours < 8:  # event is less than 8 hours
                date_str = start.format('YYYY-MM-DD')
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{summary}* on {date_str}{hours_str}"
                    }
                })
                continue  # Skip to the next iteration as this event is handled.

        if start.date() == end.date():  # the event occurs within a single day
            date_str = start.format('YYYY-MM-DD')
            if start.time() == end.time() and start.time().hour == 0 and start.time().minute == 0:  # all-day event
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{summary}* on {date_str}"
                    }
                })
            else:  # event with start and end times
                start_str = start.format('hh:mm A')
                end_str = end.format('hh:mm A')
                time_range = f" from {start_str} to {end_str}"
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*{summary}* on {date_str}{time_range}"
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

    # Post today's events
    now = arrow.now('US/Eastern')
    events_today = [event for event in gusto_events if (event['start'].date() <= now.date() <= event['end'].date())]

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
