import io
import json
import os
from datetime import datetime

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

# Import utils lazily and handle import errors gracefully (some hosts may fail importing cv2 at import time)
try:
    from utils import generate_qr_image, make_payload, decode_qr_from_bytes
    UTILS_AVAILABLE = True
    IMPORT_ERROR_MSG = ""
except Exception as e:
    # Keep the app running; server-side decoding will be unavailable
    generate_qr_image = None
    make_payload = None
    decode_qr_from_bytes = None
    UTILS_AVAILABLE = False
    IMPORT_ERROR_MSG = str(e)
import pathlib
import re
import zipfile


DEFAULT_COLUMNS = ["Dinner", "Pizza", "Breakfast", "MRD"]


def load_roster(uploaded_file):
    if uploaded_file is not None:
        df = pd.read_excel(uploaded_file)
    else:
        # try to load default teams.csv/xlsx from parent workspace
        default_xlsx = Path = None
        local_xlsx = os.path.join(os.path.dirname(__file__), "..", "teams.xlsx")
        local_csv = os.path.join(os.path.dirname(__file__), "..", "teams.csv")
        if os.path.exists(local_xlsx):
            df = pd.read_excel(local_xlsx)
        elif os.path.exists(local_csv):
            df = pd.read_csv(local_csv)
        else:
            st.warning("No roster uploaded and no default `teams.csv`/`teams.xlsx` found. Upload an XLSX to continue.")
            return None
    return df


def ensure_attendance_columns(df: pd.DataFrame):
    for c in DEFAULT_COLUMNS:
        if c not in df.columns:
            df[c] = False
        # ensure timestamp column exists for each attendance column
        ts_col = f"{c}_ts"
        if ts_col not in df.columns:
            df[ts_col] = ""
    return df


