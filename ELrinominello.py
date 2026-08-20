import os
import re
import json
import shutil
import threading
import unicodedata
from pathlib import Path
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

APP_NAME = "ELrinominello"
CONFIG_PATH = Path.home() / ".elrinominello.json"


def normalize_text(value):
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^A-Za-z0-9 _.-]+", "", value)
    value = re.sub(r"\s+", "_", value.strip())
    value = re.sub(r"_+", "_", value)
    return value or "File"


def unique_path(path, reserved=None):
    reserved = reserved or set()
    if not path.exists() and str(path).casefold() not in reserved:
        return path
    stem, suffix = path.stem, path.suffix
    index = 1
    while True:
        candidate = path.with_name(f"{stem}_{index}{suffix}")
        if not candidate.exists() and str(candidate).casefold() not in reserved:
            return candidate
        index += 1


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1180x760")
        self.minsize(980, 650)
        self.files = []
        self.plan = []
        self.history = []
        self.build_ui()
        self.load_config()
        self.protocol("WM_DELETE_WINDOW", self.close)

    def build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = ctk.CTkFrame(self, corner_radius=0, width=290)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(sidebar, text="ELrinominello", font=ctk.CTkFont(size=28, weight="bold")).grid(row=0, column=0, padx=24, pady=(28, 2), sticky="w")
        ctk.CTkLabel(sidebar, text="Rinomina i tuoi file in modo elegante", text_color="gray70", wraplength=230).grid(row=1, column=0, padx=24, pady=(0, 24), sticky="w")

        ctk.CTkButton(sidebar, text="Scegli cartella", height=42, command=self.choose_folder).grid(row=2, column=0, padx=24, pady=7, sticky="ew")
        self.folder_label = ctk.CTkLabel(sidebar, text="Nessuna cartella selezionata", text_color="gray60", wraplength=230, justify="left")
        self.folder_label.grid(row=3, column=0, padx=24, pady=(0, 16), sticky="w")

        ctk.CTkLabel(sidebar, text="Opzioni", font=ctk.CTkFont(size=16, weight="bold")).grid(row=4, column=0, padx=24, pady=(8, 8), sticky="w")
        self.include_subfolders = ctk.BooleanVar(value=False)
        self.keep_extension = ctk.BooleanVar(value=True)
        self.case_sensitive = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(sidebar, text="Includi sottocartelle", variable=self.include_subfolders, command=self.refresh_files).grid(row=5, column=0, padx=24, pady=5, sticky="w")
        ctk.CTkCheckBox(sidebar, text="Mantieni estensione", variable=self.keep_extension).grid(row=6, column=0, padx=24, pady=5, sticky="w")
        ctk.CTkCheckBox(sidebar, text="Maiuscole/minuscole", variable=self.case_sensitive).grid(row=7, column=0, padx=24, pady=5, sticky="w")

        ctk.CTkLabel(sidebar, text="Aspetto", font=ctk.CTkFont(size=16, weight="bold")).grid(row=8, column=0, padx=24, pady=(22, 8), sticky="w")
        self.appearance = ctk.CTkOptionMenu(sidebar, values=["Sistema", "Chiaro", "Scuro"], command=self.change_appearance)
        self.appearance.grid(row=9, column=0, padx=24, pady=5, sticky="ew")

        ctk.CTkButton(sidebar, text="Ripristina ultima operazione", fg_color="#7f1d1d", hover_color="#991b1b", command=self.undo).grid(row=10, column=0, padx=24, pady=(30, 7), sticky="ew")
        ctk.CTkButton(sidebar, text="Esporta piano CSV", fg_color="#374151", hover_color="#4b5563", command=self.export_csv).grid(row=11, column=0, padx=24, pady=7, sticky="ew")

        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=0, column=1, sticky="nsew", padx=24, pady=24)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(main, text="Configurazione rinomina", font=ctk.CTkFont(size=24, weight="bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(main, text="Configura il modello, controlla l'anteprima e applica le modifiche in sicurezza.", text_color="gray60").grid(row=1, column=0, sticky="w", pady=(4, 18))

        controls = ctk.CTkFrame(main)
        controls.grid(row=2, column=0, sticky="nsew")
        controls.grid_columnconfigure(1, weight=1)
        controls.grid_rowconfigure(9, weight=1)

        ctk.CTkLabel(controls, text="Modalità").grid(row=0, column=0, padx=16, pady=(16, 8), sticky="w")
        self.mode = ctk.StringVar(value="Nome + numero")
        self.mode_menu = ctk.CTkOptionMenu(controls, variable=self.mode, values=["Nome + numero", "Nome + data", "Nome + data + numero", "Prefisso + nome originale", "Sostituisci testo", "Sequenza personalizzata"], command=self.update_form)
        self.mode_menu.grid(row=0, column=1, padx=16, pady=(16, 8), sticky="ew")

        self.form = ctk.CTkFrame(controls, fg_color="transparent")
        self.form.grid(row=1, column=0, columnspan=2, sticky="ew", padx=8)
        self.form.grid_columnconfigure(1, weight=1)
        self.create_form()

        ctk.CTkLabel(controls, text="Anteprima", font=ctk.CTkFont(size=16, weight="bold")).grid(row=8, column=0, columnspan=2, padx=16, pady=(12, 8), sticky="w")
        self.preview = ctk.CTkTextbox(controls, height=260, wrap="none")
        self.preview.grid(row=9, column=0, columnspan=2, padx=16, pady=(0, 14), sticky="nsew")

        actions = ctk.CTkFrame(controls, fg_color="transparent")
        actions.grid(row=10, column=0, columnspan=2, padx=16, pady=(0, 16), sticky="ew")
        actions.grid_columnconfigure(0, weight=1)
        actions.grid_columnconfigure(1, weight=1)
        ctk.CTkButton(actions, text="Genera anteprima", height=44, command=self.generate_preview).grid(row=0, column=0, padx=(0, 6), sticky="ew")
        ctk.CTkButton(actions, text="Rinomina file", height=44, fg_color="#16a34a", hover_color="#15803d", command=self.rename_files).grid(row=0, column=1, padx=(6, 0), sticky="ew")

        self.status = ctk.CTkLabel(main, text="Pronto", text_color="gray60")
        self.status.grid(row=3, column=0, pady=(12, 0), sticky="w")

    def create_form(self):
        for widget in self.form.winfo_children():
            widget.destroy()
        mode = self.mode.get()
        self.entries = {}
        row = 0
        if mode in ["Nome + numero", "Nome + data", "Nome + data + numero"]:
            self.add_entry("Nome base", "base", "File", row)
            row += 1
        if mode in ["Nome + numero", "Nome + data + numero"]:
            self.add_entry("Numero iniziale", "start", "1", row)
            row += 1
            self.add_entry("Cifre numero", "digits", "3", row)
            row += 1
        if mode in ["Nome + data", "Nome + data + numero"]:
            self.add_entry("Formato data", "date_format", "%Y-%m-%d", row)
            row += 1
            self.date_source = ctk.StringVar(value="Data modifica")
            ctk.CTkLabel(self.form, text="Origine data").grid(row=row, column=0, padx=8, pady=6, sticky="w")
            ctk.CTkOptionMenu(self.form, variable=self.date_source, values=["Data modifica", "Data creazione", "Data odierna"]).grid(row=row, column=1, padx=8, pady=6, sticky="ew")
            row += 1
        if mode == "Prefisso + nome originale":
            self.add_entry("Prefisso", "prefix", "Archivio", row)
            row += 1
            self.add_entry("Separatore", "separator", "_", row)
            row += 1
        if mode == "Sostituisci testo":
            self.add_entry("Testo da cercare", "find", "", row)
            row += 1
            self.add_entry("Sostituisci con", "replace", "", row)
            row += 1
        if mode == "Sequenza personalizzata":
            self.add_entry("Modello", "template", "Foto_{date}_{num}_{orig}", row)
            row += 1
            self.add_entry("Formato data", "date_format", "%Y-%m-%d", row)
            row += 1
            self.add_entry("Cifre numero", "digits", "3", row)
            row += 1
        self.add_entry("Estensioni", "extensions", "Tutte", row)
        row += 1
        self.sort_var = ctk.StringVar(value="Nome crescente")
        ctk.CTkLabel(self.form, text="Ordinamento").grid(row=row, column=0, padx=8, pady=6, sticky="w")
        ctk.CTkOptionMenu(self.form, variable=self.sort_var, values=["Nome crescente", "Nome decrescente", "Data crescente", "Data decrescente", "Dimensione crescente", "Dimensione decrescente"]).grid(row=row, column=1, padx=8, pady=6, sticky="ew")

    def add_entry(self, label, key, value, row):
        ctk.CTkLabel(self.form, text=label).grid(row=row, column=0, padx=8, pady=6, sticky="w")
        entry = ctk.CTkEntry(self.form)
        entry.insert(0, value)
        entry.grid(row=row, column=1, padx=8, pady=6, sticky="ew")
        self.entries[key] = entry

    def update_form(self, _=None):
        self.create_form()
        self.generate_preview()

    def change_appearance(self, value):
        ctk.set_appearance_mode({"Sistema": "System", "Chiaro": "Light", "Scuro": "Dark"}[value])

    def choose_folder(self):
        folder = filedialog.askdirectory(title="Scegli una cartella")
        if folder:
            self.folder = Path(folder)
            self.folder_label.configure(text=str(self.folder))
            self.refresh_files()

    def refresh_files(self):
        if not hasattr(self, "folder"):
            return
        pattern = "**/*" if self.include_subfolders.get() else "*"
        self.files = [p for p in self.folder.glob(pattern) if p.is_file()]
        self.status.configure(text=f"{len(self.files)} file caricati")
        self.generate_preview()

    def sorted_files(self):
        files = list(self.files)
        option = self.sort_var.get()
        if option.startswith("Nome"):
            files.sort(key=lambda p: p.name.casefold(), reverse=option.endswith("decrescente"))
        elif option.startswith("Data"):
            files.sort(key=lambda p: p.stat().st_mtime, reverse=option.endswith("decrescente"))
        else:
            files.sort(key=lambda p: p.stat().st_size, reverse=option.endswith("decrescente"))
        extensions = self.entries.get("extensions")
        if extensions and extensions.get().strip().lower() not in ["", "tutte", "tutti", "*"]:
            allowed = {x.strip().lower().lstrip(".") for x in extensions.get().split(",")}
            files = [p for p in files if p.suffix.lower().lstrip(".") in allowed]
        return files

    def file_date(self, path):
        source = getattr(self, "date_source", tk.StringVar(value="Data modifica")).get()
        if source == "Data odierna":
            return datetime.now()
        if source == "Data creazione":
            timestamp = path.stat().st_ctime
        else:
            timestamp = path.stat().st_mtime
        return datetime.fromtimestamp(timestamp)

    def build_name(self, path, index):
        mode = self.mode.get()
        values = {key: entry.get() for key, entry in self.entries.items()}
        original = path.stem if self.keep_extension.get() else path.name
        number = int(values.get("start", "1") or 1) + index
        digits = max(1, int(values.get("digits", "3") or 3))
        num = str(number).zfill(digits)
        date = self.file_date(path).strftime(values.get("date_format", "%Y-%m-%d")) if "date_format" in values else ""
        if mode == "Nome + numero":
            stem = f"{values.get('base', 'File')}_{num}"
        elif mode == "Nome + data":
            stem = f"{values.get('base', 'File')}_{date}"
        elif mode == "Nome + data + numero":
            stem = f"{values.get('base', 'File')}_{date}_{num}"
        elif mode == "Prefisso + nome originale":
            stem = f"{values.get('prefix', 'Archivio')}{values.get('separator', '_')}{original}"
        elif mode == "Sostituisci testo":
            stem = original.replace(values.get("find", ""), values.get("replace", ""))
        else:
            stem = values.get("template", "File_{num}").replace("{num}", num).replace("{date}", date).replace("{orig}", original).replace("{name}", original)
        stem = normalize_text(stem)
        return path.with_name(stem + path.suffix if self.keep_extension.get() else stem)

    def generate_preview(self):
        if not hasattr(self, "files"):
            return
        self.plan = []
        reserved = set()
        for index, source in enumerate(self.sorted_files()):
            target = self.build_name(source, index)
            target = unique_path(target, reserved)
            reserved.add(str(target).casefold())
            self.plan.append((source, target))
        self.preview.delete("1.0", "end")
        for source, target in self.plan:
            self.preview.insert("end", f"{source.name}  →  {target.name}\n")
        self.status.configure(text=f"Anteprima pronta: {len(self.plan)} file")

    def rename_files(self):
        if not self.plan:
            self.generate_preview()
        changes = [(a, b) for a, b in self.plan if a != b]
        if not changes:
            messagebox.showinfo(APP_NAME, "Non ci sono modifiche da applicare.")
            return
        if not messagebox.askyesno(APP_NAME, f"Rinominare {len(changes)} file?"):
            return
        try:
            temporary = []
            for index, (source, target) in enumerate(changes):
                temp = source.with_name(f".__elrinominello_tmp_{index}_{source.name}")
                source.rename(temp)
                temporary.append((temp, target, source))
            for temp, target, source in temporary:
                target.parent.mkdir(parents=True, exist_ok=True)
                temp.rename(target)
            self.history.append([(source, target) for _, target, source in temporary])
            self.refresh_files()
            messagebox.showinfo(APP_NAME, "Rinomina completata.")
        except Exception as error:
            messagebox.showerror(APP_NAME, f"Operazione interrotta: {error}")

    def undo(self):
        if not self.history:
            messagebox.showinfo(APP_NAME, "Nessuna operazione da ripristinare.")
            return
        changes = self.history.pop()
        try:
            for original, current in reversed(changes):
                if current.exists():
                    current.rename(original)
            self.refresh_files()
            messagebox.showinfo(APP_NAME, "Ultima operazione ripristinata.")
        except Exception as error:
            messagebox.showerror(APP_NAME, f"Ripristino interrotto: {error}")

    def export_csv(self):
        if not self.plan:
            self.generate_preview()
        path = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        import csv
        with open(path, "w", newline="", encoding="utf-8-sig") as file:
            writer = csv.writer(file, delimiter=";")
            writer.writerow(["Nome originale", "Nuovo nome", "Percorso originale", "Percorso nuovo"])
            writer.writerows([[a.name, b.name, str(a), str(b)] for a, b in self.plan])
        messagebox.showinfo(APP_NAME, "Piano CSV esportato.")

    def load_config(self):
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            self.appearance.set(data.get("appearance", "Sistema"))
            self.change_appearance(self.appearance.get())
        except Exception:
            pass

    def save_config(self):
        CONFIG_PATH.write_text(json.dumps({"appearance": self.appearance.get()}, ensure_ascii=False, indent=2), encoding="utf-8")

    def close(self):
        self.save_config()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
