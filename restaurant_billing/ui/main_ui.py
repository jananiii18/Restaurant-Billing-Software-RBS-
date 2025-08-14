import tkinter as tk
import customtkinter as ctk
from CTkMessagebox import CTkMessagebox
import sqlite3 as s
import hashlib
import os
import json
import pandas as pd
from datetime import datetime
from fpdf import FPDF
import platform
import subprocess
from collections import Counter
from utils.db_utils import create_folders, initialize_database, fetch_menu_items

DATA_DIR = os.path.abspath("data")
BILLS_JSON_DIR = os.path.join(DATA_DIR, "bills")
CSV_EXPORT_PATH = os.path.join(DATA_DIR, "orders_detailed.csv")
SALES_REPORT_PATH = os.path.join(DATA_DIR, "sales_report.csv")
ALL_BILLS_JSON_PATH = os.path.join(DATA_DIR, "all_bills.json")

os.makedirs(BILLS_JSON_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def show_msgbox(title, message, icon):
    CTkMessagebox(title=title, message=message, icon=icon)

def open_file(path):
    try:
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.run(["open", path], check=False)
        else:
            subprocess.run(["xdg-open", path], check=False)
    except Exception:
        show_msgbox("Saved", f"File saved: {path}", "check")

def check_login(username, password):
    conn = s.connect("db/restaurant.db")
    cur = conn.cursor()
    cur.execute("SELECT password_hash, role FROM users WHERE username=?", (username,))
    row = cur.fetchone()
    conn.close()
    return row[1] if row and row[0] == hash_password(password) else None

def setup_users():
    conn = s.connect("db/restaurant.db")
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password_hash TEXT,
        role TEXT)''')
    if not cur.execute("SELECT 1 FROM users WHERE username='admin'").fetchone():
        cur.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                    ("admin", hash_password("admin123"), "admin"))
    if not cur.execute("SELECT 1 FROM users WHERE username='cashier'").fetchone():
        cur.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
                    ("cashier", hash_password("cashier123"), "cashier"))
    conn.commit()
    conn.close()

class LoginWindow:
    def __init__(self, root):
        self.root = root
        root.title("Login")
        root.geometry("400x300")
        ctk.CTkLabel(root, text="Username:").pack(pady=(50, 5))
        self.username_var = ctk.StringVar()
        self.password_var = ctk.StringVar()
        ctk.CTkEntry(root, textvariable=self.username_var).pack()
        ctk.CTkLabel(root, text="Password:").pack(pady=(10, 5))
        ctk.CTkEntry(root, textvariable=self.password_var, show="*").pack()
        ctk.CTkButton(root, text="Login", command=self.login).pack(pady=20)

    def login(self):
        u, p = self.username_var.get().strip(), self.password_var.get().strip()
        if not u or not p:
            show_msgbox("Error", "Please enter both fields", "cancel")
            return
        role = check_login(u, p)
        if role:
            self.root.withdraw()
            open_main_app(role, self.root)
        else:
            show_msgbox("Failed", "Invalid credentials", "cancel")


class RestaurantApp:
    def __init__(self, parent, role):
        self.frame = parent
        self.role = role
        self.order = []

        FONT_L = ("Arial", 18, "bold")
        FONT_M = ("Arial", 14)
        B = {"corner_radius": 15, "height": 40, "width": 200}

        for i in range(13):
            self.frame.grid_rowconfigure(i, weight=1)
        for j in range(4):
            self.frame.grid_columnconfigure(j, weight=1)

        ctk.CTkLabel(self.frame, text="Order Mode:", font=FONT_M).grid(row=0, column=0, sticky="e")
        self.mod_var = ctk.StringVar(value="Dine-In")
        self.mode_cb = ctk.CTkComboBox(self.frame, values=["Dine-In", "Takeaway"], variable=self.mod_var)
        self.mode_cb.grid(row=0, column=1, sticky="w")

        self.menu = []
        self._load_menu_from_db()

        ctk.CTkLabel(self.frame, text="Select Item:", font=FONT_M).grid(row=1, column=0, sticky="e")
        self.selected_item = ctk.StringVar(value=self.menu[0]['name'] if self.menu else "")
        self.item_dropdown = ctk.CTkComboBox(self.frame, values=[i['name'] for i in self.menu], variable=self.selected_item)
        self.item_dropdown.grid(row=1, column=1, sticky="w")

        ctk.CTkLabel(self.frame, text="Quantity:", font=FONT_M).grid(row=2, column=0, sticky="e")
        self.quant_entry = ctk.CTkEntry(self.frame)
        self.quant_entry.grid(row=2, column=1, sticky="w")
        self.quant_entry.insert(0, "1")
        vcmd_int = self.frame.register(lambda P: P.isdigit() or P == "")
        self.quant_entry.configure(validate="key", validatecommand=(vcmd_int, '%P'))

        ctk.CTkButton(self.frame, text="Add to Order", command=self.add_to_order, **B).grid(row=3, column=0, columnspan=2)
        self.order_listbox = ctk.CTkTextbox(self.frame, height=200, width=500)
        self.order_listbox.grid(row=4, column=0, columnspan=3)
        self.total_label = ctk.CTkLabel(self.frame, text="Total: ₹0", font=FONT_L)
        self.total_label.grid(row=5, column=0, columnspan=3)

        ctk.CTkLabel(self.frame, text="Payment Method:", font=FONT_M).grid(row=6, column=0, sticky="e")
        self.payment_method = ctk.StringVar(value="Cash")
        for idx, m in enumerate(["Cash", "Card", "UPI"]):
            ctk.CTkRadioButton(self.frame, text=m, variable=self.payment_method, value=m).grid(row=6, column=1 + idx)

        ctk.CTkLabel(self.frame, text="Discount %:", font=FONT_M).grid(row=7, column=0, sticky="e")
        self.discount_var = ctk.StringVar(value="0")
        self.discount_entry = ctk.CTkEntry(self.frame, textvariable=self.discount_var)
        self.discount_entry.grid(row=7, column=1, sticky="w")

        def _valid_float(P):
            if P in ("", ".", "-"):
                return True
            try:
                float(P)
                return True
            except:
                return False
        vcmd_float = self.frame.register(_valid_float)
        self.discount_entry.configure(validate="key", validatecommand=(vcmd_float, '%P'))
        self.discount_var.trace_add("write", lambda *_: self.refresh_order_display())

        ctk.CTkButton(self.frame, text="Generate Bill", command=self.show_bill_summary, fg_color="green", **B).grid(row=8, column=0)
        ctk.CTkButton(self.frame, text="Clear Order", command=self.clear_order, fg_color="red", **B).grid(row=8, column=1)
        if self.role == "admin":
            ctk.CTkButton(self.frame, text="Reports", command=self.open_reports_window, fg_color="blue", **B).grid(row=9, column=0)
            ctk.CTkButton(self.frame, text="Menu Management", command=self.open_menu_management, fg_color="purple", **B).grid(row=9, column=1)

        self.clock_label = ctk.CTkLabel(self.frame, text="", font=("Arial", 12))
        self.clock_label.grid(row=12, column=0, columnspan=3)
        self.update_clock()

        self.subtotal = 0.0
        self.gst_total = 0.0

    def _load_menu_from_db(self):
        rows = fetch_menu_items()
        self.menu = []
        seen = set()
        for row in rows:
            if len(row) >= 3:
                name = str(row[0]).strip()
                price = float(row[1])
                gst = float(row[2])
            else:
                continue
            if name not in seen:
                self.menu.append({"name": name, "price": price, "gst": gst})
                seen.add(name)

    def _find_menu_item(self, name):
        name = str(name).strip()
        for it in self.menu:
            if it["name"] == name:
                return it
        return None

    def update_clock(self):
        self.clock_label.configure(text=f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.frame.after(1000, self.update_clock)

    def get_discount_pct(self):
        txt = self.discount_entry.get().strip()
        try:
            return max(0.0, float(txt)) if txt != "" else 0.0
        except:
            return 0.0

    def add_to_order(self):
        try:
            q = int(self.quant_entry.get())
            if q <= 0: raise ValueError
        except ValueError:
            show_msgbox("Error", "Enter valid quantity", "cancel")
            return

        item_name = self.item_dropdown.get().strip()
        item = self._find_menu_item(item_name)
        if not item:
            show_msgbox("Error", "Invalid item selected", "cancel")
            return

        self.order.append({"name": item["name"], "qty": q, "price": item["price"], "gst": item["gst"]})
        self.refresh_order_display()

    def refresh_order_display(self):
        self.order_listbox.delete("1.0", "end")
        subtotal = 0.0
        gst_total = 0.0
        for i, itm in enumerate(self.order, 1):
            line = itm['qty'] * itm['price']
            self.order_listbox.insert("end", f"{i}. {itm['name']} x{itm['qty']} = ₹{line:.2f}\n")
            subtotal += line
            gst_total += line * itm['gst'] / 100.0

        self.subtotal, self.gst_total = subtotal, gst_total

        disc_pct = self.get_discount_pct()
        discount_amount = disc_pct * self.subtotal / 100.0
        final = max(0.0, self.subtotal + self.gst_total - discount_amount)
        self.total_label.configure(text=f"Total: ₹{final:.2f}")

    def clear_order(self):
        self.order.clear()
        self.order_listbox.delete("1.0", "end")
        self.total_label.configure(text="Total: ₹0")
        self.quant_entry.delete(0, "end")
        self.quant_entry.insert(0, "1")
        self.discount_var.set("0")
        if self.menu:
            self.selected_item.set(self.menu[0]["name"])
        else:
            self.selected_item.set("")
        self.mode_cb.set("Dine-In")
        self.payment_method.set("Cash")
        self.subtotal = 0.0
        self.gst_total = 0.0

    def show_bill_summary(self):
        if not self.order:
            show_msgbox("Error", "Add items first", "cancel")
            return

        oid = int(datetime.now().timestamp())
        disc_pct = self.get_discount_pct()
        discount_amount = disc_pct * self.subtotal / 100.0
        final = max(0.0, self.subtotal + self.gst_total - discount_amount)

        mode_val = self.mode_cb.get()
        payment_val = self.payment_method.get()

        try:
            self.save_order_to_db(oid, final, disc_pct, mode_val, payment_val)
            self.append_order_to_csv(oid, final, disc_pct, mode_val, payment_val)
            json_path = self.save_order_to_json(oid, final, disc_pct, mode_val, payment_val)
        except Exception as e:
            show_msgbox("Error", f"Failed to save order: {e}", "cancel")
            return

        bill_popup = ctk.CTkToplevel(self.frame)
        bill_popup.title("Bill Summary")
        bill_popup.geometry("420x520")
        bill_popup.lift()
        bill_popup.attributes("-topmost", True)
        bill_popup.focus_force()

        text = ctk.CTkTextbox(bill_popup, width=390, height=420)
        text.pack(pady=10)
        text.insert("end", f"Order ID: {oid}\nMode: {mode_val}\nPayment: {payment_val}\n\n")
        for itm in self.order:
            text.insert("end", f"{itm['name']} x{itm['qty']} = ₹{itm['qty']*itm['price']:.2f}\n")
        text.insert("end",
                    f"\nSubtotal: ₹{self.subtotal:.2f}"
                    f"\nGST: ₹{self.gst_total:.2f}"
                    f"\nDiscount: {disc_pct}%"
                    f"\nTotal: ₹{final:.2f}")
        text.configure(state="disabled")

        def export_and_close():
            try:
                self.export_bill_to_pdf(oid, self.order, self.subtotal, self.gst_total, disc_pct)
            except Exception as e:
                show_msgbox("Error", f"PDF export error: {e}", "cancel")
            bill_popup.destroy()
            self.clear_order()

        ctk.CTkButton(bill_popup, text="Export as PDF", command=export_and_close).pack(pady=10)
        ctk.CTkButton(bill_popup, text="Open JSON Bill", command=lambda oid=oid: self.open_json_bill(oid)).pack(pady=6)
        if json_path:
            ctk.CTkLabel(bill_popup, text=f"JSON saved: {json_path}", font=("Arial", 10)).pack(pady=(6,4))

    def save_order_to_db(self, oid, final, disc_pct, mode_val=None, payment_val=None):
        conn = s.connect("db/restaurant.db")
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO orders (order_id, mode, payment_method, subtotal, gst, discount, total, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            oid,
            mode_val if mode_val is not None else self.mode_cb.get(),
            payment_val if payment_val is not None else self.payment_method.get(),
            float(self.subtotal),
            float(self.gst_total),
            float(disc_pct),
            float(final),
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        for itm in self.order:
            cur.execute(
                "INSERT INTO order_items(order_id,item_name,quantity,price,gst) VALUES(?,?,?,?,?)",
                (oid, itm['name'].strip(), int(itm['qty']), float(itm['price']), float(itm['gst']))
            )
        conn.commit()
        conn.close()

    def append_order_to_csv(self, order_id, total, discount_pct, mode_val=None, payment_val=None):
        rows = []
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        mode = mode_val if mode_val is not None else self.mode_cb.get()
        payment = payment_val if payment_val is not None else self.payment_method.get()
        for itm in self.order:
            line_total = itm['qty'] * itm['price']
            rows.append({
                "order_id": order_id,
                "timestamp": ts,
                "mode": mode,
                "payment_method": payment,
                "item_name": itm['name'],
                "quantity": itm['qty'],
                "price": itm['price'],
                "gst": itm['gst'],
                "line_total": line_total,
                "subtotal": self.subtotal,
                "gst_total": self.gst_total,
                "discount_pct": discount_pct,
                "total": total
            })
        df = pd.DataFrame(rows)
        try:
            if not os.path.exists(CSV_EXPORT_PATH):
                df.to_csv(CSV_EXPORT_PATH, index=False)
            else:
                df.to_csv(CSV_EXPORT_PATH, mode="a", header=False, index=False)
        except Exception as e:
            show_msgbox("Error", f"CSV export error: {e}", "cancel")

    def save_order_to_json(self, order_id, total, discount_pct, mode_val=None, payment_val=None):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        mode = mode_val if mode_val is not None else self.mode_cb.get()
        payment = payment_val if payment_val is not None else self.payment_method.get()

        bill = {
            "order_id": int(order_id),
            "timestamp": ts,
            "mode": mode,
            "payment_method": payment,
            "items": [],
            "subtotal": float(self.subtotal),
            "gst_total": float(self.gst_total),
            "discount_pct": float(discount_pct),
            "total": float(total)
        }
        for itm in self.order:
            bill["items"].append({
                "item_name": str(itm["name"]),
                "quantity": int(itm["qty"]),
                "price": float(itm["price"]),
                "gst": float(itm["gst"]),
                "line_total": float(itm["qty"] * itm["price"])
            })

        fp = os.path.join(BILLS_JSON_DIR, f"bill_{order_id}.json")
        try:
            with open(fp, "w", encoding="utf-8") as f:
                json.dump(bill, f, ensure_ascii=False, indent=2)
            return fp
        except Exception as e:
            show_msgbox("Error", f"Save JSON error: {e}", "cancel")
            return None

    def open_json_bill(self, order_id):
        fp = os.path.join(BILLS_JSON_DIR, f"bill_{order_id}.json")
        if not os.path.exists(fp):
            show_msgbox("Error", f"No JSON found for order {order_id}", "cancel")
            return
        open_file(fp)

    def open_orders_csv(self):
        if not os.path.exists(CSV_EXPORT_PATH):
            pd.DataFrame(columns=[
                "order_id","timestamp","mode","payment_method","item_name","quantity","price","gst",
                "line_total","subtotal","gst_total","discount_pct","total"
            ]).to_csv(CSV_EXPORT_PATH, index=False)
        open_file(CSV_EXPORT_PATH)

    def export_bill_to_pdf(self, order_id, order_list, subtotal, gst_total, discount):
        os.makedirs(BILLS_JSON_DIR, exist_ok=True)
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", "B", 16)
        pdf.cell(0, 10, "Restaurant Bill", ln=True, align="C")
        pdf.set_font("Arial", size=12)
        pdf.cell(0, 10, f"Order ID: {order_id}", ln=True)
        pdf.cell(0, 10, f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ln=True)
        pdf.ln(5)
        for itm in order_list:
            pdf.cell(0, 10, f"{itm['name']} x{itm['qty']} Rs{itm['price']} | GST:{itm['gst']}%", ln=True)
        pdf.cell(0, 10, f"Subtotal: Rs{subtotal:.2f}", ln=True)
        pdf.cell(0, 10, f"GST: Rs{gst_total:.2f}", ln=True)
        pdf.cell(0, 10, f"Discount: {discount}%", ln=True)
        total_val = subtotal + gst_total - (discount * subtotal / 100.0)
        if total_val < 0:
            total_val = 0.0
        pdf.cell(0, 10, f"Total: Rs{total_val:.2f}", ln=True)
        fp = os.path.abspath(os.path.join(BILLS_JSON_DIR, f"bill_{order_id}.pdf"))
        try:
            pdf.output(fp)
            open_file(fp)
        except Exception as e:
            show_msgbox("Error", f"PDF export error: {e}", "cancel")

    def open_menu_management(self):
        menu_win = ctk.CTkToplevel(self.frame)
        menu_win.title("Menu Management")
        menu_win.geometry("420x420")

        menu_win.lift()
        menu_win.attributes("-topmost", True)
        menu_win.focus_force()

        ctk.CTkLabel(menu_win, text="Add Item", font=("Arial", 14, "bold")).pack(pady=(8,4))

        ctk.CTkLabel(menu_win, text="Item Name:").pack(pady=4)
        name_var = ctk.StringVar()
        name_entry = ctk.CTkEntry(menu_win, textvariable=name_var)
        name_entry.pack(pady=2)

        ctk.CTkLabel(menu_win, text="Category:").pack(pady=4)
        cat_var = ctk.StringVar()
        cat_entry = ctk.CTkEntry(menu_win, textvariable=cat_var)
        cat_entry.pack(pady=2)

        ctk.CTkLabel(menu_win, text="Price:").pack(pady=4)
        price_var = ctk.StringVar(value="0")
        price_entry = ctk.CTkEntry(menu_win, textvariable=price_var)
        price_entry.pack(pady=2)

        ctk.CTkLabel(menu_win, text="GST %:").pack(pady=4)
        gst_var = ctk.StringVar(value="0")
        gst_entry = ctk.CTkEntry(menu_win, textvariable=gst_var)
        gst_entry.pack(pady=2)

        def _refresh_all_dropdowns(set_selected=None):
            self._load_menu_from_db()
            names = [i['name'] for i in self.menu]
            self.item_dropdown.configure(values=names)
            if names:
                if set_selected and set_selected in names:
                    self.selected_item.set(set_selected)
                elif self.selected_item.get() not in names:
                    self.selected_item.set(names[0])
            else:
                self.selected_item.set("")
            del_dropdown.configure(values=names)
            if names:
                delete_var.set(names[0])
            else:
                delete_var.set("")

        def add_item():
            nm = name_entry.get().strip()
            if not nm:
                show_msgbox("Error", "Item name required", "cancel")
                return
            category_val = cat_entry.get().strip()
            price_text = price_entry.get().strip() or "0"
            gst_text = gst_entry.get().strip() or "0"
            try:
                price_v = float(price_text)
                gst_v = float(gst_text)
            except ValueError:
                show_msgbox("Error", "Price/GST must be numbers", "cancel")
                return

            conn = s.connect("db/restaurant.db")
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM menu WHERE lower(item_name) = lower(?) LIMIT 1", (nm,))
            if cur.fetchone():
                conn.close()
                show_msgbox("Error", "Item already exists", "cancel")
                return

            try:
                cur.execute("INSERT INTO menu (item_name, category, price, gst) VALUES (?, ?, ?, ?)",
                            (nm, category_val, price_v, gst_v))
                conn.commit()
            finally:
                conn.close()

            show_msgbox("Success", "Item added", "check")
            name_entry.delete(0, "end")
            cat_entry.delete(0, "end")
            price_entry.delete(0, "end")
            price_entry.insert(0, "0")
            gst_entry.delete(0, "end")
            gst_entry.insert(0, "0")
            _refresh_all_dropdowns(set_selected=nm)

        ctk.CTkButton(menu_win, text="Add Item", command=add_item).pack(pady=(6,10))

        ctk.CTkLabel(menu_win, text="Delete Item", font=("Arial", 14, "bold")).pack(pady=(6,4))
        delete_var = ctk.StringVar()
        items_now = [i['name'] for i in self.menu]
        del_dropdown = ctk.CTkComboBox(menu_win, values=items_now, variable=delete_var)
        del_dropdown.pack(pady=6)
        if items_now:
            delete_var.set(items_now[0])

        def delete_item():
            item_to_delete = del_dropdown.get().strip()
            if not item_to_delete:
                show_msgbox("Error", "Select an item to delete", "cancel")
                return
            conn = s.connect("db/restaurant.db")
            cur = conn.cursor()
            cur.execute("SELECT id FROM menu WHERE lower(item_name) = lower(?) LIMIT 1", (item_to_delete,))
            row = cur.fetchone()
            if not row:
                conn.close()
                show_msgbox("Error", "No matching item found to delete", "cancel")
                return
            menu_id = row[0]
            cur.execute("DELETE FROM menu WHERE id = ?", (menu_id,))
            deleted = cur.rowcount
            conn.commit()
            conn.close()
            if deleted <= 0:
                show_msgbox("Error", "Failed to delete item", "cancel")
            else:
                show_msgbox("Deleted", f"Removed: {item_to_delete}", "check")
            _refresh_all_dropdowns()

        ctk.CTkButton(menu_win, text="Delete Item", command=delete_item).pack(pady=(6,12))

    def refresh_menu(self):
        self._load_menu_from_db()
        names = [i['name'] for i in self.menu]
        self.item_dropdown.configure(values=names)
        if names:
            if self.selected_item.get() not in names:
                self.selected_item.set(names[0])

    def open_reports_window(self):
        rpt_win = ctk.CTkToplevel(self.frame)
        rpt_win.title("Reports")
        rpt_win.geometry("500x200")
        rpt_win.lift()
        rpt_win.focus_force()
        rpt_win.attributes("-topmost", True)
        rpt_win.after(500, lambda: rpt_win.attributes("-topmost", False))

        heading = ctk.CTkLabel(rpt_win, text="Reports", font=("Arial", 16, "bold"))
        heading.pack(pady=(12, 6))

        ctrl_frame = ctk.CTkFrame(rpt_win)
        ctrl_frame.pack(fill="x", padx=12, pady=6)

        ctk.CTkButton(ctrl_frame, text="Export Orders CSV", command=lambda: [self.open_orders_csv(), rpt_win.lift(), rpt_win.focus_force()]).grid(row=0, column=0, padx=6, pady=8)
        ctk.CTkButton(ctrl_frame, text="Export All Bills (JSON)", command=lambda: [self.export_all_bills_json(), rpt_win.lift(), rpt_win.focus_force()]).grid(row=0, column=1, padx=6, pady=8)
        ctrl_frame.grid_columnconfigure(0, weight=1)
        ctrl_frame.grid_columnconfigure(1, weight=1)

    def generate_sales_summary(self, freq, parent_window=None):
        conn = s.connect("db/restaurant.db")
        try:
            df_orders = pd.read_sql_query("SELECT order_id, mode, payment_method, subtotal, gst, discount, total, timestamp FROM orders", conn)
        except Exception:
            df_orders = pd.DataFrame(columns=["order_id", "mode", "payment_method", "subtotal", "gst", "discount", "total", "timestamp"])
        try:
            df_items = pd.read_sql_query("SELECT order_id, item_name, quantity, price, gst FROM order_items", conn)
        except Exception:
            df_items = pd.DataFrame(columns=["order_id", "item_name", "quantity", "price", "gst"])
        conn.close()

        if df_orders.empty:
            text = "No orders found in database.\n"
            return

        df_orders["timestamp"] = pd.to_datetime(df_orders["timestamp"])
        df_orders["date"] = df_orders["timestamp"].dt.date

        if freq == "Daily":
            summary = df_orders.groupby(df_orders["timestamp"].dt.date).agg(
                orders_count=("order_id", "nunique"),
                total_sales=("total", "sum"),
                subtotal_sum=("subtotal", "sum"),
                gst_sum=("gst", "sum")
            ).reset_index().rename(columns={"timestamp": "date"})
        elif freq == "Weekly":
            df_orders["year_week"] = df_orders["timestamp"].dt.strftime("%Y-W%U")
            summary = df_orders.groupby("year_week").agg(
                orders_count=("order_id", "nunique"),
                total_sales=("total", "sum"),
                subtotal_sum=("subtotal", "sum"),
                gst_sum=("gst", "sum")
            ).reset_index()
        else: 
            df_orders["year_month"] = df_orders["timestamp"].dt.strftime("%Y-%m")
            summary = df_orders.groupby("year_month").agg(
                orders_count=("order_id", "nunique"),
                total_sales=("total", "sum"),
                subtotal_sum=("subtotal", "sum"),
                gst_sum=("gst", "sum")
            ).reset_index()

        if not df_items.empty:
            df_items["quantity"] = pd.to_numeric(df_items["quantity"], errors="coerce").fillna(0).astype(int)
            top_items = df_items.groupby("item_name").agg(total_qty=("quantity", "sum")).reset_index().sort_values("total_qty", ascending=False)
            _ = top_items.head(10)

        try:
            summary.to_csv(SALES_REPORT_PATH, index=False)
        except Exception as e:
            show_msgbox("Error", f"Could not save sales report CSV: {e}", "cancel")

    def _write_report_text(self, txt):
        pass

    def export_sales_report_csv(self):
        if not os.path.exists(SALES_REPORT_PATH):
            self.generate_sales_summary("Monthly")
        open_file(SALES_REPORT_PATH)

    def export_all_bills_json(self):
        conn = s.connect("db/restaurant.db")
        try:
            df_orders = pd.read_sql_query("SELECT order_id, mode, payment_method, subtotal, gst, discount, total, timestamp FROM orders", conn)
            df_items = pd.read_sql_query("SELECT order_id, item_name, quantity, price, gst FROM order_items", conn)
        except Exception:
            df_orders = pd.DataFrame()
            df_items = pd.DataFrame()
        conn.close()

        if df_orders.empty:
            show_msgbox("Info", "No orders in database to export.", "check")
            return

        bills = []
        for oid in df_orders["order_id"].unique():
            row = df_orders[df_orders["order_id"] == oid].iloc[0]
            items_df = df_items[df_items["order_id"] == oid] if not df_items.empty else pd.DataFrame()
            items_list = []
            if not items_df.empty:
                for _, it in items_df.iterrows():
                    items_list.append({
                        "item_name": str(it["item_name"]),
                        "quantity": int(it["quantity"]),
                        "price": float(it["price"]),
                        "gst": float(it["gst"]),
                        "line_total": float(it["quantity"]) * float(it["price"])
                    })
            bill = {
                "order_id": int(row["order_id"]),
                "timestamp": str(row["timestamp"]),
                "mode": str(row["mode"]),
                "payment_method": str(row["payment_method"]),
                "items": items_list,
                "subtotal": float(row["subtotal"]),
                "gst_total": float(row["gst"]),
                "discount_pct": float(row["discount"]),
                "total": float(row["total"])
            }
            bills.append(bill)

        try:
            with open(ALL_BILLS_JSON_PATH, "w", encoding="utf-8") as f:
                json.dump(bills, f, ensure_ascii=False, indent=2)
            open_file(ALL_BILLS_JSON_PATH)
        except Exception as e:
            show_msgbox("Error", f"Failed to export all bills JSON: {e}", "cancel")

def open_main_app(role, login_root):
    app_root = ctk.CTk()
    app_root.title("Restaurant Billing")
    app_root.geometry("800x600")
    RestaurantApp(app_root, role)
    app_root.protocol("WM_DELETE_WINDOW", lambda: (login_root.destroy(), app_root.destroy()))
    app_root.mainloop()

def run_app():
    create_folders()
    initialize_database()
    setup_users()
    root = ctk.CTk()
    LoginWindow(root)
    root.mainloop()
