import streamlit as st
import pandas as pd
import io
from zipfile import ZipFile

# Session state storage for memory caching
if "generated_files" not in st.session_state:
    st.session_state.generated_files = {}

REASON_TRANSLATIONS_ZH = {
    "No Address Info": "地址不清",
    "Location Not Clear": "位置不明确",
    "No Clear Shipping Label": "运单标签不清晰",
    "Public or Unsafe Area": "公共或不安全区域",
    "Invalid Mailbox Delivery": "投递至无效邮箱",
    "Leave Outside of Building": "包裹留在建筑外",
    "Wrong Address": "地址错误",
    "Wrong Parcel Photo": "包裹照片错误",
    "No POD": "无POD照片",
    "Inappropriate Delivery": "投递方式不当",
}

REASON_TRANSLATIONS_ES = {
    "No Address Info": "Dirección no clara",
    "Location Not Clear": "Ubicación poco clara",
    "No Clear Shipping Label": "Etiqueta de envío ilegible",
    "Public or Unsafe Area": "Área pública o peligrosa",
    "Invalid Mailbox Delivery": "Entrega en buzón no válido",
    "Leave Outside of Building": "Paquete dejado fuera del edificio",
    "Wrong Address": "Dirección incorrecta",
    "Wrong Parcel Photo": "Foto de paquete incorrecta",
    "No POD": "Sin foto de entrega (POD)",
    "Inappropriate Delivery": "Entrega inapropiada",
}


def pod_failed_report_processor():
    st.header("POD Failed Report Processor")
    uploaded_file = st.file_uploader(
        "Upload a file", type=["csv", "xlsx"], key="pod_upload"
    )

    if uploaded_file:
        filename_no_ext = uploaded_file.name.rsplit(".", 1)[0]
        df = (
            pd.read_excel(uploaded_file)
            if uploaded_file.name.endswith(".xlsx")
            else pd.read_csv(uploaded_file)
        )
        df.columns = df.columns.str.strip()
        df = df[df["VALID POD"].astype(str).str.upper() == "N"]

        whs_choice = st.selectbox(
            "Select WHS Area",
            options=["BOI", "EUG", "GEG", "PDX", "SEA", "MSO", "BIL", "All SEA WHS"],
        )
        all_whs = ["BOI", "EUG", "GEG", "PDX", "SEA", "MSO", "BIL"]

        whs_filtered = (
            df[df["WHS"].isin(all_whs)]
            if whs_choice == "All WHS"
            else df[df["WHS"] == whs_choice]
        )

        unique_teams = sorted(whs_filtered["team_id"].dropna().unique())
        team_ids_selected = st.multiselect(
            "Select team_id(s)",
            options=["All"] + list(map(str, unique_teams)),
            default=["All"],
        )

        if st.button("Generate Files"):
            zip_buffer = io.BytesIO()
            with ZipFile(zip_buffer, mode="w") as zf:
                selected_df = whs_filtered.copy()
                if "All" not in team_ids_selected:
                    selected_df = selected_df[
                        selected_df["team_id"].astype(str).isin(team_ids_selected)
                    ]

                grouped = selected_df.groupby(["WHS", "team_id"])
                st.session_state.generated_files = {}

                for (whs, team_id), group in grouped:
                    outname = f"{whs}{team_id}_{filename_no_ext}_PODfailed.xlsx"
                    out_bytes = io.BytesIO()
                    group.to_excel(out_bytes, index=False)
                    zf.writestr(outname, out_bytes.getvalue())
                    st.session_state.generated_files[outname] = group

            st.download_button(
                "Download All Files (ZIP)",
                zip_buffer.getvalue(),
                "PODfailed_exports.zip",
                "application/zip",
            )


def display_images(row):
    pods = [row.get(f"pod_{i+1}") for i in range(6)]
    pods = [url for url in pods if isinstance(url, str) and url.startswith("http")]
    cols = st.columns(3)
    for i, pod_url in enumerate(pods):
        cols[i % 3].image(pod_url, use_container_width=True)


