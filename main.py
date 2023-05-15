import os

import arrow
import requests
from icalendar import Calendar
from slack_sdk import WebClient

# Set up the Slack app
SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
client = WebClient(token=SLACK_BOT_TOKEN)

# Define the ICS file URL
ICS_URL = os.environ["ICS_URL"]

# Define the target Slack channel
SLACK_CHANNEL = os.environ["SLACK_CHANNEL"]


def fetch_calendar(url):
  response = requests.get(url)
  response.raise_for_status()
  #print(response.text)  # Print the raw response
  calendar = Calendar.from_ical(response.text)
  return calendar


def get_todays_events(calendar):
  now = arrow.utcnow()
  events_today = []

  for component in calendar.walk():
    if component.name == "VEVENT":
      start = arrow.get(component.get("dtstart").dt)
      # Check if 'dtend' exists before attempting to get its value
      if component.get("dtend"):
        end = arrow.get(component.get("dtend").dt)
        if start.date() != end.date():  # multi-day event
          start_time = start.format("HH:mm")
          end_time = end.format("HH:mm")
          event_span = f"{start.format('YYYY-MM-DD')} {start_time} => {end.format('YYYY-MM-DD')} {end_time}"
        else:
          event_span = f"{start.format('YYYY-MM-DD')} ({start.format('HH:mm')} - {end.format('HH:mm')})"
      else:
        end = start  # If there's no end date, assume it's the same as the start date
        event_span = f"{start.format('YYYY-MM-DD')}"

      summary = component.get("summary")

      if start.date() <= now.date() <= end.date():
        events_today.append(
          {"summary": summary, "event_span": event_span}
        )

  return events_today


def get_events_in_range(calendar, start_date, end_date):
  events_in_range = []

  for component in calendar.walk():
    if component.name == "VEVENT":
      start = arrow.get(component.get('dtstart').dt)
      end = start  # Assume it's an all-day event

      # If 'dtend' exists, get its value and adjust for all-day events
      if component.get('dtend'):
        end = arrow.get(component.get('dtend').dt).shift(days=-1)  # Subtract a day from the end date

      summary = component.get('summary')

      # Check if event starts or ends within the date range, excluding the end date of the range
      if start_date.date() <= start.date() < end_date.date() or \
        start_date.date() < end.date() < end_date.date() or \
        (start.date() <= start_date.date() and end.date() >= end_date.date()):
        events_in_range.append({
          'start': start,
          'end': end,
          'summary': summary,
        })

  # Sort events by start date
  events_in_range.sort(key=lambda x: x['start'])

  return events_in_range


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
      if start.time() == end.time():  # all-day event
        time_range = ""
      else:  # event with start and end times
        start_str = start.format('HH:mm')
        end_str = end.format('HH:mm')
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
      date_str = start.format('YYYY-MM-DD')
      blocks.append({
        "type": "section",
        "text": {
          "type": "mrkdwn",
          "text": f"*{summary}* on {date_str}"
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
  calendar = fetch_calendar(ICS_URL)
  now = arrow.utcnow()

  # If today is Monday, post a summary of this week's events
  if now.format('dddd') == 'Monday':
    end_of_week = now.shift(days=+6)
    events_this_week = get_events_in_range(calendar, now, end_of_week)
    post_weekly_summary_to_slack(events_this_week)

  # Post today's events
  events_today = get_events_in_range(calendar, now, now)
  post_todays_events_to_slack(events_today)


if __name__ == "__main__":
  daily_job()
