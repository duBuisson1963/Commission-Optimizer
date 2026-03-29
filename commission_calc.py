import tkinter as tk
from tkinter import ttk, messagebox

# --- CONFIGURATION (Verified against Policy Slides) ---
CONFIGS = {
    "Group 1 (Enter/Corp)": {
        "streams": ["Television", "Radio", "Sports", "Digital"], 
        "weights": [50, 40, 5, 5]
    },
    "Group 2 (SMME/Gov)": {
        "streams": ["Digital", "Radio Classic", "Radio Sponsorship", "Radio Sport Sponsorship", "TV Classic", "TV Sponsorship", "TV Sport Sponsorship"], 
        "weights": [5, 45, 10, 2.5, 30, 5, 2.5]
    },
    "Group 3 (Prod/Cat Mgr)": {
        "streams": ["TV/Radio Sponsorship", "TV/Radio Classic", "Sports", "Digital"], 
        "weights": [75, 15, 5, 5]
    },
    "Group 4 (Sports PM)": {
        "streams": ["Digital", "Radio Sport Sponsorship", "TV Sport Sponsorship"], 
        "weights": [10, 30, 60]
    }
}

class TomFinalSimulator(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Official TOM Commission Simulator v10.2")
        # Widened window to 1150 to prevent clipping
        self.geometry("1150x950")
        
        # --- HEADER SECTION ---
        header = ttk.Frame(self, padding=20)
        header.pack(fill='x')
        
        ttk.Label(header, text="Functional Group:", font=('Arial', 11, 'bold')).grid(row=0, column=0, sticky='w')
        self.group_var = tk.StringVar(value="Group 4 (Sports PM)")
        self.dropdown = ttk.Combobox(header, textvariable=self.group_var, values=list(CONFIGS.keys()), state="readonly", width=40)
        self.dropdown.grid(row=0, column=1, padx=20, sticky='w')
        self.dropdown.bind("<<ComboboxSelected>>", lambda e: self.build_ui())

        ttk.Label(header, text="Target Commission (Midpoint):", font=('Arial', 11, 'bold')).grid(row=1, column=0, sticky='w', pady=15)
        self.mid_var = tk.StringVar(value="38,325.83")
        ttk.Entry(header, textvariable=self.mid_var, width=42).grid(row=1, column=1, padx=20, sticky='w')

        # --- SCROLLABLE TABLE AREA ---
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

        # --- FOOTER SECTION ---
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
        config = CONFIGS[self.group_var.get()]
        
        # TABLE HEADERS with fixed spacing
        headers = ["Segment Name", "Actual Revenue (Rands)", "Target Revenue (Rands)", "Weight"]
        header_widths = [35, 25, 25, 10]
        
        for c, (h, w) in enumerate(zip(headers, header_widths)):
            lbl = ttk.Label(self.frame, text=h, font=('Arial', 10, 'bold'), width=w, anchor='w')
            lbl.grid(row=0, column=c, padx=15, pady=10)

        for i, name in enumerate(config["streams"]):
            # Row index
            r = i + 1
            
            # Segment Name
            ttk.Label(self.frame, text=name, width=35, anchor='w').grid(row=r, column=0, padx=15, pady=8, sticky='w')
            
            # Actual Revenue Entry (Widened to 20)
            act = tk.StringVar(value="0")
            e_act = ttk.Entry(self.frame, textvariable=act, width=20)
            e_act.grid(row=r, column=1, padx=15, pady=8)
            
            # Target Revenue Entry (Widened to 20)
            tar = tk.StringVar(value="1")
            e_tar = ttk.Entry(self.frame, textvariable=tar, width=20)
            e_tar.grid(row=r, column=2, padx=15, pady=8)
            
            # Weight Label
            ttk.Label(self.frame, text=f"{config['weights'][i]}%", width=10, anchor='center').grid(row=r, column=3, padx=15, pady=8)
            
            self.entries.append({"name": name, "act": act, "tar": tar, "w": config["weights"][i]})

    def calculate(self):
        try:
            # --- MATH LOGIC: UNCHANGED FROM v10.1 ---
            mid_val = self.mid_var.get().replace(',', '').replace(' ', '')
            mid = float(mid_val)
            total_actual, total_target = 0.0, 0.0
            weighted_score = 0.0
            binary_earned_weight = 0.0
            all_targets_met = True
            
            audit_log = "--- OFFICIAL CALCULATION AUDIT ---\n"
            
            for e in self.entries:
                a_str = e["act"].get().replace(',', '').replace(' ', '')
                t_str = e["tar"].get().replace(',', '').replace(' ', '')
                a = float(a_str) if a_str else 0.0
                t = float(t_str) if t_str else 0.0
                w_decimal = e["w"] / 100.0
                
                ach_pct = a / t if t > 0 else 0
                weighted_score += (ach_pct * w_decimal)
                total_actual += a
                total_target += t
                
                if ach_pct >= 1.0:
                    binary_earned_weight += w_decimal
                else:
                    all_targets_met = False
                
                audit_log += f"{e['name']:<30}: {ach_pct*100:>8.2f}% ach\n"

            if all_targets_met:
                weighted_score += 0.05
                audit_log += "\nBONUS: +5% Grand Slam Achievement Applied\n"
            
            total_rev_ach = total_actual / total_target if total_target > 0 else 0
            audit_log += f"Total Revenue Achievement: {total_rev_ach*100:.2f}%\n"
            audit_log += f"Weighted Universal Score : {weighted_score*100:.2f}%\n"
            audit_log += "-"*45 + "\n"

            if total_rev_ach >= 1.0:
                if weighted_score >= 1.51:
                    mult = 4.10
                    audit_log += "TIER: 151%+ (Capped Multiplier)\n"
                elif weighted_score >= 1.21:
                    mult = 2.10
                    audit_log += "TIER: 121% - 150% Bracket\n"
                elif weighted_score >= 1.10:
                    mult = 1.00
                    audit_log += "TIER: 110% - 120% Bracket\n"
                else:
                    mult = binary_earned_weight
                    audit_log += "TIER: 100% - 109% (Binary Gate Active)\n"
                
                final_payout = mid * mult
                audit_log += f"FINAL MULTIPLIER: {mult:.2f}x\n"
            else:
                final_payout = mid * binary_earned_weight
                audit_log += "MODE: Total Revenue Gate Not Reached (<100%)\n"
                audit_log += f"EARNED COMMISSION WEIGHT: {binary_earned_weight*100:.1f}%\n"

            self.lbl_payout.config(text=f"Total Commission: R {final_payout:,.2f}")
            self.txt_audit.delete('1.0', tk.END)
            self.txt_audit.insert(tk.END, audit_log)
            
        except ValueError:
            messagebox.showerror("Input Error", "Please ensure all fields contain only numbers.")
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {str(e)}")

if __name__ == "__main__":
    app = TomFinalSimulator()
    app.mainloop()
