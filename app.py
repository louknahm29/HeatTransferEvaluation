# app.py (โค้ดฉบับสมบูรณ์สำหรับ Deploy)

import streamlit as st
import pandas as pd
from datetime import datetime
import gspread 
import io 

# --- 1. Global Configuration ---
# Google Sheet ID ที่ดึงมาจาก URL
GOOGLE_SHEET_ID = "1E6WpIgmUBZ2bPpBxSW08ktKUKJGahmzqjVcMDfsqMec"
# ชื่อ Worksheet ภายใน Google Sheet ที่ต้องการบันทึกข้อมูล
WORKSHEET_NAME = "FactoryAudit"

# กำหนดเกณฑ์คะแนน
SCORE_MAPPING = {
    'OK': 3,    
    'PRN': 2,   
    'NRIC': 1,  
    'Blank': 0 
}

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

    # 1. Loading Metadata (โค้ดส่วนนี้ยังคงเดิม)
    try:
        uploaded_file.seek(0)
        
        if uploaded_file.name.endswith('.xlsx'):
            df_metadata = pd.read_excel(uploaded_file, nrows=8, header=None)
        else:
            df_metadata = pd.read_csv(uploaded_file, nrows=8, header=None)
        
        metadata = {
            'Date_of_Audit': df_metadata.iloc[2, 1],
            'Time_Shift': df_metadata.iloc[2, 4],
            'Factory': df_metadata.iloc[3, 1],
            'Work_Area': df_metadata.iloc[3, 4],
            'Observed_Personnel': df_metadata.iloc[4, 1],
            'Supervisor': df_metadata.iloc[4, 4],
            'Machine_ID': df_metadata.iloc[5, 1],
            'Auditor': df_metadata.iloc[5, 4],
            'File_Name': uploaded_file.name
        }
    except Exception as e:
        st.warning(f"ไม่สามารถดึงข้อมูล Metadata จากส่วนหัวของไฟล์ได้: {e}. ใช้ค่าว่างแทน")
        metadata = {
            'Date_of_Audit': 'N/A', 'Time_Shift': 'N/A', 'Factory': 'N/A', 'Work_Area': 'N/A', 
            'Observed_Personnel': 'N/A', 'Supervisor': 'N/A', 'Machine_ID': 'N/A', 
            'Auditor': 'N/A', 'File_Name': uploaded_file.name
        }


    # 2. Loading Audit Questions (โค้ดส่วนนี้ยังคงเดิม)
    try:
        uploaded_file.seek(0) 
        
        col_indices = [1, 4, 5, 6, 7, 8] # Index คอลัมน์ที่ต้องการ
        
        if uploaded_file.name.endswith('.xlsx'):
            df_audit = pd.read_excel(
                uploaded_file, header=13,
                usecols=col_indices
            )
        else:
            df_audit = pd.read_csv(
                uploaded_file, header=13,
                usecols=col_indices
            )
        
        df_audit.columns = ['หัวข้อ', 'คำถาม', 'OK', 'PRN', 'NRIC', 'หมายเหตุ']
            
        df_audit = df_audit.dropna(subset=['คำถาม']).reset_index(drop=True)
        
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการอ่านไฟล์หรือโครงสร้างคอลัมน์ไม่ถูกต้อง: {e}")
        st.info("โปรดตรวจสอบว่าไฟล์ที่อัปโหลดมีโครงสร้างคอลัมน์ตามที่กำหนด")
        return None, None, None

    # 3. Scoring: คำนวณคะแนนในแต่ละข้อ (โค้ดส่วนนี้ยังคงเดิม)
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


    # 4. Summary and Group Scoring (โค้ดส่วนนี้ยังคงเดิม)
    df_audited_q = df_audit[df_audit['Score'] > 0]
    total_possible_questions = len(df_audited_q) 
    total_possible_score = total_possible_questions * SCORE_MAPPING['OK'] 
    actual_score = df_audited_q['Score'].sum()

    percentage = (actual_score / total_possible_score) * 100 if total_possible_score > 0 else 0
    grade, grade_level, description = get_grade_and_description(percentage)

    # คำนวณคะแนนรายหมวดหมู่ (Group Scores) 
    group_scores = {}
    if 'หัวข้อ' in df_audited_q.columns:
        for group, group_df in df_audited_q.groupby('หัวข้อ'):
            group_name = group.split('.', 1)[-1].strip().replace(' ', '_').replace('/', '_')
            group_score = group_df['Score'].sum()
            max_group_score = len(group_df) * SCORE_MAPPING['OK']
            
            # สร้าง 2 คอลัมน์ต่อ 1 หมวดหมู่: Score_หมวดหมู่_Actual และ Score_หมวดหมู่_Max
            group_scores[f'Score_{group_name}_Actual'] = group_score
            group_scores[f'Score_{group_name}_Max'] = max_group_score
    
    # รวม Metadata, Summary และ Group Scores เข้าด้วยกัน
    summary_data = {
        'Timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        **metadata, 
        
        # คะแนนรวม
        'Total_Questions_Audited': total_possible_questions,
        'Actual_Score': actual_score,
        'Max_Possible_Score': total_possible_score,
        'Score_Percentage_pct': round(percentage, 2),
        'Grade': grade,
        'Grade_Level': grade_level,
        'Description': description,
        
        # คะแนนรายหมวดหมู่ (Group Scores)
        **group_scores 
    }

    return df_audit, summary_data, df_audited_q

