# app.py (เวอร์ชันสมบูรณ์: อัปโหลด Google Drive + ปุ่มหน้าหลัก)

import streamlit as st
import pandas as pd
from datetime import datetime
import gspread 
import io 
# --- Imports สำหรับ Google Drive API ---
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload 
# ----------------------------------------

# --- 1. Global Configuration ---
# Google Sheet ID และ Worksheet Name
GOOGLE_SHEET_ID = "1E6WpIgmUBZ2bPpBxSW08ktKUKJGahmzqjVcMDfsqMec"
WORKSHEET_NAME = "FactoryAudit"

# ✅ รหัส Folder ID สำหรับเก็บไฟล์ (จากลิงก์ที่คุณให้มา)
RecievedFromFactory = r"C:\Users\onuma.l\OneDrive - Hi-Tech Apparel Co.,Ltd\PDU - Product Development Unit\PDU Information\10-Heat Transfer Project\07-Heat Transfer Audit"

# กำหนดเกณฑ์คะแนน
SCORE_MAPPING = {
    'OK': 3, 'PRN': 2, 'NRIC': 1, 'Blank': 0 
}

MAIN_CATEGORIES = [
    "1. People (บุคลากร)", "2. Machine (เครื่องจักร)", "3. Materials (วัสดุ)", "4. Method (วิธีการ)", 
    "5. Measurement (การวัด)", "6. Environment (สภาพแวดล้อม)", "7. Documentation & Control (เอกสารและการควบคุม)"
]

CATEGORY_ID_MAP = {
    '1': "1. People (บุคลากร)", '2': "2. Machine (เครื่องจักร)", '3': "3. Materials (วัสดุ)", 
    '4': "4. Method (วิธีการ)", '5': "5. Measurement (การวัด)", '6': "6. Environment (สภาพแวดล้อม)", 
    '7': "7. Documentation & Control (เอกสารและการควบคุม)"
}

def get_grade_and_description(percentage):
    if percentage >= 90:
        return 'A', 'Excellent (ดีเยี่ยม)', 'ปฏิบัติถูกต้องตามมาตรฐานทุกข้อ'
    elif percentage >= 75:
        return 'B', 'Good (ดี)', 'ปฏิบัติได้ดี มีข้อสังเกตเล็กน้อยแต่ไม่กระทบคุณภาพ'
    elif percentage >= 60:
        return 'C', 'Fair (พอใช้)', 'มีบางข้อไม่เป็นไปตามมาตรฐาน ต้องติดตามผล'
    else:
        return 'D', 'Poor (ไม่ผ่าน)', 'ไม่เป็นไปตามข้อกำหนดหลัก ต้องแก้ไขและตรวจซ้ำ'