def qr_bytes_for_row(row):
    payload = make_payload(row)
    img = generate_qr_image(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue(), payload


def sanitize_filename(s: str) -> str:
    if not s:
        return "unknown"
    # remove problematic chars, replace spaces with _
    s = re.sub(r"[\\/:*?\"<>|]+", "", s)
    s = re.sub(r"\s+", "_", s)
    return s


def mark_attendance(df: pd.DataFrame, identifier: str, columns_to_mark, source_path: str = None):
    # Identifier might be SRN, Email, or Name
    mask = (
        df.get("Srn", pd.Series([None]*len(df))).astype(str).fillna("") == identifier
    ) | (
        df.get("Email", pd.Series([None]*len(df))).astype(str).fillna("") == identifier
    ) | (
        df.get("Name", pd.Series([None]*len(df))).astype(str).fillna("") == identifier
    )
    if not mask.any():
        return False, f"No matching row found for id '{identifier}'"

    # set boolean True for checked columns and record a timestamp column alongside
    for c in columns_to_mark:
        if c not in df.columns:
            df[c] = False
        df.loc[mask, c] = True
        ts_col = f"{c}_ts"
        df.loc[mask, ts_col] = datetime.now().isoformat()

    # if a source CSV path was provided (loaded from disk), overwrite it in-place
    if source_path:
        try:
            # preserve original CSV formatting by writing without index
            df.to_csv(source_path, index=False)
        except Exception as e:
            return True, f"Marked (but failed to write to source CSV: {e})"

    return True, "Marked"


def main():
    st.set_page_config(page_title="Attendance Marker", layout="wide")
    st.title("Attendance marker — Dinner / Snacks / Breakfast")

    st.sidebar.header("Mode")
    mode = st.sidebar.radio("Mode", ["Admin", "Scanner", "Export"])

    uploaded = st.sidebar.file_uploader("Upload roster XLSX/CSV", type=["xlsx", "xls", "csv"], key="upload")

    df = None
    source_path = None
    if uploaded is not None:
        # user uploaded in the UI; keep in-memory only
        if uploaded.name.lower().endswith('.csv'):
            df = pd.read_csv(uploaded)
        else:
            df = pd.read_excel(uploaded)
    else:
        # attempt to load specific workspace CSV first, then common filenames
        workspace_csv = os.path.join(os.getcwd(), "Ignition 1.0 - QR.csv")
        root_csv = os.path.join(os.path.dirname(__file__), "..", "teams.csv")
        root_xlsx = os.path.join(os.path.dirname(__file__), "..", "teams.xlsx")
        if os.path.exists(workspace_csv):
            df = pd.read_csv(workspace_csv)
            source_path = workspace_csv
        elif os.path.exists(root_xlsx):
            df = pd.read_excel(root_xlsx)
            source_path = root_xlsx
        elif os.path.exists(root_csv):
            df = pd.read_csv(root_csv)
            source_path = root_csv

    if df is None:
        if mode == "Admin":
            st.info("Upload a roster `.xlsx` file that includes columns like Name, Srn, Email. The app will add attendance columns if missing.")
        else:
            st.warning("No roster loaded. Upload under the sidebar to proceed.")
    else:
        df = ensure_attendance_columns(df)

        if mode == "Admin":
            st.header("Roster preview")
            # show only Team Name, Name and attendance columns as checkboxes
            display_cols = [c for c in ["Team Name", "Name"] if c in df.columns]
            for c in DEFAULT_COLUMNS:
                if c not in df.columns:
                    df[c] = False
                display_cols.append(c)

            st.write("Edit attendance by toggling the checkboxes below; timestamps are used internally.")

            # search/filter box to quickly find a participant by Name or Team
            search = st.text_input("Search by name or team (case-insensitive)")
            if search:
                mask = pd.Series([False] * len(df))
                if 'Name' in df.columns:
                    mask = mask | df['Name'].astype(str).str.contains(search, case=False, na=False)
                if 'Team Name' in df.columns:
                    mask = mask | df['Team Name'].astype(str).str.contains(search, case=False, na=False)
                filtered = df[mask]
                st.write(f"Showing {len(filtered)} matching rows")
            else:
                filtered = df

            # render rows with checkboxes for the filtered view
            changed = False
            for idx, row in filtered.iterrows():
                cols = st.columns([3, 4, 1, 1, 1, 1])
                with cols[0]:
                    st.write(str(row.get('Team Name', '')))
                with cols[1]:
                    st.write(str(row.get('Name', '')))
                # present current state as checkbox (checked if not empty)
                val1 = bool(row.get('Dinner'))
                val2 = bool(row.get('Pizza'))
                val3 = bool(row.get('Breakfast'))
                val4 = bool(row.get('MRD'))
                with cols[2]:
                    new1 = st.checkbox('Dinner', value=val1, key=f'dinner_{idx}')
                with cols[3]:
                    new2 = st.checkbox('Pizza', value=val2, key=f'pizza_{idx}')
                with cols[4]:
                    new3 = st.checkbox('Breakfast', value=val3, key=f'breakfast_{idx}')
                with cols[5]:
                    new4 = st.checkbox('MRD', value=val4, key=f'mrd_{idx}')

                # store boolean when changed (timestamps kept by mark_attendance or manual save)
                if new1 != val1:
                    changed = True
                    df.at[idx, 'Dinner'] = bool(new1)
                if new2 != val2:
                    changed = True
                    df.at[idx, 'Pizza'] = bool(new2)
                if new3 != val3:
                    changed = True
                    df.at[idx, 'Breakfast'] = bool(new3)
                if new4 != val4:
                    changed = True
                    df.at[idx, 'MRD'] = bool(new4)

            if changed:
                if st.button('Save changes to roster'):
                    # if we loaded from a source CSV on disk, overwrite it
                    if source_path and source_path.lower().endswith('.csv'):
                        try:
                            df.to_csv(source_path, index=False)
                            st.success(f'Changes saved to {source_path}')
                        except Exception as e:
                            st.error(f'Failed to write changes to source CSV: {e}')
                    else:
                        st.success('Changes saved in memory; use Export to download updated XLSX')

            st.markdown("---")
            st.subheader("Generate and save QR codes")
            gen_all = st.button("Generate & save all QR PNGs")

            if gen_all:
                # create output folder
                out_dir = pathlib.Path(os.path.join(os.path.dirname(__file__), "..", "qrcodes")).resolve()
                out_dir.mkdir(parents=True, exist_ok=True)
                saved_files = []
                for idx, row in df.iterrows():
                    # generate Aztec (or QR fallback) containing only Team and Name
                    qr_bytes, payload = qr_bytes_for_row(row)
                    team = str(row.get('Team Name') or row.get('teamName') or '')
                    name = str(row.get('Name') or row.get('name') or '')
                    fname = f"{sanitize_filename(team)}_{sanitize_filename(name)}.png"
                    dest = out_dir / fname
                    with open(dest, 'wb') as f:
                        f.write(qr_bytes)
                    saved_files.append(dest)

                st.success(f"Saved {len(saved_files)} QR PNGs to {out_dir}")
                # create zip for download
                zip_path = out_dir.with_suffix('.zip')
                with zipfile.ZipFile(zip_path, 'w') as zf:
                    for p in saved_files:
                        zf.write(p, arcname=p.name)
                with open(zip_path, 'rb') as zf:
                    st.download_button('Download all QR PNGs (zip)', data=zf.read(), file_name=zip_path.name, mime='application/zip')

            st.markdown("---")
            # prepare xlsx bytes for download
            try:
                import io as _io
                buf = _io.BytesIO()
                df.to_excel(buf, index=False, engine='openpyxl')
                buf.seek(0)
                st.download_button("Download roster (xlsx)", data=buf.getvalue(), file_name="roster_with_attendance.xlsx", mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            except Exception as _e:
                st.error(f"Failed to create XLSX for download: {_e}")

        elif mode == "Scanner":
            st.header("Scanner")
            st.write("Open this page on your phone and allow camera access — the app will continuously scan and mark QR codes (no photo button required).")
            columns_to_mark = st.multiselect("Columns to mark when scanning", options=list(df.columns), default=DEFAULT_COLUMNS)

            st.markdown("---")
            st.subheader("Live browser scanner (recommended)")
            st.write("If your browser prompts for camera permission, allow it. The scanner will auto-detect QR codes and send the decoded text back to the app.")

            # html5-qrcode live scanner embedded via streamlit components
            html = f"""
            <div id="reader" style="width:100%"></div>
            <script src="https://unpkg.com/html5-qrcode@2.3.8/minified/html5-qrcode.min.js"></script>
            <script>
            const sendValue = (v) => {{
                const data = {{isStreamlitMessage: true, type: 'streamlit:setComponentValue', value: v}};
                window.parent.postMessage(data, '*');
            }};

            function onScanSuccess(decodedText, decodedResult) {{
                // send decoded text back to Streamlit app
                sendValue(decodedText);
            }}

            function onScanFailure(error) {{
                // ignore for now
            }}

            const config = {{ fps: 10, qrbox: 250 }};
            const html5QrcodeScanner = new Html5QrcodeScanner('reader', config, /* verbose= */ false);
            html5QrcodeScanner.render(onScanSuccess, onScanFailure);
            </script>
            """

            # components.html will return the decoded text when the embedded JS calls postMessage with the correct payload
            result = components.html(html, height=450)

            # fallback upload if browser scanning not available
            uploaded_img = st.file_uploader("Or upload QR image (fallback)", type=["png", "jpg", "jpeg"]) 

            # if the browser component returned a value, it will be available in result
            data_bytes = None
            decoded_payload_text = None
            if result:
                decoded_payload_text = result
            elif uploaded_img is not None:
                data_bytes = uploaded_img.read()

            if decoded_payload_text:
                try:
                    st.success("QR decoded (live)")
                    st.write(decoded_payload_text)
                    # payload expected to be JSON string
                    payload_obj = json.loads(decoded_payload_text)
                    identifier = payload_obj.get("id") or payload_obj.get("name")
                    ok, msg = mark_attendance(df, identifier, columns_to_mark, source_path=source_path)
                    if ok:
                        st.success(f"Marked attendance for {identifier}")
                        matches = df[(df.get('Srn', '').astype(str) == str(identifier)) | (df.get('Email', '').astype(str) == str(identifier)) | (df.get('Name', '').astype(str) == str(identifier))]
                        st.dataframe(matches)
                    else:
                        st.error(msg)
                except Exception as e:
                    st.error(f"Failed to decode or mark QR: {e}")
            elif data_bytes is not None:
                try:
                    payload = decode_qr_from_bytes(data_bytes)
                    if not payload:
                        st.error("No QR decoded from image.")
                    else:
                        st.success("QR decoded")
                        st.json(json.loads(payload))
                        payload_obj = json.loads(payload)
                        identifier = payload_obj.get("id") or payload_obj.get("name")
                        ok, msg = mark_attendance(df, identifier, columns_to_mark, source_path=source_path)
                        if ok:
                            st.success(f"Marked attendance for {identifier}")
                            matches = df[(df.get('Srn', '').astype(str) == str(identifier)) | (df.get('Email', '').astype(str) == str(identifier)) | (df.get('Name', '').astype(str) == str(identifier))]
                            st.dataframe(matches)
                        else:
                            st.error(msg)
                except Exception as e:
                    st.error(f"Failed to decode or mark QR: {e}")

        elif mode == "Export":
            st.header("Export roster with attendance")
            st.write("Download current roster with attendance columns added/updated.")
            xlsx_bytes = io.BytesIO()
            df.to_excel(xlsx_bytes, index=False, engine='openpyxl')
            xlsx_bytes.seek(0)
            st.download_button("Download XLSX", data=xlsx_bytes, file_name="roster_with_attendance.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


if __name__ == "__main__":
    main()
