import argparse
import json
import random

from id_data.clothing import get_clothing


def main():
    parser = argparse.ArgumentParser(description="Preview coordinated portrait clothing.")
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--palette", choices=["neutral", "tonal", "muted contrast", "bright accent"])
    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count must be positive")
    random.seed(args.seed)
    for _ in range(args.count):
        print(json.dumps(get_clothing(palette=args.palette), ensure_ascii=False))


if __name__ == "__main__":
    main()