def process_checklist_data(uploaded_file):
    try:
        uploaded_file.seek(0)
        if uploaded_file.name.endswith('.xlsx'):
            df_metadata = pd.read_excel(uploaded_file, nrows=15, header=None)
        else:
            df_metadata = pd.read_csv(uploaded_file, nrows=15, header=None)
        
        metadata_raw = {
            'Date_of_Audit': df_metadata.iloc[3, 2],
            'Time_Shift': df_metadata.iloc[3, 5],
            'Factory': df_metadata.iloc[4, 2],
            'Work_Area': df_metadata.iloc[4, 5],
            'Observed_Personnel': df_metadata.iloc[5, 2],
            'Supervisor': df_metadata.iloc[5, 5],
            'Machine_ID': df_metadata.iloc[6, 2],
            'Auditor': df_metadata.iloc[6, 5],
            'File_Name': uploaded_file.name
        }
    except Exception as e:
        metadata_raw = {k: 'N/A' for k in ['Date_of_Audit', 'Time_Shift', 'Factory', 'Work_Area', 'Observed_Personnel', 'Supervisor', 'Machine_ID', 'Auditor']}
        metadata_raw['File_Name'] = uploaded_file.name

    try:
        uploaded_file.seek(0) 
        col_indices = [1, 2, 3, 5, 6, 7, 8] 
        if uploaded_file.name.endswith('.xlsx'):
            df_audit = pd.read_excel(uploaded_file, header=13, usecols=col_indices)
        else:
            df_audit = pd.read_csv(uploaded_file, header=13, usecols=col_indices)
        
        df_audit.columns = ['หัวข้อ', 'เลขข้อ', 'คำถาม', 'OK', 'PRN', 'NRIC', 'หมายเหตุ']
        df_audit = df_audit.dropna(subset=['คำถาม']).copy() 
        df_audit['Category_ID'] = df_audit['เลขข้อ'].astype(str).str.split('.', expand=True)[0]
        df_audit = df_audit[df_audit['Category_ID'].isin(CATEGORY_ID_MAP.keys())].reset_index(drop=True)
        df_audit['หัวข้อ'] = df_audit['หัวข้อ'].ffill() 
        
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการอ่านไฟล์: {e}")
        return None, None, None

    df_audit['Score'] = 0
    df_audit['Scoring Category'] = 'Blank'

    for index, row in df_audit.iterrows():
        if pd.notna(row['OK']) and row['OK'] != "":
            df_audit.loc[index, 'Score'] = SCORE_MAPPING['OK']
            df_audit.loc[index, 'Scoring Category'] = 'OK'
        elif pd.notna(row['PRN']) and row['PRN'] != "":
            df_audit.loc[index, 'Score'] = SCORE_MAPPING['PRN']
            df_audit.loc[index, 'Scoring Category'] = 'PRN'
        elif pd.notna(row['NRIC']) and row['NRIC'] != "":
            df_audit.loc[index, 'Score'] = SCORE_MAPPING['NRIC']
            df_audit.loc[index, 'Scoring Category'] = 'NRIC'

    df_audited_q = df_audit[df_audit['Score'] > 0]
    total_possible_questions = len(df_audited_q) 
    actual_score = df_audited_q['Score'].sum()
    total_possible_score = total_possible_questions * SCORE_MAPPING['OK'] 
    percentage = (actual_score / total_possible_score) * 100 if total_possible_score > 0 else 0
    grade, grade_level, description = get_grade_and_description(percentage)

    group_scores_detailed = {}
    if 'Category_ID' in df_audited_q.columns:
        for category_id, group_df in df_audited_q.groupby('Category_ID'):
            group_full_name = CATEGORY_ID_MAP.get(category_id, 'Unknown')
            group_name = group_full_name.split('.', 1)[-1].strip().replace(' ', '_').replace('/', '_').replace('&', '').strip()
            group_score = group_df['Score'].sum()
            max_group_score = len(group_df) * SCORE_MAPPING['OK']
            group_remarks_list = group_df['หมายเหตุ'].dropna().tolist()
            group_remarks_text = " / ".join(group_remarks_list)
            
            group_scores_detailed[f'Score_{group_name}'] = f"{group_score}/{max_group_score}"
            group_scores_detailed[f'Score_{group_name}_Actual'] = group_score
            group_scores_detailed[f'Score_{group_name}_Max'] = max_group_score
            group_scores_detailed[f'Remarks_{group_name}'] = group_remarks_text
            
    final_summary = {
        'Timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'Date_of_Audit': metadata_raw['Date_of_Audit'],
        'Time_Shift': metadata_raw['Time_Shift'],
        'Factory': metadata_raw['Factory'],
        'Work_Area': metadata_raw['Work_Area'],
        'Observed_Personnel': metadata_raw['Observed_Personnel'],
        'Supervisor': metadata_raw['Supervisor'],
        'Machine_ID': metadata_raw['Machine_ID'],
        'Auditor': metadata_raw['Auditor'],
        'File_Name': metadata_raw['File_Name'],
        'Actual_Score': actual_score,
        'Score_Percentage_pct': round(percentage, 2),
        'Grade': grade,
        'Grade_Level': grade_level,
        'Description': description,
        'Total_Questions_Audited': total_possible_questions,
        'Max_Possible_Score': total_possible_score,
    }
    final_summary.update(group_scores_detailed)
    return df_audit, final_summary, df_audited_q

# --- 3. GOOGLE SHEETS & DRIVE INTEGRATION ---

def upload_file_to_drive(uploaded_file, folder_id):
    """อัปโหลดไฟล์ไปยัง Google Drive"""
    try:
        credentials_dict = st.secrets["gcp_service_account"]
        SCOPES = ['https://www.googleapis.com/auth/drive.file']
        credentials = service_account.Credentials.from_service_account_info(credentials_dict, scopes=SCOPES)
        
        drive_service = build('drive', 'v3', credentials=credentials)
        
        file_metadata = {
            'name': uploaded_file.name,
            'parents': [folder_id]
        }

        # เตรียมไฟล์สำหรับ Upload
        fh = io.BytesIO(uploaded_file.getvalue())
        mimetype = uploaded_file.type if uploaded_file.type else 'application/octet-stream'
        media = MediaIoBaseUpload(fh, mimetype=mimetype, resumable=True)

        # สั่ง Upload (supportsAllDrives=True ช่วยให้รองรับ Shared Drive)
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True 
        ).execute()
        
        return True, f"บันทึกไฟล์ลง Drive สำเร็จ (File ID: {file.get('id')})"
    except Exception as e:
        return False, f"❌ Error GDrive Upload: {e}"

