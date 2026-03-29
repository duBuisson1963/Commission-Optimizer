import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
from fpdf import FPDF
from datetime import datetime

# --- CONFIGURATION (Frozen) ---
SALARY_SCALES = {
    "Own Midpoint": None,
    "Grade 08 (Entry)": 18500.00,
    "Grade 09 (Junior)": 22450.00,
    "Grade 10 (Standard)": 27276.33,
    "Grade 11 (Senior)": 35800.00,
    "Grade 12 (Lead)": 48200.00
}

CONFIGS = {
    "Group 1 (Enter/Corp)": [("Television", 50), ("Radio", 40), ("Sports", 5), ("Digital", 5)],
    "Group 2 (SMME/Gov)": [("Digital", 5), ("Radio Classic", 45), ("Radio Sponsorship", 10), 
                           ("Radio Sport Sponsorship", 2.5), ("TV Classic", 30), 
                           ("TV Sponsorship", 5), ("TV Sport Sponsorship", 2.5)],
    "Group 3 (Prod/Cat Mgr)": [("TV/Radio Sponsorship", 75), ("TV/Radio Classic", 15), 
                               ("Sports", 5), ("Digital", 5)],
    "Group 4 (Sports PM)": [("Digital", 10), ("Radio Sport Sponsorship", 30), 
                             ("TV Sport Sponsorship", 60)]
}

