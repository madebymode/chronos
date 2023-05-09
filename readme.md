# Event Notifier

This is a Python script that fetches events from an iCalendar feed and posts a summary of the day's events to a designated Slack channel. The script is designed to run daily using a Docker container and a cron job.

## Prerequisites

To run this script, you will need the following:

- A Slack bot token with the `chat:write` & `channels:join` scopes
- An iCalendar feed URL
- Docker installed on your system

## Configuration

Before running the script, you need to set the following environment variables:

- `SLACK_BOT_TOKEN`: Your Slack bot token
- `SLACK_CHANNEL`: The name of the Slack channel to post the events summary to
- `ICS_URL`: The URL of the iCalendar feed

You can set these variables using a `.env` file in the root of the project. There is an example file provided (`example.env`).

## Usage

To run the script, use the following command:

```
docker-compose up
```

This will start the Docker container and run the script at 9am Eastern Time every day.

## Modifying the Script

If you need to modify the script to meet your requirements, you can do so by editing the `main.py` file in the root of the project. Once you have made your changes, rebuild the Docker image using the following command:

```
docker-compose build
```

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.
