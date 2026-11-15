"""Allow `python -m minicoder ...` as well as the `minicoder` console script."""
from minicoder.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
