"""Print the scripted scene sequence. Used as `python -m fakes.scene`."""

from fakes.scene.script import publish_script


def main() -> None:
    """Print each scripted scene message."""

    def publish(topic: str, message: object) -> None:
        print(f"{topic} {message}")

    publish_script(publish)


if __name__ == "__main__":
    main()
