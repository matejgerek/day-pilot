from daypilot.services.config import ConfigMissingError, load_config
from daypilot.services.whoop_data import WhoopDataService, WhoopServiceError


def main() -> None:
    try:
        config = load_config()
    except ConfigMissingError as exc:
        print(f"Config error: {exc}")
        return

    if not config.whoop:
        print("WHOOP is not connected. Run `cli whoop-connect` first.")
        return

    service = WhoopDataService(config.whoop)
    try:
        snapshot = service.get_snapshot()
    except WhoopServiceError as exc:
        print(f"WHOOP unavailable: {exc}")
        return

    print(snapshot.format_for_prompt())


if __name__ == "__main__":
    main()