class TomFinalSimulator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Official TOM Commission Simulator v10.10")
        self.geometry("1250x1000")
        
        # --- HEADER ---
        header = ttk.Frame(self, padding=20)
        header.pack(fill='x')
        
        ttk.Label(header, text="Functional Group:", font=('Arial', 10, 'bold')).grid(row=0, column=0, sticky='w')
        self.group_var = tk.StringVar(value="Group 2 (SMME/Gov)")
        self.dropdown = ttk.Combobox(header, textvariable=self.group_var, values=list(CONFIGS.keys()), state="readonly", width=35)
        self.dropdown.grid(row=0, column=1, padx=10, sticky='w')
        self.dropdown.bind("<<ComboboxSelected>>", lambda e: self.build_ui())

        ttk.Label(header, text="Salary Scale:", font=('Arial', 10, 'bold')).grid(row=1, column=0, sticky='w', pady=10)
        self.scale_var = tk.StringVar(value="Own Midpoint")
        self.scale_dropdown = ttk.Combobox(header, textvariable=self.scale_var, values=list(SALARY_SCALES.keys()), state="readonly", width=35)
        self.scale_dropdown.grid(row=1, column=1, padx=10, sticky='w')
        self.scale_dropdown.bind("<<ComboboxSelected>>", self.update_midpoint)

        ttk.Label(header, text="Target Midpoint:", font=('Arial', 10, 'bold')).grid(row=1, column=2, padx=10, sticky='w')
        self.mid_var = tk.StringVar(value="27,276.33")
        self.mid_entry = ttk.Entry(header, textvariable=self.mid_var, width=20)
        self.mid_entry.grid(row=1, column=3, sticky='w')

        btn_f = ttk.Frame(header)
        btn_f.grid(row=0, column=2, columnspan=2, padx=10)
        ttk.Button(btn_f, text="Import CSV/Excel", command=self.import_file).pack(side='left', padx=5)
        ttk.Button(btn_f, text="Export PDF Audit", command=self.export_pdf).pack(side='left', padx=5)

        # --- INPUT AREA ---
        container = ttk.Frame(self)
        container.pack(fill='both', expand=True, padx=10)
        self.canvas = tk.Canvas(container)
        self.scroll = ttk.Scrollbar(container, orient="vertical", command=self.canvas.yview)
        self.frame = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        # --- FOOTER ---
        footer = ttk.Frame(self, padding=10)
        footer.pack(fill='x', side='bottom')
        ttk.Button(footer, text="Run Master Audit & Advice", command=self.calculate).pack(pady=5)
        self.lbl_payout = ttk.Label(footer, text="Total Commission: R 0.00", font=('Arial', 22, 'bold'), foreground="#1b5e20")
        self.lbl_payout.pack()
        
        r_frame = ttk.Frame(footer)
        r_frame.pack(fill='x', pady=5)
        self.txt_audit = tk.Text(r_frame, height=14, font=('Courier New', 10), bg="#f1f3f4", padx=10, pady=10)
        self.txt_audit.pack(side='left', fill='both', expand=True, padx=5)
        self.txt_advice = tk.Text(r_frame, height=14, font=('Courier New', 10), bg="#e8f5e9", padx=10, pady=10)
        self.txt_advice.pack(side='right', fill='both', expand=True, padx=5)

        self.entries = []
        self.build_ui()

    def update_midpoint(self, event=None):
        val = SALARY_SCALES[self.scale_var.get()]
        if val is not None: self.mid_var.set(f"{val:,.2f}")

    def build_ui(self):
        for w in self.frame.winfo_children(): w.destroy()
        self.entries = []
        streams = CONFIGS[self.group_var.get()]
        headers = ["Segment Name", "Actual Revenue (Rands)", "Target Revenue (Rands)", "Weight"]
        for c, h in enumerate(headers):
            ttk.Label(self.frame, text=h, font=('Arial', 9, 'bold'), width=[35, 25, 25, 10][c]).grid(row=0, column=c, padx=10, pady=5)
        for i, (name, weight) in enumerate(streams):
            ttk.Label(self.frame, text=name, width=35).grid(row=i+1, column=0, padx=10, pady=4, sticky='w')
            act, tar = tk.StringVar(value="0"), tk.StringVar(value="1")
            ttk.Entry(self.frame, textvariable=act, width=18).grid(row=i+1, column=1, padx=10, pady=4)
            ttk.Entry(self.frame, textvariable=tar, width=18).grid(row=i+1, column=2, padx=10, pady=4)
            ttk.Label(self.frame, text=f"{weight}%", width=10).grid(row=i+1, column=3, padx=10, pady=4)
            self.entries.append({"name": name, "act": act, "tar": tar, "w": weight})

    def import_file(self):
        path = filedialog.askopenfilename(filetypes=[("Excel/CSV", "*.xlsx *.csv")])
        if not path: return
        try:
            df = pd.read_excel(path) if path.endswith('.xlsx') else pd.read_csv(path)
            if 'Midpoint' in df.columns: self.mid_var.set(f"{df['Midpoint'].iloc[0]:,.2f}")
            for _, row in df.iterrows():
                for e in self.entries:
                    if str(row['Segment']).strip().lower() == e['name'].lower():
                        e['act'].set(f"{row['Actual']:,.2f}")
                        e['tar'].set(f"{row['Target']:,.2f}")
            messagebox.showinfo("Success", "Data Loaded!")
        except Exception as e: messagebox.showerror("Error", str(e))

    def calculate(self):
        try:
            mid = float(self.mid_var.get().replace(',', '').replace(' ', ''))
            total_actual, total_target, weighted_score, binary_weight = 0.0, 0.0, 0.0, 0.0
            segments_data = []
            all_met = True
            
            # BUILD TABLE STRING
            audit = "--- MASTER AUDIT ---\n"
            audit += f"{'STREAM':<25} {'ACTUAL':<15} {'TARGET':<15} {'% ACH':<10} {'COMMISSION'}\n"
            audit += "-"*80 + "\n"
            
            total_comm_contribution = 0.0
            for e in self.entries:
                a = float(e["act"].get().replace(',', '').replace(' ', ''))
                t = float(e["tar"].get().replace(',', '').replace(' ', ''))
                w_dec = e["w"] / 100.0
                ach = a / t if t > 0 else 0
                weighted_score += (ach * w_dec); total_actual += a; total_target += t
                
                # Weighted Rand Contribution
                comm_contrib = mid * (ach * w_dec)
                total_comm_contribution += comm_contrib
                
                if ach >= 1.0: binary_weight += w_dec
                else: all_met = False
                
                audit += f"{e['name']:<25} {a:>15,.2f} {t:>15,.2f} {ach*100:>8.2f}% R {comm_contrib:>10,.2f}\n"
                segments_data.append({"name": e["name"], "target": t, "actual": a, "weight": e["w"], "ach": ach})

            audit += "-"*80 + "\n"
            tot_ach_pct = (total_actual / total_target * 100) if total_target > 0 else 0
            audit += f"{'TOTALS:':<25} {total_actual:>15,.2f} {total_target:>15,.2f} {tot_ach_pct:>8.2f}% R {total_comm_contribution:>10,.2f}\n"

            if all_met: weighted_score += 0.05
            rev_ach = total_actual / total_target if total_target > 0 else 0
            s = round(weighted_score, 4)
            
            # --- FROZEN MULTIPLIER LOGIC ---
            next_t = None; next_m = 0.0
            if rev_ach >= 1.0:
                if s >= 1.8001: mult = 6.20; next_t = None
                elif s >= 1.5001: mult = 4.10; next_t = 1.8001; next_m = 6.20
                elif s >= 1.2001: mult = 2.10; next_t = 1.5001; next_m = 4.10
                elif s >= 1.0001: mult = 1.00; next_t = 1.2001; next_m = 2.10
                elif s == 1.0000: mult = 0.50; next_t = 1.0001; next_m = 1.00
                else: mult = binary_weight; next_t = 1.0000; next_m = 0.50
            else: mult = binary_weight; next_t = "GATE"

            payout = mid * mult
            self.lbl_payout.config(text=f"Total Commission: R {payout:,.2f}")
            audit += f"\nWeighted Univ. Score: {weighted_score*100:.2f}%\nMultiplier: {mult:.2f}x\n"
            self.txt_audit.delete('1.0', tk.END); self.txt_audit.insert(tk.END, audit)

            # --- ADVISOR ---
            advice = "--- STRATEGIC ADVISOR: LOW HANGING FRUITS ---\n"
            if next_t == "GATE":
                gap = total_target - total_actual
                advice += f"TARGET: Unlock Total Revenue Gate (100%)\nEFFORT: Sell R {gap:,.2f} in ANY segment.\nCOMMISSION BENEFIT: Unlocks Multiplier payouts."
            elif next_t:
                pts_needed = next_t - s
                benefit_zar = (mid * next_m) - payout
                advice += f"TARGET: Reach {next_t*100:.2f}% Weighted Score\n\n"
                ranked = sorted(segments_data, key=lambda x: x['weight']/x['target'] if x['target']>0 else 0, reverse=True)
                for i, item in enumerate(ranked[:3]):
                    rands = (pts_needed * item['target']) / (item['weight']/100.0)
                    advice += f"{i+1}. PATH: {item['name']}\n   EFFORT: Sell R {rands:,.2f} more\n   COMMISSION BENEFIT: +R {benefit_zar:,.2f}\n"
            else: advice += "STATUS: Maximum 6.20x Bracket Reached."
            
            if not all_met:
                gs_gap = sum([max(0, x['target'] - x['actual']) for x in segments_data])
                advice += f"\nGRAND SLAM: Need R {gs_gap:,.2f} more for +5%.\nCOMMISSION BENEFIT: +R {mid*0.05:,.2f}"
            self.txt_advice.delete('1.0', tk.END); self.txt_advice.insert(tk.END, advice)
        except Exception as e: messagebox.showerror("Error", str(e))

    def export_pdf(self):
        include_advice = messagebox.askyesno("PDF Export", "Include Strategic Advisor (Low Hanging Fruits) in the report?")
        path = filedialog.asksaveasfilename(defaultextension=".pdf")
        if not path: return
        try:
            pdf = FPDF()
            pdf.add_page(); pdf.set_font("Arial", 'B', 16)
            pdf.cell(200, 10, "TOM Strategic Commission Report", ln=True, align='C')
            pdf.set_font("Courier", size=9)
            pdf.ln(10); pdf.multi_cell(0, 5, self.txt_audit.get('1.0', tk.END))
            if include_advice:
                pdf.ln(5); pdf.set_font("Courier", 'B', 10); pdf.cell(200, 10, "STRATEGIC ADVICE:", ln=True)
                pdf.set_font("Courier", size=9); pdf.multi_cell(0, 5, self.txt_advice.get('1.0', tk.END))
            pdf.ln(10); pdf.set_font("Arial", 'B', 14); pdf.cell(200, 10, self.lbl_payout.cget('text'), ln=True)
            pdf.output(path); messagebox.showinfo("Success", "PDF Saved!")
        except Exception as e: messagebox.showerror("Error", str(e))

if __name__ == "__main__":
    app = TomFinalSimulator(); app.mainloop()
