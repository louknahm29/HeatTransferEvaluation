# app.py (โค้ดฉบับสมบูรณ์สำหรับ Deploy)

import streamlit as st
import pandas as pd
from datetime import datetime
import gspread 
import io 
# --- NEW IMPORTS FOR GOOGLE DRIVE API ---
from google.oauth2 import service_account
from googleapiclient.discovery import build
# ----------------------------------------

# --- 1. Global Configuration ---
# Google Sheet ID และ Worksheet Name
GOOGLE_SHEET_ID = "1E6WpIgmUBZ2bPpBxSW08ktKUKJGahmzqjVcMDfsqMec"
WORKSHEET_NAME = "FactoryAudit"

# Google Drive Folder ID สำหรับเก็บไฟล์ที่อัปโหลด
GDRIVE_FOLDER_ID = "1lpKmazYDw907m-2sGF-MfRisNMd3lkzg"

# กำหนดเกณฑ์คะแนน
SCORE_MAPPING = {
    'OK': 3, 'PRN': 2, 'NRIC': 1, 'Blank': 0 
}

# ⚠️ กำหนด Main Categories ตามชื่อเต็มที่ใช้ในการจัดกลุ่ม ⚠️
MAIN_CATEGORIES = [
    "1. บุคลากร", "2. เครื่องจักร", "3. วัสดุ", "4. วิธีการ", 
    "5. การวัด", "6. สภาพแวดล้อม", "7. Documentation & Control"
]

def get_grade_and_description(percentage):
    """กำหนดเกรดและคำอธิบายตามเปอร์เซ็นต์คะแนนรวม"""
    if percentage >= 90:
        return 'A', 'Excellent (ดีเยี่ยม)', 'ปฏิบัติถูกต้องตามมาตรฐานทุกข้อ'
    elif percentage >= 75:
        return 'B', 'Good (ดี)', 'ปฏิบัติได้ดี มีข้อสังเกตเล็กน้อยแต่ไม่กระทบคุณภาพ'
    elif percentage >= 60:
        return 'C', 'Fair (พอใช้)', 'มีบางข้อไม่เป็นไปตามมาตรฐาน ต้องติดตามผล'
    else:
        return 'D', 'Poor (ไม่ผ่าน)', 'ไม่เป็นไปตามข้อกำหนดหลัก ต้องแก้ไขและตรวจซ้ำ'

