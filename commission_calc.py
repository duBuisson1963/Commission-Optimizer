import tkinter as tk
from tkinter import ttk, messagebox

# --- CONFIGURATION (Master Weights for Groups) ---
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
        self.title("Official TOM Commission Simulator v10.4")
        self.geometry("1150x950")
        
        header = ttk.Frame(self, padding=20)
        header.pack(fill='x')
        
        ttk.Label(header, text="Functional Group:", font=('Arial', 11, 'bold')).grid(row=0, column=0, sticky='w')
        self.group_var = tk.StringVar(value="Group 2 (SMME/Gov)")
        self.dropdown = ttk.Combobox(header, textvariable=self.group_var, values=list(CONFIGS.keys()), state="readonly", width=40)
        self.dropdown.grid(row=0, column=1, padx=20, sticky='w')
        self.dropdown.bind("<<ComboboxSelected>>", lambda e: self.build_ui())

        ttk.Label(header, text="Target Commission (Midpoint):", font=('Arial', 11, 'bold')).grid(row=1, column=0, sticky='w', pady=15)
        self.mid_var = tk.StringVar(value="27,276.33")
        ttk.Entry(header, textvariable=self.mid_var, width=42).grid(row=1, column=1, padx=20, sticky='w')

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

        footer = ttk.Frame(self, padding=20)
        footer.pack(fill='x', side='bottom')
        ttk.Button(footer, text="Calculate Final Payout", command=self.calculate).pack(pady=10)
        self.lbl_payout = ttk.Label(footer, text="Total Commission: R 0.00", font=('Arial', 24, 'bold'), foreground="#1b5e20")
        self.lbl_payout.pack()
        self.txt_audit = tk.Text(footer, height=12, font=('Courier New', 11), bg="#f8f9fa", padx=15, pady=15)
        self.txt_audit.pack(fill='x', pady=10)

        self.entries = []
        self.build_ui()

    def build_ui(self):
        for w in self.frame.winfo_children(): w.destroy()
        self.entries = []
        streams = CONFIGS[self.group_var.get()]
        headers = ["Segment Name", "Actual Revenue", "Target Revenue", "Weight"]
        for c, h in enumerate(headers):
            ttk.Label(self.frame, text=h, font=('Arial', 10, 'bold'), width=[35, 25, 25, 10][c], anchor='w').grid(row=0, column=c, padx=15, pady=10)

        for i, (name, weight) in enumerate(streams):
            ttk.Label(self.frame, text=name, width=35, anchor='w').grid(row=i+1, column=0, padx=15, pady=8, sticky='w')
            act, tar = tk.StringVar(value="0"), tk.StringVar(value="1")
            ttk.Entry(self.frame, textvariable=act, width=20).grid(row=i+1, column=1, padx=15, pady=8)
            ttk.Entry(self.frame, textvariable=tar, width=20).grid(row=i+1, column=2, padx=15, pady=8)
            ttk.Label(self.frame, text=f"{weight}%", width=10, anchor='center').grid(row=i+1, column=3, padx=15, pady=8)
            self.entries.append({"name": name, "act": act, "tar": tar, "w": weight})

    def calculate(self):
        try:
            mid = float(self.mid_var.get().replace(',', '').replace(' ', ''))
            total_actual, total_target, weighted_score, binary_weight = 0.0, 0.0, 0.0, 0.0
            all_met = True
            
            audit = f"--- MASTER AUDIT: {self.group_var.get()} ---\n"
            for e in self.entries:
                a_str = e["act"].get().replace(',', '').replace(' ', '')
                t_str = e["tar"].get().replace(',', '').replace(' ', '')
                a = float(a_str) if a_str else 0.0
                t = float(t_str) if t_str else 1.0 # Default to 1 to avoid div by zero
                w_dec = e["w"] / 100.0
                ach = a / t
                weighted_score += (ach * w_dec)
                total_actual += a
                total_target += t
                if ach >= 1.0: binary_weight += w_dec
                else: all_met = False
                audit += f"{e['name']:<30}: {ach*100:>8.2f}% ach\n"

            if all_met:
                weighted_score += 0.05
                audit += "\nBONUS: +5% Grand Slam Applied\n"
            
            rev_ach = total_actual / total_target if total_target > 0 else 0
            audit += f"Total Rev Achievement: {rev_ach*100:.2f}%\n"
            audit += f"Weighted Univ. Score : {weighted_score*100:.2f}%\n"
            audit += "-"*45 + "\n"

            # MASTER UNIVERSAL MULTIPLIERS (v10.4)
            if rev_ach >= 1.0:
                s = round(weighted_score, 4)
                if s >= 1.8001: mult = 6.20
                elif s >= 1.5001: mult = 4.10
                elif s >= 1.2001: mult = 2.10
                elif s >= 1.0001: mult = 1.00
                elif s == 1.0000: mult = 0.50 # Exact 100% floor
                else: mult = binary_weight
                
                payout = mid * mult
                audit += f"MULTIPLIER APPLIED: {mult:.2f}x\n"
            else:
                payout = mid * binary_weight
                audit += f"BINARY GATE ONLY: {binary_weight*100:.1f}% Weight\n"

            self.lbl_payout.config(text=f"Total Commission: R {payout:,.2f}")
            self.txt_audit.delete('1.0', tk.END)
            self.txt_audit.insert(tk.END, audit)
        except Exception as e:
            messagebox.showerror("Error", str(e))

if __name__ == "__main__":
    app = TomFinalSimulator()
    app.mainloop()