def pod_reason_explanation():
    st.header("POD Fail Reason Explanation")

    # 1) Date selection
    selected_date = st.date_input("📅 Select the Date for Report")

    # 2) Use cache or upload
    use_cache = False
    if st.session_state.get("generated_files"):
        use_cache = st.radio("Use files from memory cache?", ["Yes", "No"]) == "Yes"

    dfs = {}
    if use_cache:
        dfs = st.session_state.generated_files
    else:
        uploaded_files = st.file_uploader(
            "Upload multiple files",
            accept_multiple_files=True,
            type=["csv", "xlsx"],
            key="reason_upload",
        )
        if uploaded_files:
            for f in uploaded_files:
                df = pd.read_excel(f) if f.name.endswith(".xlsx") else pd.read_csv(f)
                dfs[f.name] = df

    if not dfs:
        st.info("Please upload files or use the memory cache first.")
        return

    # 3) Combine all dataframes for global filtering
    combined_list = []
    for title, df in dfs.items():
        df = df.copy()
        df["__source__"] = title  # optional info source
        combined_list.append(df)

    combined_df = pd.concat(combined_list, ignore_index=True)

    # Basic column checks
    if "result" not in combined_df.columns or "Driver ID" not in combined_df.columns:
        st.warning("Your data must contain 'result' and 'Driver ID' columns.")
        return

    # 4) Team (DSP) selection — single choice, default All
    if "team_id" in combined_df.columns:
        team_ids = combined_df["team_id"].dropna().astype(str).unique().tolist()
        team_ids = sorted(team_ids)
        team_choice = st.selectbox(
            "Select DSP / Team (team_id)",
            options=["All"] + team_ids,
            index=0,
        )
    else:
        team_choice = "All"

    # 5) Build reason list *based on the selected team*
    if team_choice == "All" or "team_id" not in combined_df.columns:
        df_for_reasons = combined_df
    else:
        df_for_reasons = combined_df[combined_df["team_id"].astype(str) == team_choice]

    if df_for_reasons.empty:
        st.warning("No POD records found for the selected team.")
        return

    reason_values = df_for_reasons["result"].dropna().astype(str).unique().tolist()
    reason_values = sorted(reason_values)

    reason_choice = st.selectbox(
        "Select POD Fail Reason",
        options=["All"] + reason_values,
        index=0,
    )

    # 6) Filter button
    if not st.button("Filter"):
        return

    # Apply filters to the full combined df
    filtered = combined_df.copy()

    if "team_id" in filtered.columns and team_choice != "All":
        filtered = filtered[filtered["team_id"].astype(str) == team_choice]

    if reason_choice != "All":
        filtered = filtered[filtered["result"].astype(str) == reason_choice]

    if filtered.empty:
        st.warning("No POD records match the selected team and reason.")
        return

    # 7) Reason counts for summary (after filters)
    reason_counts = filtered["result"].value_counts()

    # Helper: team labels in three languages
    if team_choice == "All":
        team_label_en = "all teams"
        team_label_zh = "所有团队"
        team_label_es = "todos los equipos"
    else:
        team_label_en = f"team {team_choice}"
        team_label_zh = f"团队 {team_choice}"
        team_label_es = f"equipo {team_choice}"

    date_str = selected_date.strftime("%Y-%m-%d")

    # 8) English Summary
    st.markdown("### 📝 Summary (English)")
    st.markdown(
        f"POD inspection found {team_label_en} had POD failures on {date_str}. "
        f"Please train the drivers below, with a focus on the following issues:"
    )
    for reason, count in reason_counts.items():
        st.markdown(f"- {reason}: **{count}** cases")

    # 9) Chinese Summary
    st.markdown("### 📝 总结（中文）")
    st.markdown(
        f"POD抽检发现 {date_str} {team_label_zh} 存在POD不合格情况，"
        f"请对以下司机进行培训，重点关注以下问题："
    )
    for reason, count in reason_counts.items():
        zh_reason = REASON_TRANSLATIONS_ZH.get(str(reason).strip(), str(reason))
        st.markdown(f"- {zh_reason}：**{count}** 次")

    # 10) Spanish Summary
    st.markdown("### 📝 Resumen (Español)")
    st.markdown(
        f"La inspección de POD encontró fallas de POD para {team_label_es} el {date_str}. "
        f"Por favor capaciten a los conductores indicados abajo, con enfoque en los siguientes problemas:"
    )
    for reason, count in reason_counts.items():
        es_reason = REASON_TRANSLATIONS_ES.get(str(reason).strip(), str(reason))
        st.markdown(f"- {es_reason}: **{count}** casos")

    st.markdown("---")

    # 11) Display all filtered PODs: driver, reason, POD (no click/expander)
    st.markdown("### 🚚 Driver Details and POD Examples")

    # Sort by Driver ID then tno for nicer grouping
    if "tno" in filtered.columns:
        filtered = filtered.sort_values(by=["Driver ID", "tno"])
    else:
        filtered = filtered.sort_values(by=["Driver ID"])

    current_driver = None

    for _, row in filtered.iterrows():
        driver_id = row.get("Driver ID", "Unknown")
        tno = row.get("tno", "Unknown")
        result = row.get("result", "")

        # New driver header
        if driver_id != current_driver:
            current_driver = driver_id
            st.markdown(f"#### Driver {driver_id}")

        st.markdown(f"- Parcel `{tno}` — {result}")
        display_images(row)

    st.markdown("---")


# Sidebar navigation
st.sidebar.title("Navigation")
app_mode = st.sidebar.selectbox(
    "Choose a function", ["POD Failed Report Processor", "POD Reason Explanation"]
)

if app_mode == "POD Failed Report Processor":
    pod_failed_report_processor()
elif app_mode == "POD Reason Explanation":
    pod_reason_explanation()
