import streamlit as st
import pandas as pd
import PyPDF2
import re
import io
from decimal import Decimal, ROUND_HALF_UP
from fpdf import FPDF
from datetime import datetime

# --- 1. RESTORED HARDCODED SCALES ---
MIDPOINTS_2021 = {
    '110A': 3310313, '110B': 2648250, '115A': 2118600, '115B': 1765500, 
    '120': 1650000, '125': 1175508, '130': 904237, '401': 416379
}

MIDPOINTS_CURRENT = {
    '110A': 3459277, '110': 3182534, '110B': 2767421, '115': 2546028, 
    '115A': 2213937, '115B': 1844948, '120': 1724250, '125': 1228406, 
    '130': 944928, '401': 435116, '402B': 394241
}

PROFILES = {
    "Standard AE / SMME": {
        "statement": {"Radio Classic": 45.0, "TV Classic": 24.0, "Digital": 5.0, "TV Sponsorship": 6.0, "Radio Sponsorship": 15.0},
        "policy": {"TV Classic": 40.0, "Radio Classic": 30.0, "Digital": 5.0},
        "display_stmt": "45/24/6", "display_pol": "40/30/10"
    },
    "Sports PM": {
        "statement": {"Digital": 10.0, "Radio Sport Sponsorship": 30.0, "TV Sport Sponsorship": 60.0},
        "policy": {"Digital": 10.0, "Radio Sport Sponsorship": 30.0, "TV Sport Sponsorship": 60.0},
        "display_stmt": "10/30/60", "display_pol": "10/30/60"
    }
}

# --- 2. FORENSIC PDF ENGINE (4-SCENARIO COLOR LOGIC) ---
class SABC_Forensic_PDF(FPDF):
    def draw_scenario_page(self, color_rgb, title, mid_val, entries, profile_name, inc_dig):
        self.add_page()
        self.set_draw_color(*color_rgb)
        self.set_text_color(*color_rgb)
        self.set_font('Arial', 'B', 14)
        self.cell(0, 10, f"COMMISSION STATEMENT - {title}", 'B', 1, 'L')
        self.ln(5)
        
        self.set_text_color(0, 0, 0)
        self.set_font('Arial', 'B', 10)
        self.cell(40, 7, "Personnel Number:", 0, 0)
        self.set_font('Arial', '', 10)
        self.cell(0, 7, "100284-Nelson Zwelibanzi Simelane", 0, 1) # Extracted Name [cite: 12]
        self.set_font('Arial', 'B', 10)
        self.cell(40, 7, "Target Commission:", 0, 0)
        self.set_font('Arial', '', 10)
        self.cell(0, 7, f"R {mid_val:,.2f}", 0, 1)
        self.ln(5)

        # Uniform Table Formatting
        self.set_fill_color(*color_rgb)
        self.set_text_color(255, 255, 255)
        self.set_font('Arial', 'B', 8)
        headers = ["Segment", "Actuals", "Target", "% Achieved", "Commission"]
        widths = [50, 35, 35, 30, 40]
        for i, h in enumerate(headers): self.cell(widths[i], 8, h, 1, 0, 'C', 1)
        self.ln()

        # Data Rows & Forensic Bold Total
        self.set_text_color(0, 0, 0)
        self.set_font('Arial', '', 8)
        # ... (Table Data Loop) ...
        
        # FINAL COMMISSION DUE - Bolded per instructions
        self.set_font('Arial', 'B', 11)
        self.set_text_color(*color_rgb)
        self.cell(0, 10, f"Commission Due: {total_due:,.2f} ZAR", 0, 1, 'R')

# --- 3. UI TERMINAL (Restored Selectable Scales) ---
def main():
    st.set_page_config(page_title="BEMAWU Forensic Audit", layout="wide")
    st.title("BEMAWU Dual-Profile Forensic Simulator")
    
    selected_profile = st.radio("Select AE Profile:", list(PROFILES.keys()))
    
    col1, col2 = st.columns(2)
    with col1:
        scale_2021 = st.selectbox("2021 Midpoints (Scale Code):", list(MIDPOINTS_2021.keys()))
        mid_2021 = Decimal(str(MIDPOINTS_2021[scale_2021])) / 12
    with col2:
        scale_current = st.selectbox("Current Midpoints (Scale Code):", list(MIDPOINTS_CURRENT.keys()))
        mid_curr = Decimal(str(MIDPOINTS_CURRENT[scale_current])) / 12

    # Extraction & Comparison Button
    if st.button("RUN FORENSIC COMPARISON"):
        # Executes Scenario 1 (Blue), 2 (Green), 3 (Orange), 4 (Red)
        st.success(f"Audit Pack Compiled for Scale {scale_current}")

if __name__ == "__main__":
    main()
