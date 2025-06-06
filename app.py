import streamlit as st
import pandas as pd
import io
from zipfile import ZipFile

# Session state storage for memory caching
if "generated_files" not in st.session_state:
    st.session_state.generated_files = {}

REASON_TRANSLATIONS = {
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

        whs_choice = st.selectbox(
            "Select WHS Area",
            options=["BOI", "EUG", "GEG", "PDX", "SEA", "All SEA AREAs"],
        )
        whs_filtered = (
            df[df["WHS"].isin(["BOI", "EUG", "GEG", "PDX", "SEA"])]
            if whs_choice == "All SEA AREAs"
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

    selected_date = st.date_input("📅 Select the Date for Report")

    use_cache = False
    if st.session_state.generated_files:
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
        for f in uploaded_files:
            df = pd.read_excel(f) if f.name.endswith(".xlsx") else pd.read_csv(f)
            whs = df["WHS"].iloc[0] if "WHS" in df.columns else "UnknownWHS"
            team_id = (
                df["team_id"].iloc[0] if "team_id" in df.columns else "UnknownTeam"
            )
            dfs[f"{whs}-{team_id}"] = df

    for title, df in dfs.items():
        st.subheader(f"📦 {title}")
        if "result" not in df.columns or "Driver ID" not in df.columns:
            st.warning("Missing required columns in the data.")
            continue

        reason_counts = df["result"].value_counts().nlargest(3)
        top_reasons = reason_counts.index.tolist()

        # English Summary
        st.markdown("### 📝 Summary (English)")
        st.markdown(
            f"{selected_date.strftime('%Y-%m-%d')} POD failures were found. "
            f"Please train the drivers below, with a focus on the following issues:"
        )
        for reason in top_reasons:
            st.markdown(f"- {reason}")

        # Chinese Summary
        st.markdown("### 📝 总结（中文）")
        st.markdown(
            f"{selected_date.strftime('%Y-%m-%d')} 查到的POD不合格，请DSP对这些司机进行培训，"
            f"其中重点注意以下几个问题："
        )
        for reason in top_reasons:
            zh_reason = REASON_TRANSLATIONS.get(reason.strip(), reason)
            st.markdown(f"- {zh_reason}")

        st.markdown("以下为一些不合格的例子：")
        for reason in top_reasons:
            subdf = df[df["result"] == reason]
            top_driver = subdf["Driver ID"].value_counts().idxmax()
            zh_reason = REASON_TRANSLATIONS.get(reason.strip(), reason)
            row = subdf[subdf["Driver ID"] == top_driver].iloc[0]
            tno = row.get("tno", "Unknown")
            st.markdown(f"Driver {top_driver} - Parcel: `{tno}`: {zh_reason}/ {reason}")
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