def process_checklist_data(uploaded_file):
    """ทำความสะอาดข้อมูล, คำนวณคะแนน, และสรุปผลจากไฟล์ที่อัปโหลด"""

    # 1. Loading Metadata (โหลดข้อมูลบริบทจากส่วนหัว)
    try:
        uploaded_file.seek(0)
        
        if uploaded_file.name.endswith('.xlsx'):
            df_metadata = pd.read_excel(uploaded_file, nrows=15, header=None)
        else:
            df_metadata = pd.read_csv(uploaded_file, nrows=15, header=None)
        
        # Mapping ข้อมูลจากตำแหน่งเซลล์ในไฟล์ (อิงตาม Value Column Index)
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
        metadata_raw = {
            'Date_of_Audit': 'N/A', 'Time_Shift': 'N/A', 'Factory': 'N/A', 'Work_Area': 'N/A', 
            'Observed_Personnel': 'N/A', 'Supervisor': 'N/A', 'Machine_ID': 'N/A', 
            'Auditor': 'N/A', 'File_Name': uploaded_file.name
        }


    # 2. Loading Audit Questions
    try:
        uploaded_file.seek(0) 
        
        # Index คอลัมน์ที่ต้องการ: [1: หัวข้อ, 2: เลขข้อ, 3: คำถาม, 4: OK, 5: PRN, 6: NRIC, 7: หมายเหตุ]
        col_indices = [1, 2, 3, 4, 5, 6, 7] 
        
        if uploaded_file.name.endswith('.xlsx'):
            df_audit = pd.read_excel(uploaded_file, header=13, usecols=col_indices)
        else:
            df_audit = pd.read_csv(uploaded_file, header=13, usecols=col_indices)
        
        df_audit.columns = ['หัวข้อ', 'เลขข้อ', 'คำถาม', 'OK', 'PRN', 'NRIC', 'หมายเหตุ']
            
        df_audit = df_audit.dropna(subset=['คำถาม']).reset_index(drop=True)
        
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการอ่านไฟล์หรือโครงสร้างคอลัมน์ไม่ถูกต้อง: {e}")
        return None, None, None

    # 3. Scoring
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


    # 4. Summary and Group Scoring
    df_audited_q = df_audit[df_audit['Score'] > 0]
    total_possible_questions = len(df_audited_q) 
    actual_score = df_audited_q['Score'].sum()
    total_possible_score = total_possible_questions * SCORE_MAPPING['OK'] 
    percentage = (actual_score / total_possible_score) * 100 if total_possible_score > 0 else 0
    grade, grade_level, description = get_grade_and_description(percentage)

    # 4a. คำนวณคะแนนและ Remarks รายหมวดหมู่
    group_scores_detailed = {}
    if 'หัวข้อ' in df_audited_q.columns:
        for group, group_df in df_audited_q.groupby('หัวข้อ'):
            # NOTE: ใช้ group_name ที่ไม่มีเลขนำหน้าสำหรับคีย์ใน Dictionary
            group_name = group.split('.', 1)[-1].strip().replace(' ', '_').replace('/', '_').replace('&', '').strip() 
            group_score = group_df['Score'].sum()
            max_group_score = len(group_df) * SCORE_MAPPING['OK']
            
            group_remarks_list = group_df['หมายเหตุ'].dropna().tolist()
            group_remarks_text = "; ".join(group_remarks_list)
            
            group_scores_detailed[f'Score_{group_name}'] = f"{group_score}/{max_group_score}"
            group_scores_detailed[f'Score_{group_name}_Actual'] = group_score
            group_scores_detailed[f'Score_{group_name}_Max'] = max_group_score
            group_scores_detailed[f'Remarks_{group_name}'] = group_remarks_text
            
    
    # 4b. จัดเรียงข้อมูลตามลำดับที่ผู้ใช้ต้องการ (Final Header Structure)
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
        
        # 3. Simplified Group Scores (ตามลำดับที่ต้องการ)
        'Score_บุคลากร': group_scores_detailed.get('Score_บุคลากร', '0/0'),
        'Score_เครื่องจักร': group_scores_detailed.get('Score_เครื่องจักร', '0/0'),
        'Score_วัสดุ': group_scores_detailed.get('Score_วัสดุ', '0/0'),
        'Score_วิธีการ': group_scores_detailed.get('Score_วิธีการ', '0/0'),
        'Score_การวัด': group_scores_detailed.get('Score_การวัด', '0/0'),
        'Score_สภาพแวดล้อม': group_scores_detailed.get('Score_สภาพแวดล้อม', '0/0'),
        'Score_Documentation_Control': group_scores_detailed.get('Score_Documentation_Control', '0/0'),
        
        # 4. Detailed Scores (ข้อมูลเชิงลึกที่เหลือ)
        'Total_Questions_Audited': total_possible_questions,
        'Max_Possible_Score': total_possible_score,
    }
    
    final_summary.update(group_scores_detailed)


    return df_audit, final_summary, df_audited_q

# --- 3. GOOGLE SHEETS & DRIVE INTEGRATION ---

