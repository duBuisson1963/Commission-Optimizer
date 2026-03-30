import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pandas as pd
from fpdf import FPDF
from decimal import Decimal, ROUND_HALF_UP

# --- SCENARIO 1: SABC APPLIED WEIGHTS (From Spreadsheet) ---
STATEMENT_W = {
    "Radio Classic": 45.0, "TV Classic": 24.0, "TV Sponsorship": 6.0,
    "Radio Sponsorship": 15.0, "Digital": 5.0, "TV Sport Sponsorship": 2.5, "Radio Sport Sponsorship": 2.5
}

# --- SCENARIO 2: POLICY DICTATED WEIGHTS (Official Scheme) ---
POLICY_W = {
    "TV Classic": 40.0, "Radio Classic": 30.0, "TV Sponsorship": 10.0,
    "Radio Sponsorship": 10.0, "Digital": 5.0, "TV Sport Sponsorship": 2.5, "Radio Sport Sponsorship": 2.5
}

class TomDualForensic(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("BEMAWU Dual-Profile Forensic Simulator v10.35")
        self.geometry("1250x1000")
        
        header = ttk.Frame(self, padding=20)
        header.pack(fill='x')
        
        ttk.Label(header, text="Target Commission (Midpoint):", font=('Arial', 10, 'bold')).grid(row=0, column=0, sticky='w')
        self.mid_var = tk.StringVar(value="27276.33")
        ttk.Entry(header, textvariable=self.mid_var, width=15).grid(row=0, column=1, padx=10, sticky='w')

        btn_f = ttk.Frame(header)
        btn_f.grid(row=0, column=2, padx=10)
        ttk.Button(btn_f, text="Import CSV/Excel", command=self.import_file).pack(side='left', padx=5)
        ttk.Button(btn_f, text="Export PDF Audit", command=self.export_pdf).pack(side='left', padx=5)

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

        footer = ttk.Frame(self, padding=10)
        footer.pack(fill='x', side='bottom')
        ttk.Button(footer, text="RUN FORENSIC COMPARISON", command=self.calculate).pack(pady=5)
        self.lbl_payout = ttk.Label(footer, text="SABC APPLIED PAYOUT: R 0.00", font=('Arial', 22, 'bold'), foreground="#1b5e20")
        self.lbl_payout.pack()
        
        r_frame = ttk.Frame(footer)
        r_frame.pack(fill='x', pady=5)
        self.txt_audit = tk.Text(r_frame, height=22, font=('Courier New', 10), bg="#f1f3f4", padx=10, pady=10)
        self.txt_audit.pack(side='left', fill='both', expand=True, padx=5)
        self.txt_advice = tk.Text(r_frame, height=22, font=('Courier New', 10), bg="#e8f5e9", padx=10, pady=10)
        self.txt_advice.pack(side='right', fill='both', expand=True, padx=5)

        self.entries = []
        self.build_ui()

    def get_mult(self, score):
        if score < 100: return Decimal('0.00')
        if score == 100: return Decimal('0.50')
        if score <= 120: return Decimal('1.00')
        if score <= 150: return Decimal('2.10')
        if score <= 180: return Decimal('4.10')
        return Decimal('6.20') 

    def build_ui(self):
        for w in self.frame.winfo_children(): w.destroy()
        self.entries = []
        segments = ["Digital", "Radio Classic", "Radio Sponsorship", "Radio Sport Sponsorship", "TV Classic", "TV Sponsorship", "TV Sport Sponsorship"]
        headers = ["Segment Name", "Actual Revenue (Rands)", "Target Revenue (Rands)"]
        for c, h in enumerate(headers):
            ttk.Label(self.frame, text=h, font=('Arial', 9, 'bold'), width=[35, 25, 25][c]).grid(row=0, column=c, padx=10, pady=5)
        for i, name in enumerate(segments):
            ttk.Label(self.frame, text=name, width=35).grid(row=i+1, column=0, padx=10, pady=4, sticky='w')
            act, tar = tk.StringVar(value="0"), tk.StringVar(value="1")
            ttk.Entry(self.frame, textvariable=act, width=18).grid(row=i+1, column=1, padx=10, pady=4)
            ttk.Entry(self.frame, textvariable=tar, width=18).grid(row=i+1, column=2, padx=10, pady=4)
            self.entries.append({"name": name, "act": act, "tar": tar})

    def run_scenario(self, mid, w_map, m_pay, logic_type):
        lines, sum_seg = [], Decimal('0')
        for e in self.entries:
            a, t = Decimal(e["act"].get().replace(',', '').replace(' ', '')), Decimal(e["tar"].get().replace(',', '').replace(' ', ''))
            w = Decimal(str(w_map.get(e["name"], 0))) / 100
            ach = a / t if t > 0 else Decimal('0')
            sc = (mid * w) if ach >= 1.0 else Decimal('0')
            sum_seg += sc
            lines.append(f"{e['name']:<25} {ach*100:>7.1f}% R {sc:>12,.2f}")
        
        if logic_type == 'absorbed':
            total = max(sum_seg, m_pay)
        else: # additive
            total = sum_seg + m_pay
            
        return {"lines": lines, "tot": total, "base_sum": sum_seg}

    def calculate(self):
        try:
            mid = Decimal(self.mid_var.get().replace(',', ''))
            ta, tt = Decimal('0'), Decimal('0')
            for e in self.entries:
                ta += Decimal(e["act"].get().replace(',', '').replace(' ', ''))
                tt += Decimal(e["tar"].get().replace(',', '').replace(' ', ''))
            
            rev_ach = (ta / tt * 100).quantize(Decimal('0.01')) if tt > 0 else Decimal('0')
            m = self.get_mult(rev_ach)
            m_pay = (mid * m).quantize(Decimal('0.01'), ROUND_HALF_UP)
            
            # Scenario 1: What SABC did (Spreadsheet weights + Absorption)
            applied = self.run_scenario(mid, STATEMENT_W, m_pay, 'absorbed')
            
            # Scenario 2: What Policy dictates (Official weights + Additive)
            policy = self.run_scenario(mid, POLICY_W, m_pay, 'additive')
            
            audit = f"--- SCENARIO 1: SABC APPLIED CALCULATION (From Statements) ---\n"
            audit += f"Weights Applied: 45/24/6 | Total Ach: {rev_ach}% | Mult: {m}x\n"
            audit += f"{'STREAM':<25} {'% ACH':>8} {'SABC PAID':>14}\n"
            audit += "-"*50 + "\n"
            audit += "\n".join(applied["lines"]) + "\n"
            audit += "-"*50 + "\n"
            audit += f"{'MULTIPLIER PAYOUT:':<35} R {m_pay:>12,.2f}\n"
            audit += f"{'FINAL SABC PAYOUT (Absorbed):':<35} R {applied['tot']:>12,.2f}\n\n\n"
            
            audit += f"--- SCENARIO 2: POLICY DICTATED CALCULATION (Official) ---\n"
            audit += f"Weights Applied: 40/30/10 | Total Ach: {rev_ach}% | Mult: {m}x\n"
            audit += f"{'STREAM':<25} {'% ACH':>8} {'POLICY DUE':>14}\n"
            audit += "-"*50 + "\n"
            audit += "\n".join(policy["lines"]) + "\n"
            audit += "-"*50 + "\n"
            audit += f"{'MULTIPLIER PAYOUT:':<35} R {m_pay:>12,.2f}\n"
            audit += f"{'FINAL POLICY DUE (Additive):':<35} R {policy['tot']:>12,.2f}\n"

            self.txt_audit.delete('1.0', tk.END); self.txt_audit.insert(tk.END, audit)
            self.lbl_payout.config(text=f"SABC APPLIED PAYOUT: R {applied['tot']:,.2f}")
            
            shortfall = policy['tot'] - applied['tot']
            
            adv = "--- FORENSIC DISCREPANCY SUMMARY ---\n\n"
            adv += f"1. SABC APPLIED PAYOUT:  R {applied['tot']:,.2f}\n"
            adv += f"2. POLICY DICTATED DUE:  R {policy['tot']:,.2f}\n"
            adv += "-"*40 + "\n"
            adv += f"TOTAL SHORTFALL OWED:    R {shortfall:,.2f}\n\n"
            adv += "EXPLANATION OF DIFFERENCE:\n"
            adv += "- SABC utilized weights of 45/24/6 in their spreadsheets.\n"
            adv += "- SABC replaced segment earnings with the multiplier payout.\n"
            adv += "- The Official Policy mandates weights of 40/30/10.\n"
            adv += "- Policy indicates the multiplier should be additive.\n"
            self.txt_advice.delete('1.0', tk.END); self.txt_advice.insert(tk.END, adv)
        except Exception: messagebox.showerror("Error", "Check inputs")

    def import_file(self):
        path = filedialog.askopenfilename()
        if not path: return
        try:
            if path.endswith('.xlsx'):
                df = pd.read_excel(path)
            else:
                # Standard read with latin-1 for Excel CSVs
                df = pd.read_csv(path, encoding='latin-1')
            
            for _, row in df.iterrows():
                for e in self.entries:
                    if str(row['Segment']).strip().lower() == e['name'].lower():
                        e['act'].set(f"{row['Actual']:,.2f}"); e['tar'].set(f"{row['Target']:,.2f}")
            messagebox.showinfo("Success", "Loaded Successfully")
        except Exception as e: messagebox.showerror("Error", str(e))

    def export_pdf(self):
        path = filedialog.asksaveasfilename(defaultextension=".pdf")
        if not path: return
        try:
            pdf = FPDF(); pdf.add_page(); pdf.set_font("Courier", size=9)
            pdf.multi_cell(0, 5, self.txt_audit.get('1.0', tk.END))
            pdf.output(path); messagebox.showinfo("Success", "Saved")
        except Exception: messagebox.showerror("Error", "Export Failed")

if __name__ == "__main__":
    TomDualForensic().mainloop()