def automate_storage_and_save(summary_data, uploaded_file):
    
    # 1. อัปโหลดไฟล์ไปยัง Google Drive
    drive_success, drive_message = upload_file_to_drive(uploaded_file, GDRIVE_FOLDER_ID)
    
    if not drive_success:
        return False, drive_message 

    # 2. บันทึกข้อมูลสรุปไปยัง Google Sheets
    try:
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        spreadsheet = gc.open_by_key(GOOGLE_SHEET_ID)
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME) 

        headers = list(summary_data.keys())
        values = []
        for v in summary_data.values():
            if isinstance(v, (pd.Timestamp, datetime)):
                values.append(str(v))
            elif hasattr(v, 'item'):
                values.append(v.item())
            else:
                values.append(v)

        if worksheet.row_values(1) != headers:
            worksheet.append_row(headers)

        worksheet.append_row(values)
        
        sheet_message = f"บันทึกข้อมูลสำเร็จใน Sheet: **{WORKSHEET_NAME}**"
        final_message = f"✅ **เสร็จสมบูรณ์:** {drive_message} <br> {sheet_message}"
        return True, final_message

    except KeyError:
        return False, "❌ **Error:** กรุณาตั้งค่า `secrets.toml` ให้ถูกต้อง!"
    except Exception as e:
        return False, f"❌ Error GSheets Save: {e}"

# --- 4. Streamlit UI ---

st.set_page_config(layout="wide", page_title="Heat Transfer Audit App")
st.title("🔥 ระบบประเมิน Heat Transfer Process Audit")
st.markdown("---")

# 1. Upload
st.header("1. Upload Heat Transfer Checklist File")
uploaded_file = st.file_uploader(
    "อัปโหลดไฟล์ที่กรอกข้อมูลแล้ว (.xlsx หรือ .csv)",
    type=["xlsx", "csv"]
)

