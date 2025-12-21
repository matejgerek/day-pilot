from datetime import datetime
from zoneinfo import ZoneInfo

from daypilot.services.config import load_config
from daypilot.services.weather import WeatherService


def main() -> None:
    config = load_config()
    service = WeatherService()
    if config.location.timezone:
        now = datetime.now(ZoneInfo(config.location.timezone))
    else:
        now = datetime.now().astimezone()
    report = service.fetch(config.location, now=now)
    print(service.format_for_prompt(report))


if __name__ == "__main__":
    main()
