import os
import platform
import shutil
import subprocess
import tempfile
import tkinter as tk
from tkinter import ttk, messagebox
import re

APP = "Windows Detonator"

def run_cmd(command):
    try:
        p = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=15)
        return p.stdout.strip(), p.stderr.strip(), p.returncode
    except Exception as e:
        return "", str(e), 1

def human_bytes(n):
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"

def is_admin():
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

def ram_info():
    # WMIC is available on many Windows installations; PowerShell is fallback.
    out, _, rc = run_cmd(
        'wmic OS get FreePhysicalMemory,TotalVisibleMemorySize /Value'
    )
    vals = {}
    if rc == 0:
        for line in out.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                try:
                    vals[k.strip()] = int(v.strip()) * 1024
                except ValueError:
                    pass
    if vals.get("TotalVisibleMemorySize"):
        total = vals["TotalVisibleMemorySize"]
        free = vals.get("FreePhysicalMemory", 0)
        used = max(total - free, 0)
        pct = used / total * 100
        return total, free, used, pct

    ps = ("powershell -NoProfile -Command "
          '"$m=Get-CimInstance Win32_OperatingSystem; '
          '"[Console]::WriteLine(($m.TotalVisibleMemorySize*1024));'
          '"[Console]::WriteLine(($m.FreePhysicalMemory*1024))"')
    out, _, rc = run_cmd(ps)
    nums = [int(x) for x in re.findall(r"\d+", out)]
    if len(nums) >= 2:
        total, free = nums[0], nums[1]
        used = max(total-free, 0)
        return total, free, used, used/total*100
    return None

def clean_temp():
    deleted = 0
    freed = 0
    paths = list(dict.fromkeys([tempfile.gettempdir(),
                                os.environ.get("TEMP"),
                                os.environ.get("TMP")]))
    for path in [p for p in paths if p]:
        for root, dirs, files in os.walk(path, topdown=False):
            for name in files:
                fp = os.path.join(root, name)
                try:
                    size = os.path.getsize(fp)
                    os.remove(fp)
                    deleted += 1
                    freed += size
                except OSError:
                    pass
            for name in dirs:
                try:
                    os.rmdir(os.path.join(root, name))
                except OSError:
                    pass
    return deleted, freed

