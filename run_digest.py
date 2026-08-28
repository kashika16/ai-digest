import argparse
from pathlib import Path

from ai_digest.config import load_config
from ai_digest.digest import preview_digest, preview_digest_html, run_digest
from ai_digest.launchd import launch_agent_destination, write_launch_agent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--preview-html", metavar="PATH")
    parser.add_argument("--ignore-seen", action="store_true")
    parser.add_argument("--install-launchd", action="store_true")
    parser.add_argument("--launchd-path", metavar="PATH")
    parser.add_argument("--hour", type=int, default=7)
    parser.add_argument("--minute", type=int, default=0)
    args = parser.parse_args()

    config = load_config()
    if args.preview:
        print(preview_digest(config, ignore_seen=args.ignore_seen))
        return
    if args.preview_html:
        output_path = Path(args.preview_html).expanduser()
        output_path.write_text(preview_digest_html(config, ignore_seen=args.ignore_seen))
        print(output_path)
        return
    if args.install_launchd:
        destination = Path(args.launchd_path).expanduser() if args.launchd_path else launch_agent_destination()
        write_launch_agent(config, destination, args.hour, args.minute)
        print(destination)
        return
    run_digest(config, ignore_seen=args.ignore_seen)


if __name__ == "__main__":
    main()
