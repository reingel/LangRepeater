import sys

from .app import AppController


def main() -> None:
    try:
        controller = AppController()
        controller.run()
    except KeyboardInterrupt:
        print("\nExiting.")
        sys.exit(0)


if __name__ == "__main__":
    main()