# --- 3. Google Sheets Integration ---
def save_to_google_sheet(summary_data):
    """บันทึกข้อมูลสรุปไปยัง Google Sheet ที่ระบุ"""
    try:
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        
        spreadsheet = gc.open_by_key(GOOGLE_SHEET_ID)
        worksheet = spreadsheet.worksheet(WORKSHEET_NAME) 

        headers = list(summary_data.keys())
        values = list(summary_data.values())

        if worksheet.row_values(1) != headers:
            worksheet.append_row(headers)

        worksheet.append_row(values)
        return True, f"บันทึกข้อมูลสำเร็จใน Google Sheet (Worksheet: **{WORKSHEET_NAME}**)"

    except KeyError:
        return False, "❌ **Error:** กรุณาตั้งค่า `secrets.toml` และ Service Account Key ให้ถูกต้อง!"
    except gspread.WorksheetNotFound:
        return False, f"❌ **Error:** ไม่พบ Worksheet ชื่อ '{WORKSHEET_NAME}' ใน Google Sheet ID ที่กำหนด!"
    except Exception as e:
        return False, f"❌ เกิดข้อผิดพลาดในการบันทึก Google Sheet: {e}"

# --- 4. Streamlit UI (*** ส่วนที่แก้ไขและเพิ่มเติมตารางสรุป 7 ด้าน ***) ---

st.set_page_config(layout="wide", page_title="Heat Transfer Audit App")
st.title("🔥 ระบบประเมิน Heat Transfer Process Audit")
st.markdown("---")

# 1. File Uploader
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
        st.header("2. ผลการประเมินคะแนนรวม")
        
        # แสดงผลสรุปคะแนนรวม (Metric Boxes)
        col1, col2, col3 = st.columns(3)
        col1.metric("คะแนนที่ทำได้", f"{summary['Actual_Score']}", f"จาก {summary['Max_Possible_Score']} คะแนน")
        col2.metric("เปอร์เซ็นต์รวม", f"{summary['Score_Percentage_pct']}%")
        col3.metric("เกรดรวม", f"{summary['Grade']} ({summary['Grade_Level']})")

        st.info(f"**คำอธิบายผลการประเมิน:** {summary['Description']}")
        
        st.markdown("---")
        
        ### 3. ตารางสรุปคะแนน 7 ด้าน (New Feature)
        st.header("3. สรุปคะแนนตามด้านการตรวจสอบ (7 Categories)")
        
        # 3a. สร้าง DataFrame สำหรับแสดงผล
        group_summary_data = []
        for key, value in summary.items():
            if key.startswith('Score_') and key.endswith('_Actual'):
                category_name = key.replace('Score_', '').replace('_Actual', '').replace('_', ' ')
                max_key = key.replace('_Actual', '_Max')
                
                actual = value
                max_score = summary.get(max_key, 0)
                
                percentage = (actual / max_score) * 100 if max_score > 0 else 0
                
                group_summary_data.append({
                    'ด้านที่ตรวจสอบ (Category)': category_name.title(),
                    'คะแนนที่ได้ (Actual)': actual,
                    'คะแนนสูงสุด (Max)': max_score,
                    'เปอร์เซ็นต์ (%)': f"{percentage:.2f}%"
                })

        df_group_summary = pd.DataFrame(group_summary_data)
        st.dataframe(
            df_group_summary,
            hide_index=True,
            use_container_width=True
        )
        
        st.markdown("---")
        
        ### 4. รายละเอียดการประเมินรายข้อและ Metadata
        
        # 4a. แสดง Metadata ส่วนหัว
        st.subheader("ข้อมูลส่วนหัวของฟอร์ม (Metadata)")
        # จัด Metadata ในรูปแบบตาราง 2 คอลัมน์เพื่อให้ดูง่ายขึ้น
        metadata_display = {
            'Date of Audit': summary.get('Date_of_Audit'),
            'Time/Shift': summary.get('Time_Shift'),
            'Factory': summary.get('Factory'),
            'Work Area': summary.get('Work_Area'),
            'Machine ID': summary.get('Machine_ID'),
            'Auditor': summary.get('Auditor'),
            'Observed Personnel': summary.get('Observed_Personnel'),
            'Supervisor': summary.get('Supervisor'),
        }
        st.json(metadata_display) # ใช้ json เพื่อแสดงโครงสร้าง

        # 4b. แสดงรายละเอียดรายข้อ
        st.markdown("---")
        st.header("5. รายละเอียดการประเมินรายข้อ")
        st.dataframe(df_audit_result[['คำถาม', 'Scoring Category', 'Score', 'หมายเหตุ']])

        # 5. Save to Google Sheet Button
        st.markdown("---")
        st.header("6. บันทึกผลสรุป")
        
        if st.button("บันทึกผลสรุปทั้งหมดไปยัง Google Sheet"):
            success, message = save_to_google_sheet(summary)
            if success:
                st.success(message)
                st.write("ข้อมูลทั้งหมด (Metadata, คะแนนรวม, คะแนน 7 ด้าน) ได้ถูกบันทึกเป็น Header ใน Google Sheet เรียบร้อยแล้ว")
                
            else:
                st.error(message)

        # 6. Download Processed Data (Optional)
        st.download_button(
            label="⬇️ ดาวน์โหลดผลการประเมินทั้งหมด (CSV)",
            data=df_audit_result.to_csv(index=False).encode('utf-8'),
            file_name=f"audit_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
else:
    st.info("กรุณาอัปโหลดไฟล์ Excel/CSV ที่กรอกข้อมูลแล้ว เพื่อเริ่มต้นการประเมิน")
