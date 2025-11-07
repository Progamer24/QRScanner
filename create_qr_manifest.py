#!/usr/bin/env python3
"""Create a CSV manifest with Team Name, Name and QR path for each roster row.

Usage: python create_qr_manifest.py

The script will look for a roster CSV in this order:
 - ./Ignition 1.0 - QR.csv
 - ./teams.csv
 - ./teams.xlsx (will read first sheet)

It will produce `qr_manifest.csv` next to this script.
"""
from pathlib import Path
import csv
import re
import sys

import pandas as pd


DEFAULT_INPUTS = [
    Path.cwd() / "Ignition 1.0 - QR.csv",
    Path.cwd() / "teams.csv",
    Path.cwd() / "teams.xlsx",
]

# Template path (as requested) - note: keep double backslashes when writing literal Python strings
QR_PATH_TEMPLATE = r"C:\Users\Lenovo\Pictures\Club Work\Vegavath\ignition 1.0\ParticipantQR\{filename}"


def sanitize_filename(s: str) -> str:
    if s is None:
        return "unknown"
    s = str(s)
    # remove path-unfriendly characters, keep alphanum, space, underscore, hyphen
    s = re.sub(r"[^A-Za-z0-9 _-]", "", s)
    s = re.sub(r"\s+", "_", s).strip("_")
    if not s:
        return "unknown"
    return s


def find_input_file():
    for p in DEFAULT_INPUTS:
        if p.exists():
            return p
    return None


def read_roster(path: Path):
    if path.suffix.lower() in (".csv",):
        return pd.read_csv(path)
    elif path.suffix.lower() in (".xlsx", ".xls"):
        return pd.read_excel(path)
    else:
        raise RuntimeError(f"Unsupported file: {path}")


def main():
    inp = find_input_file()
    if inp is None:
        print("No roster found. Put `Ignition 1.0 - QR.csv` or `teams.csv` or `teams.xlsx` in the current folder.")
        sys.exit(1)

    print(f"Reading roster from: {inp}")
    df = read_roster(inp)

    # prefer these column names
    team_col = None
    name_col = None
    for c in ["Team Name", "teamName", "team", "Team"]:
        if c in df.columns:
            team_col = c
            break
    for c in ["Name", "name", "Full Name", "FullName"]:
        if c in df.columns:
            name_col = c
            break

    if name_col is None:
        print("No name column found in roster. Columns: ", df.columns.tolist())
        sys.exit(1)

    out_path = Path.cwd() / "qr_manifest.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as outf:
        writer = csv.writer(outf)
        writer.writerow(["Team Name", "Name", "QR"])
        for _, row in df.iterrows():
            team = row.get(team_col) if team_col else ""
            name = row.get(name_col)
            filename = f"{sanitize_filename(team)}_{sanitize_filename(name)}.png"
            qr_path = QR_PATH_TEMPLATE.format(filename=filename)
            writer.writerow([team, name, qr_path])

    print(f"Wrote manifest: {out_path}")
    # show first 5 lines
    import itertools
    with open(out_path, encoding="utf-8") as f:
        for i, line in enumerate(itertools.islice(f, 6)):
            print(line.strip())


if __name__ == "__main__":
    main()