def upload_file_to_drive(uploaded_file, folder_id):
    """ฟังก์ชันอัปโหลดไฟล์ไปยัง Google Drive โดยใช้ Service Account"""
    try:
        credentials_dict = st.secrets["gcp_service_account"]
        SCOPES = ['https://www.googleapis.com/auth/drive.file']
        credentials = service_account.Credentials.from_service_account_info(credentials_dict, scopes=SCOPES)
        
        drive_service = build('drive', 'v3', credentials=credentials)
        
        file_metadata = {
            'name': uploaded_file.name,
            'parents': [folder_id]
        }
        uploaded_file.seek(0)
        media_body = io.BytesIO(uploaded_file.getvalue())

        file = drive_service.files().create(
            body=file_metadata,
            media_body=media_body,
            fields='id'
        ).execute()
        
        return True, f"บันทึกไฟล์สำเร็จ (File ID: {file.get('id')})"
    except Exception as e:
        return False, f"❌ Error GDrive Upload: {e}"

def automate_storage_and_save(summary_data, uploaded_file):
    """จัดการการจัดเก็บไฟล์ (Drive) และบันทึกข้อมูล (Sheets)"""
    
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
        values = list(summary_data.values())

        if worksheet.row_values(1) != headers:
            worksheet.append_row(headers)

        worksheet.append_row(values)
        
        sheet_message = f"บันทึกข้อมูลสำเร็จใน Sheet: **{WORKSHEET_NAME}**"
        final_message = f"✅ **การทำงานเสร็จสมบูรณ์:** {drive_message}. {sheet_message}"
        return True, final_message

    except KeyError:
        return False, "❌ **Error:** กรุณาตั้งค่า `secrets.toml` และ Service Account Key ให้ถูกต้อง!"
    except Exception as e:
        return False, f"❌ Error GSheets Save: {e}"


# --- 4. Streamlit UI (แสดงผลตาม Layout ใหม่) ---

st.set_page_config(layout="wide", page_title="Heat Transfer Audit App")
st.title("🔥 ระบบประเมิน Heat Transfer Process Audit")
st.markdown("---")

# 1. อัปโหลดไฟล์ Heat Transfer Checklist
st.header("1. อัปโหลดไฟล์ Heat Transfer Checklist")
uploaded_file = st.file_uploader(
    "อัปโหลดไฟล์ที่กรอกข้อมูลแล้ว (.xlsx หรือ .csv)",
    type=["xlsx", "csv"]
)