def firewall_block(ip):
    # Validate IPv4/IPv6 characters before passing to netsh.
    if not re.fullmatch(r"[0-9A-Fa-f:.]+", ip):
        raise ValueError("Invalid IP address.")
    rule = "WindowsDetonator_Block_" + ip.replace(":", "_").replace(".", "_")
    out, err, rc = run_cmd(
        f'netsh advfirewall firewall add rule name="{rule}" '
        f'dir=in action=block remoteip={ip}'
    )
    if rc != 0:
        raise RuntimeError(err or out or "Firewall command failed.")
    return rule

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Windows Detonator — Defensive Prototype")
        self.geometry("900x630")
        self.minsize(800, 560)

        ttk.Label(self, text="WINDOWS DETONATOR",
                  font=("Segoe UI", 22, "bold")).pack(pady=(12, 0))
        ttk.Label(self, text="Detect • Diagnose • Defuse",
                  font=("Segoe UI", 11)).pack()
        self.status = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status).pack(pady=6)

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=8)

        self.system_tab = ttk.Frame(nb, padding=12)
        self.memory_tab = ttk.Frame(nb, padding=12)
        self.network_tab = ttk.Frame(nb, padding=12)

        nb.add(self.system_tab, text="System Debug")
        nb.add(self.memory_tab, text="Cache & RAM")
        nb.add(self.network_tab, text="DDoS Guard")

        self.build_system()
        self.build_memory()
        self.build_network()

    def build_system(self):
        ttk.Label(self.system_tab, text="Windows / Hardware Diagnostics",
                  font=("Segoe UI", 15, "bold")).pack(anchor="w")
        self.output = tk.Text(self.system_tab, font=("Consolas", 10))
        self.output.pack(fill="both", expand=True, pady=8)
        ttk.Button(self.system_tab, text="Run Diagnostics",
                   command=self.debug).pack(anchor="w")

    def debug(self):
        lines = [
            f"OS: {platform.platform()}",
            f"Computer: {platform.node()}",
            f"Python runtime: {platform.python_version()}",
            f"Administrator: {'YES' if is_admin() else 'NO'}"
        ]
        mem = ram_info()
        if mem:
            total, free, used, pct = mem
            lines += [
                f"RAM total: {human_bytes(total)}",
                f"RAM used: {human_bytes(used)} ({pct:.1f}%)",
                f"RAM available: {human_bytes(free)}"
            ]
        else:
            lines.append("RAM information could not be read.")

        drive = os.environ.get("SystemDrive", "C:") + "\\"
        try:
            d = shutil.disk_usage(drive)
            lines += [
                f"System drive: {drive}",
                f"Disk used: {human_bytes(d.used)} / {human_bytes(d.total)} ({d.used/d.total*100:.1f}%)",
                f"Disk free: {human_bytes(d.free)}"
            ]
        except OSError:
            pass

        out, err, _ = run_cmd("ipconfig /all")
        lines.append("\nNetwork configuration:\n" + (out or err))
        self.output.delete("1.0", "end")
        self.output.insert("end", "\n".join(lines))
        self.status.set("Diagnostics complete")

    def build_memory(self):
        ttk.Label(self.memory_tab, text="Cache Cleanup & Memory Health",
                  font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(
            self.memory_tab,
            text=("Physical RAM cannot be increased by software. "
                  "This module reports RAM health and cleans the current user's TEMP files."),
            wraplength=780
        ).pack(anchor="w", pady=8)

        self.mem_label = ttk.Label(self.memory_tab, text="")
        self.mem_label.pack(anchor="w", pady=8)

        ttk.Button(self.memory_tab, text="Refresh RAM",
                   command=self.refresh_ram).pack(anchor="w", pady=4)
        ttk.Button(self.memory_tab, text="Clean TEMP Cache",
                   command=self.clean_cache).pack(anchor="w", pady=4)

        ttk.Label(
            self.memory_tab,
            text="Locked files are skipped. Windows component files are not blindly deleted.",
            wraplength=780
        ).pack(anchor="w", pady=15)
        self.refresh_ram()

    def refresh_ram(self):
        mem = ram_info()
        if not mem:
            self.mem_label.config(text="RAM information unavailable.")
            return
        total, free, used, pct = mem
        self.mem_label.config(
            text=f"Used: {human_bytes(used)} / {human_bytes(total)}   "
                 f"| Available: {human_bytes(free)}   | Usage: {pct:.1f}%"
        )
        self.status.set("RAM status refreshed")

    def clean_cache(self):
        if not messagebox.askyesno(
            "Confirm cleanup",
            "Delete files from the current user's TEMP folders?\n"
            "Locked files will be skipped."
        ):
            return
        deleted, freed = clean_temp()
        self.status.set("TEMP cleanup complete")
        messagebox.showinfo(
            APP,
            f"Cleanup finished.\n\nFiles deleted: {deleted}\nSpace freed: {human_bytes(freed)}"
        )
        self.refresh_ram()

    def build_network(self):
        ttk.Label(self.network_tab, text="Defensive DDoS / Connection Monitor",
                  font=("Segoe UI", 15, "bold")).pack(anchor="w")
        ttk.Label(
            self.network_tab,
            text=("Shows active network connections using Windows netstat. "
                  "Select an IP to create an inbound Windows Firewall block rule. "
                  "This is endpoint defense; it does not generate attack traffic "
                  "or stop upstream volumetric DDoS by itself."),
            wraplength=780
        ).pack(anchor="w", pady=8)

        bar = ttk.Frame(self.network_tab)
        bar.pack(fill="x")
        ttk.Button(bar, text="Scan Connections",
                   command=self.scan_connections).pack(side="left")
        ttk.Button(bar, text="Block Selected IP",
                   command=self.block_selected).pack(side="left", padx=8)

        self.tree = ttk.Treeview(
            self.network_tab, columns=("ip", "count"), show="headings"
        )
        self.tree.heading("ip", text="Remote IP")
        self.tree.heading("count", text="Connection Count")
        self.tree.column("ip", width=520)
        self.tree.column("count", width=180, anchor="center")
        self.tree.pack(fill="both", expand=True, pady=8)

    def scan_connections(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        out, err, rc = run_cmd("netstat -ano")
        if rc != 0:
            messagebox.showerror("Scan failed", err or out)
            return

        counts = {}
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 4 and parts[0].upper() in ("TCP", "UDP"):
                remote = parts[2] if parts[0].upper() == "TCP" else parts[1]
                if remote and remote != "*:*":
                    ip = remote.rsplit(":", 1)[0]
                    if ip.startswith("[") and "]" in ip:
                        ip = ip[1:ip.index("]")]
                    counts[ip] = counts.get(ip, 0) + 1

        for ip, count in sorted(counts.items(), key=lambda x: x[1], reverse=True)[:50]:
            self.tree.insert("", "end", values=(ip, count))

        self.status.set(f"Found {len(counts)} remote IPs")

    def block_selected(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Select IP", "Select a remote IP first.")
            return

        ip = self.tree.item(selected[0], "values")[0]
        if not messagebox.askyesno(
            "Confirm firewall block",
            f"Create an inbound Windows Firewall block rule for:\n{ip}?"
        ):
            return

        try:
            rule = firewall_block(ip)
            self.status.set(f"Firewall rule created for {ip}")
            messagebox.showinfo(
                "Windows Detonator",
                f"Firewall rule created.\n\nRule: {rule}\n\n"
                "Run as Administrator if Windows denies the action."
            )
        except Exception as e:
            messagebox.showerror(
                "Firewall action failed",
                f"{e}\n\nRun the application as Administrator."
            )

if __name__ == "__main__":
    App().mainloop()
