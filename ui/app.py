#!/usr/bin/env python3
# app.py
import threading
import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import requests
import os
import sys
import itertools

API_BASE = os.getenv("APP_API_BASE", "https://web.com/api")  # change if needed

class FrontDisplay(tk.Frame):
    def __init__(self, master, onAuthSuccess):
        super().__init__(master)
        self.onAuthSuccess = onAuthSuccess
        self.createWidgets()

    def createWidgets(self):
        tk.Label(self, text="Welcome — please authenticate").pack(pady=8)
        tk.Label(self, text="Username").pack()
        self.usernameEntry = tk.Entry(self)
        self.usernameEntry.pack(pady=4)
        tk.Label(self, text="Password").pack()
        self.passwordEntry = tk.Entry(self, show="*")
        self.passwordEntry.pack(pady=4)

        self.statusLabel = tk.Label(self, text="", fg="blue")
        self.statusLabel.pack(pady=4)

        self.loginBtn = tk.Button(self, text="Login", command=self.attemptLogin)
        self.loginBtn.pack(pady=6)

    def attemptLogin(self):
        user = self.usernameEntry.get().strip()
        pwd = self.passwordEntry.get().strip()
        if not user or not pwd:
            messagebox.showwarning("Missing", "Enter username and password.")
            return
        self.loginBtn.config(state="disabled")
        self.statusLabel.config(text="Authenticating...")
        # run network call in a thread to avoid freezing UI
        threading.Thread(target=self._doAuth, args=(user, pwd), daemon=True).start()

    def _doAuth(self, username, password):
        fakeToken = "dev-token-123"
        fakeResp = {"username": username, "dev": True}
        self.after(0, lambda: self.onAuthSuccess(fakeToken, fakeResp))
        return
        try:
            url = f"{API_BASE}/auth"  # adjust endpoint if needed
            resp = requests.post(url, json={"username": username, "password": password}, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            token = data.get("token") or data.get("access_token")
            if not token:
                raise ValueError("no token in response")
            # success: call back on main thread
            self.after(0, lambda: self.onAuthSuccess(token, data))
        except Exception as e:
            self.after(0, lambda e=e: self._authFailed(e))

    def _authFailed(self, exc):
        self.statusLabel.config(text=f"Failed: {exc}")
        self.loginBtn.config(state="normal")


class MainDisplay(tk.Frame):
    def __init__(self, master, token, meta, onLogout):
        super().__init__(master, bd=2, relief="groove", padx=8, pady=8)
        self.token = token
        self.meta = meta or {}
        self.onLogout = onLogout

        # spinner state
        self._spinnerIter = itertools.cycle("|/-\\")
        self._spinning = False

        self.createWidgets()
        self.populateTableWithFakeData()  # initial seed

    def createWidgets(self):
        # top: greeting + refresh (spinner)
        topFrame = tk.Frame(self)
        topFrame.pack(fill="x", pady=(0,8))

        userLabelText = self.meta.get("user") or self.meta.get("username") or "user"
        greeting = tk.Label(topFrame, text=f"Selamat (pagi/siang/sore/malam), {userLabelText}!", anchor="w")
        greeting.pack(side="left")

        # spinner + refresh button on right
        self.spinnerLabel = tk.Label(topFrame, text=" ")  # will show spinner chars
        self.spinnerLabel.pack(side="right", padx=(6,0))

        refreshBtn = tk.Button(topFrame, text="Refresh", command=self.onRefreshClicked)
        refreshBtn.pack(side="right", padx=(0,6))

        logoutBtn = tk.Button(topFrame, text="Logout", command=self.doLogout)
        logoutBtn.pack(side="right")

        # main body: left filters, right table
        bodyFrame = tk.Frame(self)
        bodyFrame.pack(fill="both", expand=True)

        # left filter column
        leftCol = tk.Frame(bodyFrame, width=220)
        leftCol.pack(side="left", fill="y", padx=(0,12))

        # filter items (stacked)
        ttk.Label(leftCol, text="Tabel").pack(anchor="w", pady=(0,4))
        self.tableCombo = ttk.Combobox(leftCol, values=["reads", "teachers", "users"], state="readonly")
        self.tableCombo.current(0)
        self.tableCombo.pack(fill="x", pady=(0,8))

        ttk.Label(leftCol, text="Jenis").pack(anchor="w", pady=(0,4))
        self.typeCombo = ttk.Combobox(leftCol, values=["Semua","Artikel","Berita","Pengumuman"], state="readonly")
        self.typeCombo.current(0)
        self.typeCombo.pack(fill="x", pady=(0,8))

        ttk.Label(leftCol, text="Urut berdasarkan").pack(anchor="w", pady=(0,4))
        self.orderCombo = ttk.Combobox(leftCol, values=["created DESC","created ASC","title ASC"], state="readonly")
        self.orderCombo.current(0)
        self.orderCombo.pack(fill="x", pady=(0,8))

        # extra filters (ellipsis in wireframe)
        ttk.Label(leftCol, text="Filter 1").pack(anchor="w", pady=(8,4))
        self.filter1 = ttk.Combobox(leftCol, values=["-","A","B","C"], state="readonly")
        self.filter1.current(0)
        self.filter1.pack(fill="x", pady=(0,8))

        ttk.Label(leftCol, text="Filter 2").pack(anchor="w", pady=(0,4))
        self.filter2 = ttk.Combobox(leftCol, values=["-","X","Y","Z"], state="readonly")
        self.filter2.current(0)
        self.filter2.pack(fill="x", pady=(0,8))

        # Edit content button at bottom-left
        tk.Button(leftCol, text="Edit konten", command=self.onEditContent, width=16).pack(side="bottom", pady=(12,0))

        # right: table
        rightCol = tk.Frame(bodyFrame)
        rightCol.pack(side="left", fill="both", expand=True)

        # Treeview (table) with scrollbar
        cols = ("idx", "judul", "uuid", "pembuat")
        self.tree = ttk.Treeview(rightCol, columns=cols, show="headings", height=12)
        self.tree.heading("idx", text="#")
        self.tree.heading("judul", text="Judul")
        self.tree.heading("uuid", text="UUID")
        self.tree.heading("pembuat", text="Pembuat")
        self.tree.column("idx", width=40, anchor="center")
        self.tree.column("judul", width=240, anchor="w")
        self.tree.column("uuid", width=220, anchor="w")
        self.tree.column("pembuat", width=140, anchor="w")

        vsb = ttk.Scrollbar(rightCol, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(rightCol, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        rightCol.grid_rowconfigure(0, weight=1)
        rightCol.grid_columnconfigure(0, weight=1)

        # binds: filter change -> refresh table
        for widget in (self.tableCombo, self.typeCombo, self.orderCombo, self.filter1, self.filter2):
            widget.bind("<<ComboboxSelected>>", lambda e: self.onFiltersChanged())

        # double-click on row -> open edit (or preview)
        self.tree.bind("<Double-1>", self.onRowDouble)

    # --- actions ---
    def onRefreshClicked(self):
        # simulate network refresh: start spinner and reload table (fake)
        if self._spinning:
            return
        self._spinning = True
        self._animateSpinner()
        # in real app: spawn thread to fetch using self.token and filters
        self.after(800, self._stopSpinnerAndReload)  # simulate short delay

    def _animateSpinner(self):
        if not self._spinning:
            self.spinnerLabel.config(text=" ")
            return
        ch = next(self._spinnerIter)
        self.spinnerLabel.config(text=ch)
        self.after(120, self._animateSpinner)

    def _stopSpinnerAndReload(self):
        self._spinning = False
        self.spinnerLabel.config(text=" ")
        self.populateTableWithFakeData()

    def onFiltersChanged(self):
        # in production you'd refetch using the filters; here we just refresh
        self.populateTableWithFakeData()

    def onRowDouble(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        item = self.tree.item(sel[0])
        vals = item.get("values", [])
        uuid = vals[2] if len(vals) > 2 else None
        messagebox.showinfo("Row selected", f"UUID: {uuid}")

    def onEditContent(self):
        messagebox.showinfo("Edit", "Open content editor (hook here)")

    # --- data population (replace with real API call) ---
    def populateTableWithFakeData(self):
        # clear
        for r in self.tree.get_children():
            self.tree.delete(r)
        # example rows matching your sketch (1 and 44 as left-most numbers)
        sample = [
            (1, "Judul Pertama", "6b643e3d-7bac-5850-93e8-7c477d000001", "Admin A"),
            (44, "Judul Kedua sangat panjang contohnya...", "6b643e3d-7bac-5850-93e8-7c477d00002", "Editor B"),
        ]
        for row in sample:
            self.tree.insert("", "end", values=row)

    def doLogout(self):
        # forward
        self.onLogout()


class SMAN2PORTAL(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Two-screen Auth App")
        self.geometry("480x280")
        self.resizable(False, False)
        self.currentFrame = None
        self.token = None
        self.showFront()

    def replaceFrame(self, frame):
        if self.currentFrame:
            self.currentFrame.destroy()
        self.currentFrame = frame
        self.currentFrame.pack(expand=True, fill="both")

    def showFront(self):
        self.replaceFrame(FrontDisplay(self, self.onAuthSuccess))

    def onAuthSuccess(self, token, meta):
        self.token = token
        self.replaceFrame(MainDisplay(self, token, meta, self.onLogout))

    def onLogout(self):
        self.token = None
        self.showFront()

def main():
    app = SMAN2PORTAL()
    app.mainloop()

if __name__ == "__main__":
    main()