if uploaded_file is not None:
    st.success(f"อัปโหลดไฟล์ **{uploaded_file.name}** สำเร็จ! เริ่มประมวลผล...")

    # 2. Processing
    df_audit_result, summary, df_audited_q = process_checklist_data(uploaded_file)

    if df_audit_result is not None:
        st.markdown("---")
        # 2. ผลการประเมินคะแนนรวม
        st.header("2. ผลการประเมินคะแนนรวม")
        
        col1, col2, col3 = st.columns(3)
        col1.metric("คะแนนที่ทำได้", f"{summary['Actual_Score']}", f"จาก {summary['Max_Possible_Score']} คะแนน")
        col2.metric("เปอร์เซ็นต์รวม", f"{summary['Score_Percentage_pct']}%")
        col3.metric("เกรดรวม", f"{summary['Grade']} ({summary['Grade_Level']})")

        st.info(f"**คำอธิบายผลการประเมิน:** {summary['Description']}")
        
        st.markdown("---")
        
        ### 3. ตารางสรุปคะแนน 7 ด้าน
        st.header("3. สรุปคะแนนตามด้านการตรวจสอบ (7 Categories)")
        
        group_summary_data = []
        for category_th in MAIN_CATEGORIES:
            # NOTE: ใช้วิธีดึงชื่อหมวดหมู่ที่ไม่มีเลขนำหน้าสำหรับคีย์ใน Dictionary
            key_name = category_th.split('.', 1)[-1].strip().replace(' ', '_').replace('&', '').strip() 
            
            actual = summary.get(f'Score_{key_name}_Actual', 0)
            max_score = summary.get(f'Score_{key_name}_Max', 0)
            remarks_text = summary.get(f'Remarks_{key_name}', '')
            
            percentage = (actual / max_score) * 100 if max_score > 0 else 0
            
            group_summary_data.append({
                'Main Category': category_th,
                'คะแนนที่ได้': f"{actual} / {max_score}",
                'เปอร์เซ็นต์ (%)': f"{percentage:.2f}%",
                'หมายเหตุ': remarks_text
            })

        df_group_summary = pd.DataFrame(group_summary_data)
        st.dataframe(
            df_group_summary,
            hide_index=True,
            use_container_width=True
        )
        
        st.markdown("---")
        
        ### 4. ข้อมูลทั่วไป (Metadata)
        
        st.header("4. ข้อมูลทั่วไป")
        
        # จัด Metadata ในรูปแบบตาราง 2 คอลัมน์
        metadata_map = {
            'วันที่ตรวจสอบ': summary.get('Date_of_Audit'),
            'เวลา/รอบการทำงาน': summary.get('Time_Shift'),
            'โรงงาน': summary.get('Factory'),
            'พื้นที่ตรวจสอบ': summary.get('Work_Area'),
            'Machine ID/เครื่องจักร': summary.get('Machine_ID'),
            'ผู้ตรวจสอบ': summary.get('Auditor'),
            'ผู้ปฏิบัติงาน': summary.get('Observed_Personnel'),
            'หัวหน้างาน': summary.get('Supervisor'),
            'ชื่อไฟล์ที่อัปโหลด': summary.get('File_Name'),
        }
        
        df_metadata_table = pd.DataFrame(metadata_map.items(), columns=['หัวข้อ', 'ข้อมูล'])
        st.dataframe(df_metadata_table, hide_index=True, use_container_width=True)

        st.markdown("---")
        
        ### 5. รายละเอียดการประเมินรายข้อ (แสดงเหมือนแบบฟอร์ม)
        st.header("5. รายละเอียดการประเมินรายข้อ")
        
        # เตรียม DataFrame สำหรับแสดงผล
        df_display = df_audit_result[['หัวข้อ', 'เลขข้อ', 'คำถาม', 'OK', 'PRN', 'NRIC', 'หมายเหตุ']].copy()
        
        # 5a. ล้างค่าในคอลัมน์ 'หัวข้อ' ออก เพื่อให้แสดงเพียงครั้งเดียว
        df_display['หัวข้อ'] = df_display['หัวข้อ'].mask(df_display['หัวข้อ'].duplicated(), '')
        
        st.dataframe(
            df_display,
            column_order=['หัวข้อ', 'เลขข้อ', 'คำถาม', 'OK', 'PRN', 'NRIC', 'หมายเหตุ'],
            hide_index=True,
            use_container_width=True
        )

        st.markdown("---")
        
        ### 6. บันทึกผลสรุป
        st.header("6. บันทึกผลสรุป")
        
        if st.button("บันทึกผลสรุปและจัดเก็บไฟล์ทั้งหมด"):
            # เรียกใช้ฟังก์ชันรวมเพื่ออัปโหลดไฟล์และบันทึกข้อมูล
            success, message = automate_storage_and_save(summary, uploaded_file)
            if success:
                st.success(message)
                st.write("ข้อมูลทั้งหมด (Metadata, คะแนนรวม, คะแนน 7 ด้าน) ได้ถูกบันทึกใน Google Sheet และไฟล์ต้นฉบับได้ถูกจัดเก็บใน Google Drive เรียบร้อยแล้ว")
                
            else:
                st.error(message)

        # 7. Download Processed Data (Optional)
        st.download_button(
            label="⬇️ ดาวน์โหลดผลการประเมินทั้งหมด (CSV)",
            data=df_audit_result.to_csv(index=False).encode('utf-8'),
            file_name=f"audit_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
else:
    st.info("กรุณาอัปโหลดไฟล์ Excel/CSV ที่กรอกข้อมูลแล้ว เพื่อเริ่มต้นการประเมิน")
