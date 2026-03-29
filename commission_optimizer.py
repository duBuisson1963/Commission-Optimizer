import tkinter as tk
from tkinter import ttk, messagebox

# --- STRICT NAMING CONFIGURATION (Verified against your images) ---
CONFIGS = {
    "Group 1 (Enter/Corp)": {
        "streams": ["Television", "Radio", "Sports", "Digital"], 
        "weights": [50, 40, 5, 5]
    },
    "Group 2 (SMME/Gov)": {
        "streams": ["Digital", "Radio Classic", "Radio Sponsorship", "Radio Sport Sponsorship", "TV Classic", "TV Sponsorship", "TV Sport Sponsorship"], 
        "weights": [5, 45, 10, 2.5, 30, 5, 2.5]
    },
    "Group 4 (Sports PM)": {
        "streams": ["Digital", "Radio Sport Sponsorship", "TV Sport Sponsorship"], 
        "weights": [10, 30, 60]
    }
}

class CommissionApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Commission Simulator v8.0 (Final Math & Labels)")
        self.geometry("1000x850")
        
        # --- HEADER INPUTS ---
        header = ttk.Frame(self, padding=20)
        header.pack(fill='x')
        
        ttk.Label(header, text="Functional Group:").grid(row=0, column=0, sticky='w', pady=5)
        self.group_var = tk.StringVar(value="Group 4 (Sports PM)")
        self.dropdown = ttk.Combobox(header, textvariable=self.group_var, values=list(CONFIGS.keys()), state="readonly", width=35)
        self.dropdown.grid(row=0, column=1, padx=10, sticky='w')
        self.dropdown.bind("<<ComboboxSelected>>", lambda e: self.build_ui())

        # CORRECTED LABEL: Target Commission
        ttk.Label(header, text="Target Commission (Midpoint):").grid(row=1, column=0, sticky='w', pady=5)
        self.mid_var = tk.StringVar(value="38,325.83")
        ttk.Entry(header, textvariable=self.mid_var, width=37).grid(row=1, column=1, padx=10, sticky='w')

        # --- DATA TABLE (FIXED GRID LAYOUT) ---
        self.table_frame = ttk.Frame(self, padding=20)
        self.table_frame.pack(fill='both', expand=True)
        
        # --- FOOTER / RESULTS ---
        footer = ttk.Frame(self, padding=20)
        footer.pack(fill='x', side='bottom')
        
        ttk.Button(footer, text="Calculate Commission", command=self.calculate).pack(pady=10)
        
        # CORRECTED LABEL: Total Commission
        self.lbl_payout = ttk.Label(footer, text="Total Commission: R 0.00", font=('Arial', 24, 'bold'), foreground="#1b5e20")
        self.lbl_payout.pack()
        
        self.advice_box = tk.Text(footer, height=8, font=('Arial', 11), bg="#f8f9fa", padx=10, pady=10)
        self.advice_box.pack(fill='x', pady=10)

        self.entries = []
        self.build_ui()

    def build_ui(self):
        for w in self.table_frame.winfo_children(): w.destroy()
        self.entries = []
        
        # TABLE HEADERS
        headers = ["Segment", "Actuals", "Target", "Weight"]
        for c, h in enumerate(headers):
            ttk.Label(self.table_frame, text=h, font=('Arial', 10, 'bold')).grid(row=0, column=c, padx=25, pady=10, sticky='w')

        config = CONFIGS[self.group_var.get()]
        for i, name in enumerate(config["streams"]):
            row = i + 1
            ttk.Label(self.table_frame, text=name, width=28).grid(row=row, column=0, padx=25, pady=5, sticky='w')
            
            act = tk.StringVar(value="0")
            ttk.Entry(self.table_frame, textvariable=act, width=15).grid(row=row, column=1, padx=25, pady=5)
            
            tar = tk.StringVar(value="1")
            ttk.Entry(self.table_frame, textvariable=tar, width=15).grid(row=row, column=2, padx=25, pady=5)
            
            ttk.Label(self.table_frame, text=f"{config['weights'][i]}%").grid(row=row, column=3, padx=25, pady=5)
            
            self.entries.append({"name": name, "act": act, "tar": tar, "w": config["weights"][i]})

    # --- RESTORED v7.0 MATH LOGIC ---
    def calculate(self):
        try:
            mid = float(self.mid_var.get().replace(',', '').replace(' ', ''))
            w_act, w_tar, binary_sum, gaps = 0, 0, 0, []

            for e in self.entries:
                a = float(e["act"].get().replace(',', ''))
                t = float(e["tar"].get().replace(',', ''))
                w = e["w"] / 100.0
                
                # Math from v7.0
                w_act += (a * w)
                w_tar += (t * w)
                
                ach = a / t if t != 0 else 0
                pot_val = mid * w
                if ach >= 1.0: 
                    binary_sum += pot_val
                else: 
                    gaps.append({"name": e["name"], "short": t - a, "unlocks": pot_val, "efficiency": pot_val/(t-a)})

            # Math from v7.0
            overall = w_act / w_tar if w_tar != 0 else 0
            
            if overall >= 1.51: mult, next_t = 4.10, None
            elif overall >= 1.21: mult, next_t = 2.10, 1.51
            elif overall >= 1.10: mult, next_t = 1.00, 1.21
            else: mult, next_t = 0, 1.10

            final = mid * mult if overall >= 1.10 else binary_sum
            
            # Label correctly set to Total Commission
            self.lbl_payout.config(text=f"Total Commission: R {final:,.2f}")

            # STRATEGY ADVICE (Restored from v7.0)
            self.advice_box.delete('1.0', tk.END)
            advice = f"OVERALL ACHIEVEMENT: {overall*100:.2f}%\n"
            advice += "-"*50 + "\n"
            
            if next_t:
                short = (w_tar * next_t) - w_act
                advice += f"🚀 MULTIPLIER PUSH: Sell R {short:,.2f} more TOTAL to jump to the next Tier.\n"
            
            if gaps and overall < 1.10:
                gaps.sort(key=lambda x: x['efficiency'], reverse=True)
                top = gaps[0]
                advice += f"🎯 QUICK WIN: Sell R {top['short']:,.2f} in {top['name']} to unlock R {top['unlocks']:,.2f} instantly.\n"
            
            self.advice_box.insert(tk.END, advice)
            
        except Exception: 
            messagebox.showerror("Error", "Please check that all inputs are numbers.")

if __name__ == "__main__":
    CommissionApp().mainloop()