if uploaded_file is not None:
    st.success(f"Upload successful: **{uploaded_file.name}**")
    
    # 2. Processing
    df_audit_result, summary, df_audited_q = process_checklist_data(uploaded_file)

    if df_audit_result is not None:
        st.markdown("---")
        # 2. Overall Score
        st.header("2. Overall Score Evaluation (ผลการประเมินคะแนนรวม)")
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Actual Score", f"{summary['Actual_Score']}", f"จาก {summary['Max_Possible_Score']}")
        col2.metric("Total Score", f"{summary['Max_Possible_Score']}")
        col3.metric("Percentage", f"{summary['Score_Percentage_pct']}%")
        col4.metric("Grade", f"{summary['Grade']} ({summary['Grade_Level']})")
        st.info(f"**Description:** {summary['Description']}")
        
        st.markdown("---")
        
        # 3. Metadata Display (Table)
        st.header("3. Information (ข้อมูลทั่วไป)")
        METADATA_HEADERS_MAP = {
            'Date of Audit (วันที่ตรวจสอบ)': 'Date of Audit\n(วันที่ตรวจสอบ)',
            'Time of Audit (เวลา/รอบการทำงาน)': 'Time of Audit\n(เวลา/รอบการทำงาน)',
            'Factory (โรงงาน)': 'Factory\n(โรงงาน)',
            'Work Area (พื้นที่ตรวจสอบ)': 'Work Area\n(พื้นที่ตรวจสอบ)',
            'Machine ID (หมายเลขเครื่องจักร)': 'Machine ID\n(หมายเลขเครื่องจักร)',
            'Auditor (ผู้ตรวจสอบ)': 'Auditor\n(ผู้ตรวจสอบ)',
            'Observed Personnel (ผู้ปฏิบัติงาน)': 'Observed Personnel\n(ผู้ปฏิบัติงาน)',
            'Supervisor (หัวหน้างาน)': 'Supervisor\n(หัวหน้างาน)',
            'File Name (ชื่อไฟล์ที่อัปโหลด)': 'File Name\n(ชื่อไฟล์ที่อัปโหลด)',
        }
        metadata_map = {
            'Date of Audit (วันที่ตรวจสอบ)': summary.get('Date_of_Audit'),
            'Time of Audit (เวลา/รอบการทำงาน)': summary.get('Time_Shift'),
            'Factory (โรงงาน)': summary.get('Factory'),
            'Work Area (พื้นที่ตรวจสอบ)': summary.get('Work_Area'),
            'Machine ID (หมายเลขเครื่องจักร)': summary.get('Machine_ID'),
            'Auditor (ผู้ตรวจสอบ)': summary.get('Auditor'),
            'Observed Personnel (ผู้ปฏิบัติงาน)': summary.get('Observed_Personnel'),
            'Supervisor (หัวหน้างาน)': summary.get('Supervisor'),
            'File Name (ชื่อไฟล์ที่อัปโหลด)': summary.get('File_Name'),
        }
        df_metadata_table = pd.DataFrame(metadata_map.items(), columns=['Internal Header', 'ข้อมูล'])
        df_metadata_table['Header (หัวข้อ)'] = df_metadata_table['Internal Header'].apply(lambda x: METADATA_HEADERS_MAP.get(x, x))
        st.dataframe(df_metadata_table[['Header (หัวข้อ)', 'ข้อมูล']], hide_index=True, use_container_width=True)

        st.markdown("---")
        
        # 4. Summary & Details
        st.header("4. Summary & Details (รายละเอียด)")
        with st.expander("ดูตารางสรุปคะแนน 7 ด้าน", expanded=True):
            group_summary_data = []
            for category_th in MAIN_CATEGORIES:
                key_name = category_th.split('.', 1)[-1].strip().replace(' ', '_').replace('&', '').strip()
                actual = summary.get(f'Score_{key_name}_Actual', 0)
                max_score = summary.get(f'Score_{key_name}_Max', 0)
                remarks_text = summary.get(f'Remarks_{key_name}', '')
                percentage = (actual / max_score) * 100 if max_score > 0 else 0
                group_summary_data.append({
                    'Main Category': category_th.replace(' (', '\n('), 
                    'Score': f"{actual} / {max_score}", 
                    'Percentage (%)': f"{percentage:.2f}%", 
                    'Remark': remarks_text
                })
            st.dataframe(pd.DataFrame(group_summary_data), hide_index=True, use_container_width=True)

        with st.expander("ดูรายละเอียดการตรวจรายข้อ"):
            DISPLAY_COLUMNS_MAP = {
                'หัวข้อ': 'Category',
                'เลขข้อ': 'No.',
                'คำถาม': 'Question',
                'OK': 'OK',
                'PRN': 'PRN',
                'NRIC': 'NRIC',
                'หมายเหตุ': 'Remark'
            }
            df_display = df_audit_result[['หัวข้อ', 'เลขข้อ', 'คำถาม', 'OK', 'PRN', 'NRIC', 'หมายเหตุ']].copy()
            cols_to_clean = ['OK', 'PRN', 'NRIC', 'หมายเหตุ']
            df_display[cols_to_clean] = df_display[cols_to_clean].fillna('')
            df_display['หัวข้อ'] = df_display['หัวข้อ'].mask(df_display['หัวข้อ'].duplicated(), '')
            df_display = df_display.rename(columns=DISPLAY_COLUMNS_MAP)
            st.dataframe(df_display, column_order=list(DISPLAY_COLUMNS_MAP.values()), hide_index=True, use_container_width=True)

        st.markdown("---")
        
        # ----------------------------------------------------
        # 6. ACTION BUTTONS (ส่วนปุ่มหน้าหลักที่เพิ่มให้)
        # ----------------------------------------------------
        st.header("6. Actions (บันทึกผล)")
        
        col_btn1, col_btn2 = st.columns([1, 1])

        with col_btn1:
            # ปุ่มหลัก: บันทึกข้อมูล
            if st.button("💾 บันทึกข้อมูลลง Google Sheet & Drive", type="primary", use_container_width=True):
                with st.spinner('กำลังเชื่อมต่อ Google Drive และบันทึกข้อมูล...'):
                    success, message = automate_storage_and_save(summary, uploaded_file)
                if success:
                    st.success(message)
                    st.balloons()
                else:
                    st.error(message)

        with col_btn2:
            # ปุ่มเสริม: รีเซ็ตเพื่อเริ่มใหม่
            if st.button("🔄 เริ่มต้นใหม่ (Reset)", use_container_width=True):
                st.rerun()

        # ส่วนดาวน์โหลด (Backup)
        st.download_button(
            label="⬇️ Download Result CSV (สำรองข้อมูล)",
            data=df_audit_result.to_csv(index=False).encode('utf-8'),
            file_name=f"audit_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
else:
    st.info("Please upload the filled-out Excel/CSV file to begin evaluation.")
