import json
import csv
import os
from pathlib import Path


JSON_DIR = Path(__file__).parent / "JSON"
OUT_CSV = Path(__file__).parent / "teams.csv"
OUT_XLSX = Path(__file__).parent / "teams.xlsx"

def safe_join_list(val):
    if val is None:
        return ""
    if isinstance(val, list):
        return ", ".join(str(x) for x in val if x is not None)
    return str(val)


def extract_from_file(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    team_name = data.get("teamName") or data.get("team_name") or data.get("TeamName") or ""
    campus = data.get("campus", "")

    members = data.get("members") or []

    rows = []

    # collect unique members by SRN or email to avoid duplicates (e.g., leader duplicated)
    seen = set()

    for m in members:
        name = m.get("name") or m.get("fullName") or ""
        srn = (m.get("srn") or m.get("SRN") or "").strip()
        email = (m.get("email") or "").strip()
        phone = m.get("phone") or m.get("Phone") or ""
        sem = safe_join_list(m.get("semester") or m.get("sem"))
        sec = m.get("section") or m.get("sec") or ""
        dep = safe_join_list(m.get("department") or m.get("dept"))
        hostel = safe_join_list(m.get("hostel") or m.get("Hostel"))

        # payment url - prefer explicit url field if present
        payment_url = m.get("payment_url") or m.get("paymentUrl") or m.get("paymentDataUrl") or m.get("payment_data_url")
        if not payment_url:
            # sometimes only a filename is present
            payment_name = m.get("paymentName") or m.get("payment_name") or ""
            payment_url = payment_name

        # dedupe key: prefer srn, else email, else name+phone
        key = srn or email or (name + "::" + phone)
        if not key:
            # skip if entirely empty
            continue
        if key in seen:
            continue
        seen.add(key)

        rows.append({
            "Team Name": team_name,
            "Name": name,
            "Srn": srn,
            "Email": email,
            "Phone No": phone,
            "Campus": campus,
            "Sem": sem,
            "Sec": sec,
            "Dep": dep,
            "Hostel/Day scholar": hostel,
            "Payment_url": payment_url,
        })

    return rows


def main():
    if not JSON_DIR.exists():
        print(f"JSON directory not found: {JSON_DIR}")
        return

    all_rows = []
    for p in sorted(JSON_DIR.glob("*.json")):
        try:
            rows = extract_from_file(p)
            all_rows.extend(rows)
        except Exception as e:
            print(f"Failed to parse {p}: {e}")

    if not all_rows:
        print("No rows extracted.")
        return

    # write CSV
    fieldnames = [
        "Team Name",
        "Name",
        "Srn",
        "Email",
        "Phone No",
        "Campus",
        "Sem",
        "Sec",
        "Dep",
        "Hostel/Day scholar",
        "Payment_url",
    ]

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in all_rows:
            writer.writerow(r)

    print(f"Wrote CSV: {OUT_CSV}")

    # try to write XLSX if pandas is available
    try:
        import pandas as pd

        df = pd.DataFrame(all_rows)
        df = df[fieldnames]
        df.to_excel(OUT_XLSX, index=False)
        print(f"Wrote XLSX: {OUT_XLSX}")
    except Exception as e:
        print("Could not write XLSX (pandas/openpyxl missing). CSV is available.")


if __name__ == "__main__":
    main()
