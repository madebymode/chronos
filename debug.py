import sys

import arrow

import main  # import the main.py script

# get the date argument from command line
if len(sys.argv) != 2:
    print("Please provide a date as argument in the format YYYY-MM-DD.")
    sys.exit(1)

# convert the argument to a date
try:
    date_arg = arrow.get(sys.argv[1], 'YYYY-MM-DD').date()
except Exception as e:
    print("Invalid date format. Please provide a date in the format YYYY-MM-DD.")
    sys.exit(1)


def specific_day_job():
    gusto_calendar = main.fetch_calendar(main.GUSTO_ICS_URL)
    gusto_events = main.get_events(gusto_calendar)

    # Post events for the specific date
    events_on_date = [event for event in gusto_events if event['start'].date() <= date_arg <= event['end'].date()]
    main.post_todays_events_to_slack(events_on_date)


if __name__ == "__main__":
    specific_day_job()
