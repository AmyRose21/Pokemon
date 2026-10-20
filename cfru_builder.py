#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 CFRU Builder — Compilador DPE -> CFRU para Pokemon FireRed
================================================================================
 App de escritorio (Tkinter) en español que automatiza la instalacion de:
   * DPE  (Dynamic Pokemon Expansion, incluida version Gen 9 de Shiny-Miner)
   * CFRU (Complete FireRed Upgrade, incluido fork CFRU-expansion de Shiny-Miner)

 Flujo soportado (por pasos, como en la guia oficial de Skeli789):
   1. Respalda tu ROM original.
   2. Copia tu ROM a la carpeta del DPE como BPRE0.gba.
   3. Ejecuta  python scripts/make.py  dentro del DPE  ->  test.gba
   4. PAUSA: revisas el resultado y pulsas "Continuar".
   5. Copia el test.gba del DPE a la carpeta del CFRU como BPRE0.gba.
   6. Ejecuta  python scripts/make.py  dentro del CFRU  ->  test.gba final
   7. Guarda la ROM final con nombre y carpeta elegidos.

 Modo actualizacion: reinstalar SOLO el DPE o SOLO el CFRU cuando editaste
 habilidades, movimientos, items, etc. en los archivos fuente del repo.

 Requisitos (los mismos de la guia oficial):
   * Python 3.7.x  (el CFRU/DPE originales NO recomiendan 3.8+)
   * devkitPro + devkitARM con su carpeta bin en el PATH
   * ROM Pokemon FireRed US 1.0 (header BPRE)

 Ejecutar:  python cfru_builder.py   (o doble clic en Iniciar_CFRU_Builder.bat)
================================================================================
"""

import os
import sys
import json
import re
import stat
import errno
import time
import queue
import shutil
import socket
import threading
import subprocess

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    from tkinter.scrolledtext import ScrolledText
except Exception:  # pragma: no cover
    print("ERROR: este programa necesita Tkinter, que viene incluido con Python.")
    sys.exit(1)

APP_NAME = "CFRU Builder"
APP_VERSION = "1.3.0"

# ---------------------------------------------------------------------------
# Paleta "Dark gamer" (GitHub-dark con acentos GBA)
# ---------------------------------------------------------------------------
C_BG      = "#0d1117"   # fondo principal
C_PANEL   = "#161b22"   # tarjetas / paneles
C_PANEL2  = "#1c2128"   # paneles elevados / consola frame
C_INPUT   = "#010409"   # fondo de inputs y consola
C_BORDER  = "#30363d"   # bordes
C_FG      = "#e6edf3"   # texto principal
C_MUTED   = "#8b949e"   # texto secundario
C_GREEN   = "#3fb950"   # verde GBA (ok)
C_GREEN_D = "#238636"   # verde boton
C_RED     = "#f85149"   # rojo pokedex (error)
C_YELLOW  = "#d29922"   # amarillo (aviso)
C_BLUE    = "#58a6ff"   # azul info
C_PURPLE  = "#a371f7"   # morado acento

FONT_UI    = ("Segoe UI", 9)
FONT_UI_B  = ("Segoe UI", 9, "bold")
FONT_TITLE = ("Segoe UI", 16, "bold")
FONT_MONO  = ("Consolas", 9)
FONT_SMALL = ("Segoe UI", 8)

MAX_LOG_HISTORY = 4000   # lineas maximas mostradas en consola


# ---------------------------------------------------------------------------
# Utilidades basicas
# ---------------------------------------------------------------------------
def app_dir():
    """Carpeta donde vive esta aplicacion (no depende del cwd)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def timestamp():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def stamp_compact():
    return time.strftime("%Y%m%d_%H%M%S")


def fmt_size(n):
    if n is None:
        return "?"
    mb = n / (1024.0 * 1024.0)
    if mb >= 1.0:
        return "%.1f MB" % mb
    return "%.0f KB" % (n / 1024.0)


def open_path(path):
    """Abre una carpeta o archivo con el programa predeterminado del sistema."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception:
        return False


def valid_rom_header(path):
    """Verifica que la ROM sea un FireRed US (codigo interno 'BPRE' @ 0xAC)
    y lee la revision del byte de version (0xBC: 0x00 = FireRed 1.0, la
    requerida por el CFRU; 0x01 = rev 1.1, NO soportada)."""
    try:
        if not os.path.isfile(path):
            return (False, None, None, "La ROM no existe")
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            f.seek(0xAC)
            code = f.read(4)
            f.seek(0xBC)
            ver = f.read(1)
        code = code.decode("ascii", "replace").strip()
        ok = (code == "BPRE")
        rev = ver[0] if ver else None
        if ok:
            if rev == 0:
                msg = "ROM FireRed US 1.0 válida (BPRE, rev 0) — la requerida por el CFRU"
            else:
                msg = ("ROM FireRed válida (BPRE) PERO parece revision %s. "
                       "El CFRU requiere FireRed US 1.0 (rev 0, byte 0xBC=00). "
                       "Una rev distinta puede colgar el juego en cualquier "
                       "momento." % (rev,))
        else:
            msg = "La ROM no es FireRed US (codigo '%s')" % code
        return (ok, code, size, msg)
    except Exception as e:
        return (False, None, None, "No se pudo leer la ROM: %s" % e)


def clean_path(p):
    """Limpia rutas pegadas con comillas ("Copiar como ruta" de Windows)
    o con separadores sobrantes al final."""
    if not p:
        return p
    p = str(p).strip().strip('"').strip("'").strip()
    while len(p) > 1 and p[-1] in "\\/" and not (len(p) == 3 and p[1] == ":"):
        p = p[:-1]
    return p


def find_devkitarm(extra_roots=None):
    r"""Detecta devkitARM por 4 vias, de mas directa a mas desesperada:
      1) compilador arm-none-eabi-* en el PATH del proceso
      2) variables de entorno DEVKITARM / DEVKITPRO
      3) registro de Windows (HKLM/HKCU): capta instalaciones hechas DESPUES
         de que arrancara esta sesion (PATH sin refrescar en el proceso)
      4) rutas tipicas del disco (C:\devkitPro\devkitARM\bin, etc.)
    Devuelve (metodo, carpeta_bin) o (None, None)."""
    def bin_ok(d):
        try:
            for n in ("arm-none-eabi-gcc", "arm-none-eabi-as"):
                names = [n, n + ".exe"] if os.name == "nt" else [n]
                for cand in names:
                    if os.path.isfile(os.path.join(d, cand)):
                        return True
        except Exception:
            pass
        return False

    # 1) PATH del proceso
    for tool in ("arm-none-eabi-gcc", "arm-none-eabi-as"):
        w = shutil.which(tool)
        if w:
            return ("PATH", os.path.dirname(w))

    # 2) variables de entorno
    v = clean_path(os.environ.get("DEVKITARM") or "")
    if v:
        for c in (os.path.join(v, "bin"), v):
            if bin_ok(c):
                return ("variables de entorno", c)
    v = clean_path(os.environ.get("DEVKITPRO") or "")
    if v:
        for c in (os.path.join(v, "devkitARM", "bin"), os.path.join(v, "devkitARM")):
            if bin_ok(c):
                return ("variables de entorno", c)

    # 3) registro de Windows (instalaciones recientes que el proceso todavia no ve)
    if os.name == "nt":
        try:
            import winreg
            for hive, sub in ((winreg.HKEY_LOCAL_MACHINE,
                               r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                              (winreg.HKEY_CURRENT_USER, "Environment")):
                try:
                    with winreg.OpenKey(hive, sub) as k:
                        for val in ("DEVKITARM", "DEVKITPRO", "Path", "PATH"):
                            try:
                                data, _t = winreg.QueryValueEx(k, val)
                            except OSError:
                                continue
                            for part in str(data).split(";"):
                                part = clean_path(part.strip())
                                if not part or "devkitarm" not in part.lower().replace("\\", "/"):
                                    continue
                                if bin_ok(part):
                                    return ("registro de Windows", part)
                                if bin_ok(os.path.join(part, "bin")):
                                    return ("registro de Windows", os.path.join(part, "bin"))
                except Exception:
                    continue
        except Exception:
            pass

    # 4) rutas tipicas del disco
    roots = ["C:\\devkitPro", "C:\\devkitpro",
             "C:\\Program Files\\devkitPro", "C:\\Program Files (x86)\\devkitPro",
             os.path.join(os.path.expanduser("~"), "devkitPro"),
             "D:\\devkitPro", "E:\\devkitPro"]
    if extra_roots:
        roots = list(extra_roots) + roots
    for r in roots:
        for c in (os.path.join(r, "devkitARM", "bin"), os.path.join(r, "devkitARM")):
            if bin_ok(c):
                return ("disco", c)
    return (None, None)


def devkit_build_env():
    """Entorno para los make.py con devkitARM GARANTIZADO: si devkitARM se
    detecto por registro o disco pero el PATH del proceso esta desactualizado
    (tipico tras instalar devkitPro sin reiniciar sesion), se inyecta la
    carpeta bin y las variables DEVKITPRO/DEVKITARM solo para la compilacion.
    No modifica nada de tu sistema. Devuelve (env, (metodo, bin))."""
    env = os.environ.copy()
    m, bin_dir = find_devkitarm()
    if bin_dir:
        key = "PATH" if "PATH" in env else "Path"
        cur = env.get(key) or ""
        if bin_dir.lower().rstrip("\\/") not in cur.lower().replace("/", "\\"):
            env[key] = bin_dir + os.pathsep + cur
        base = os.path.dirname(bin_dir.rstrip("\\/"))      # ...\\devkitARM
        pro = os.path.dirname(base)                          # ...\\devkitPro
        if not env.get("DEVKITARM") and os.path.isdir(base):
            env["DEVKITARM"] = base
        if not env.get("DEVKITPRO") and os.path.isdir(pro) and not os.path.basename(pro).lower().startswith("bin"):
            env["DEVKITPRO"] = pro
    return env, (m, bin_dir)


def normalize_hex(text, default=None):
    """Convierte '0x900000' / '900000' / 9437184 a entero (hex por defecto)."""
    if text is None:
        return default
    s = str(text).strip().lower().replace(" ", "")
    if not s:
        return default
    try:
        if s.startswith("0x"):
            return int(s, 16)
        # Por convencion GBA, un numero 'plano' se interpreta como hexadecimal
        return int(s, 16)
    except ValueError:
        return default


def default_python_for_build():
    """Python recomendado para ejecutar make.py (evita pythonw si es posible)."""
    exe = sys.executable or "python"
    base = os.path.basename(exe).lower()
    if base.startswith("pythonw"):
        exe = os.path.join(os.path.dirname(exe), "python.exe")
    return exe


# ---------------------------------------------------------------------------
# Python REAL vs alias FALSO de la Microsoft Store (v1.0.3)
# ---------------------------------------------------------------------------
# El mensaje "no se encontro Python; ejecutar sin argumentos para instalar
# desde el Microsoft Store..." NO lo imprime ningun Python real: lo imprime
# el ejecutable FALSO C:\Users\X\AppData\Local\Microsoft\WindowsApps\
# python.exe (el "alias de ejecucion de aplicaciones" de Windows). Si
# make.py o cualquiera de sus subprocesos llama a "python" y el PATH
# resuelve a ese alias, la compilacion muere con codigo 1 sin razon
# aparente, aunque tu Python este perfectamente instalado.
STORE_STUB_LINE_MARKERS = (
    "no se encontr",            # es: "no se encontro/encontro Python" (aguanta mojibake)
    "python was not found",     # mensaje del alias en ingles
    "microsoft store",
    "ejecutar sin argumentos",
    "alias de ejecucion",
)


def is_store_stub_path(path):
    """True si esa ruta apunta al python.exe FALSO de la Microsoft Store."""
    try:
        p = str(path).lower().replace("/", "\\")
    except Exception:
        return False
    return "\\microsoft\\windowsapps\\" in (p + "\\")


def is_store_stub_output(text):
    """True si una linea de salida parece el mensaje del alias falso de la
    Tienda (espanol o ingles, incluso con tildes convertidas a mojibake)."""
    t = str(text).lower()
    return any(m in t for m in STORE_STUB_LINE_MARKERS)


_PY_PROBE_CACHE = {}


def probe_python(exe, timeout=12):
    """Comprueba que exe sea un Python REAL que arranca y responde con su
    version. Devuelve (ok, version_o_error). El resultado se cachea 30 s
    para no lanzar sondas nuevas en cada refresco de la GUI."""
    key = os.path.abspath(str(exe)) if exe else ""
    hit = _PY_PROBE_CACHE.get(key)
    now = time.time()
    if hit and (now - hit[0]) < 30:
        return hit[1], hit[2]
    ok, ver = False, ""
    try:
        kw = {}
        if os.name == "nt":
            kw["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        p = subprocess.run([exe, "-c", "import sys; print(sys.version.split()[0])"],
                           capture_output=True, timeout=timeout, **kw)
        out = (p.stdout or b"").decode("utf-8", "replace").strip()
        err = (p.stderr or b"").decode("utf-8", "replace").strip()
        if p.returncode == 0 and re.match(r"^\d+\.\d+\.\d+", out):
            ok, ver = True, out.split()[0]
        else:
            ver = (out + " " + err).strip()[:160] or ("codigo de salida %s" % p.returncode)
    except Exception as e:
        ver = "%s: %s" % (type(e).__name__, e)
    _PY_PROBE_CACHE[key] = (now, ok, ver)
    return ok, ver


def build_env_for_make(python_exe):
    """Entorno DEFINITIVO de los make.py (v1.0.3). Parte de devkit_build_env()
    (devkitARM garantizado) y ademas:
      * pone la carpeta del python ELEGIDO al frente del PATH: cualquier
        'python' interno de make.py usara el python REAL, no el alias falso;
      * quita la carpeta Microsoft\\WindowsApps del PATH SOLO durante esta
        compilacion (ahi viven los python.exe/python3.exe falsos de la Tienda);
      * define PYTHONIOENCODING=utf-8 para decodificar bien la salida.
    No toca nada del sistema. Devuelve (env, info_devkit, alias_quitados)."""
    env, dk = devkit_build_env()
    try:
        py_dir = os.path.dirname(os.path.abspath(str(python_exe)))
    except Exception:
        py_dir = ""
    key = "PATH" if "PATH" in env else "Path"
    raw = env.get(key) or ""
    parts = [p.strip() for p in raw.split(os.pathsep) if p.strip()]

    def _n(p):
        return p.replace("/", "\\").rstrip("\\").lower()

    alias_quitados = 0
    kept = []
    for p in parts:
        if "\\microsoft\\windowsapps" in _n(p):
            alias_quitados += 1
            continue
        kept.append(p)
    parts = kept
    if py_dir:
        parts = [py_dir] + [p for p in parts if _n(p) != _n(py_dir)]
    env[key] = os.pathsep.join(parts)
    env["PYTHONIOENCODING"] = "utf-8"
    return env, dk, alias_quitados


# ---------------------------------------------------------------------------
# ConfigStore: configuracion persistente (config.json)
# ---------------------------------------------------------------------------
class ConfigStore(object):
    DEFAULTS = {
        "rom_path": "",
        "dpe_dir": "",
        "cfru_dir": "",
        "offset_dpe": "0x750000",
        "offset_cfru": "0x900000",
        "out_dir": "",
        "out_name": "MiHack_CFRU",
        "python_for_build": "",          # vacio = default_python_for_build()
        "auto_apply_offsets": True,
        "backup_enabled": True,
        "clean_before_update": False,
        "shelly_activar": True,   # v1.1.0: módulo Shelly (inicial al arrancar)
        "higiene_sav": True,   # v1.2.2: renombrar .sav/.sgm viejos de la ROM final
        "geometry": "",
    }

    def __init__(self, path=None):
        self.path = path or os.path.join(app_dir(), "config.json")
        self.data = dict(self.DEFAULTS)
        self.load()

    def load(self):
        try:
            if os.path.isfile(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                for k in self.DEFAULTS:
                    if k in saved:
                        self.data[k] = saved[k]
        except Exception:
            pass
        return self.data

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            return True
        except Exception:
            return False

    def get(self, key):
        val = self.data.get(key, self.DEFAULTS.get(key))
        if key == "python_for_build" and not val:
            val = default_python_for_build()
        return val

    def set(self, key, value):
        self.data[key] = value
        return self.save()


# ---------------------------------------------------------------------------
# RepoInspector: inspeccion de las carpetas DPE / CFRU
# ---------------------------------------------------------------------------
RE_OFFSET = re.compile(r"(OFFSET_TO_PUT\s*=\s*)(0x[0-9A-Fa-f]+|\d+)")

class RepoInfo(object):
    """Resultado de la inspeccion de un repositorio."""

    def __init__(self, path=""):
        self.path = path
        self.exists = False
        self.has_make = False
        self.make_path = ""
        self.has_data_extractor = False
        self.has_clean = False
        self.kind = "desconocido"          # 'dpe' | 'cfru' | 'desconocido'
        self.variant = "desconocida"        # 'shiny' | 'skeli' | 'desconocida'
        self.variant_label = ""
        self.current_offset = None
        self.error = ""

    @property
    def label(self):
        if not self.exists:
            return "sin carpeta"
        if not self.has_make:
            return "no parece un repo (falta scripts/make.py)"
        base = {"dpe": "DPE", "cfru": "CFRU", "desconocido": "repo"}.get(self.kind, "repo")
        return "%s (%s)" % (base, self.variant_label or self.variant)


class RepoInspector(object):

    @staticmethod
    def inspect(path):
        info = RepoInfo(path or "")
        if not path:
            info.error = "Carpeta no seleccionada"
            return info
        if not os.path.isdir(path):
            info.error = "La carpeta no existe"
            return info
        info.exists = True

        make_path = os.path.join(path, "scripts", "make.py")
        if os.path.isfile(make_path):
            info.has_make = True
            info.make_path = make_path
            info.current_offset = RepoInspector.read_offset(make_path)

        info.has_data_extractor = os.path.isfile(
            os.path.join(path, "scripts", "data_extractor.py"))
        info.has_clean = os.path.isfile(
            os.path.join(path, "scripts", "clean.py"))

        # Variante del repo: fork de Shiny-Miner / Tha Code Mining hub vs original
        info.variant, info.variant_label = RepoInspector._variant(path)

        # Tipo de repo: DPE trae data_extractor.py; el CFRU no.
        if info.has_make and info.has_data_extractor:
            info.kind = "dpe"
        elif info.has_make:
            info.kind = "cfru"

        if not info.has_make:
            info.error = "No se encontro scripts/make.py dentro de la carpeta"
        return info

    @staticmethod
    def _variant(path):
        readme = os.path.join(path, "README.md")
        blob = ""
        try:
            if os.path.isfile(readme):
                with open(readme, "r", encoding="utf-8", errors="replace") as f:
                    blob = f.read(4000)
        except Exception:
            blob = ""
        low = blob.lower()
        if any(t in low for t in ("shiny", "tha code mining", "expansion")):
            return ("shiny", "fork Shiny-Miner/TCMH")
        if "complete firered upgrade" in low or "skeli" in low or "dynamic pokemon expansion" in low:
            return ("skeli", "original Skeli789")
        # clean.py solo existe en el fork -> pista secundaria
        if os.path.isfile(os.path.join(path, "scripts", "clean.py")):
            return ("shiny", "fork (con clean.py)")
        return ("desconocida", "variante no identificada")

    @staticmethod
    def read_offset(make_path):
        try:
            with open(make_path, "r", encoding="utf-8", errors="replace") as f:
                m = RE_OFFSET.search(f.read())
            if m:
                s = m.group(2).lower()
                return int(s, 16) if s.startswith("0x") else int(s)
        except Exception:
            pass
        return None

    @staticmethod
    def write_offset(make_path, value):
        """Escribe OFFSET_TO_PUT en scripts/make.py. Devuelve (ok, msg)."""
        if not os.path.isfile(make_path):
            return (False, "No existe %s" % make_path)
        try:
            with open(make_path, "r", encoding="utf-8", errors="replace") as f:
                src = f.read()
            if RE_OFFSET.search(src):
                src2 = RE_OFFSET.sub(lambda m: m.group(1) + "0x%X" % value, src, count=1)
            else:
                return (False, "No se encontro 'OFFSET_TO_PUT' dentro de make.py")
            with open(make_path, "w", encoding="utf-8", newline="") as f:
                f.write(src2)
            return (True, "OFFSET_TO_PUT actualizado a 0x%X" % value)
        except Exception as e:
            return (False, "Error escribiendo offset: %s" % e)


# ---------------------------------------------------------------------------
# Historial de compilaciones (history.json + logs/*.log)
# ---------------------------------------------------------------------------
class History(object):
    def __init__(self, base_dir=None):
        self.base = base_dir or app_dir()
        self.logs_dir = os.path.join(self.base, "logs")
        self.json_path = os.path.join(self.base, "history.json")
        try:
            os.makedirs(self.logs_dir, exist_ok=True)
        except Exception:
            pass

    def entries(self):
        try:
            if os.path.isfile(self.json_path):
                with open(self.json_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def add(self, entry):
        lst = self.entries()
        lst.insert(0, entry)
        lst = lst[:200]
        try:
            with open(self.json_path, "w", encoding="utf-8") as f:
                json.dump(lst, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
        return entry

    def new_log_file(self, mode):
        fname = "build_%s_%s.log" % (stamp_compact(), mode)
        return os.path.join(self.logs_dir, fname)

    def clear(self):
        try:
            with open(self.json_path, "w", encoding="utf-8") as f:
                json.dump([], f)
            return True
        except Exception:
            return False


# ---------------------------------------------------------------------------
# BuildEngine: ejecuta las compilaciones en segundo plano y emite eventos
# ---------------------------------------------------------------------------
def classify_line(line):
    """Clasifica una linea de salida para darle color en la consola."""
    low = line.lower()
    if any(t in low for t in ("[error]", "error", "traceback", "exception",
                              "failed", "fatal", "no such file", "cannot find",
                              "no se encontro", "fallido", "fallo")):
        return "err"
    if any(t in low for t in ("[warn]", "warning", "warn ", "aviso",
                              "advertencia", "note:")):
        return "warn"
    if any(t in low for t in ("[ok]", "success", "successfully", " done",
                              "complete", "built", "finished", "finalizo",
                              "listo", "guardada", "copiada")):
        return "ok"
    return ""


class BuildEngine(object):
    """
    Motor de compilacion. Corre en un hilo aparte y comunica la GUI mediante
    una cola de eventos (dicts):
      {"t":"log",     "line":str, "level":""}
      {"t":"step",    "i":int, "state":"pending|current|done|fail|pause"}
      {"t":"state",   "state":"idle|running|paused|done|error|cancelled", "msg":str}
      {"t":"finished","success":bool, "mode":str, "summary":str, "rom_out":str}
    """

    STATE_IDLE = "idle"
    STATE_RUNNING = "running"
    STATE_PAUSED = "paused"
    STATE_DONE = "done"
    STATE_ERROR = "error"
    STATE_CANCELLED = "cancelled"

    CHAIN_STEPS = [
        "Respaldar ROM original",
        "Preparar carpetas y aplicar offsets",
        "Copiar ROM -> DPE (BPRE0.gba)",
        "Compilar DPE (make.py)",
        "PAUSA: revisa el resultado y pulsa 'Continuar'",
        "Copiar DPE/test.gba -> CFRU (BPRE0.gba)",
        "Compilar CFRU (make.py)",
        "Guardar ROM final",
        "Registrar en historial",
    ]

    def __init__(self, evq, cfg, history, base_dir=None):
        self.q = evq
        self.cfg = cfg
        self.history = history
        self.base_dir = base_dir or app_dir()
        self.state = self.STATE_IDLE
        self._thread = None
        self._cancel = False
        self._pause_evt = threading.Event()
        self._proc = None
        self._proc_lock = threading.Lock()
        self._log_fh = None

    # ---------------- infraestructura de eventos ----------------
    def _emit(self, ev):
        try:
            self.q.put_nowait(ev)
        except Exception:
            pass

    def _log(self, line, level=""):
        ev = {"t": "log", "line": line.rstrip("\r\n"), "level": level or classify_line(line)}
        self._emit(ev)
        if self._log_fh:
            try:
                self._log_fh.write(ev["line"] + "\n")
                self._log_fh.flush()
            except Exception:
                pass

    def _info(self, msg):
        self._log("[INFO] " + msg, "info")

    def _ok(self, msg):
        self._log("[OK] " + msg, "ok")

    def _warn(self, msg):
        self._log("[WARN] " + msg, "warn")

    def _err(self, msg):
        self._log("[ERROR] " + msg, "err")

    def _step(self, i, st):
        self._emit({"t": "step", "i": i, "state": st})

    def _set_state(self, st, msg=""):
        self.state = st
        self._emit({"t": "state", "state": st, "msg": msg})

    def _steps_all(self, st):
        for i in range(len(self.CHAIN_STEPS)):
            self._step(i, st)

    # ---------------- API publica ----------------
    @property
    def busy(self):
        return self.state in (self.STATE_RUNNING, self.STATE_PAUSED)

    def full_chain(self):
        """Compilacion completa: DPE primero, pausa, luego CFRU."""
        return self._launch("cadena", self._do_chain)

    def update_dpe(self):
        """Modo actualizacion: reinstalar solo el DPE."""
        return self._launch("actualizar-dpe", self._do_update_dpe)

    def update_cfru(self):
        """Modo actualizacion: reinstalar solo el CFRU."""
        return self._launch("actualizar-cfru", self._do_update_cfru)

    def continue_after_pause(self):
        if self.state == self.STATE_PAUSED:
            self._pause_evt.set()
            self._info("Continuando hacia el CFRU...")
            return True
        return False

    def cancel(self):
        if not self.busy:
            return False
        self._cancel = True
        self._pause_evt.set()
        with self._proc_lock:
            proc = self._proc
        if proc and proc.poll() is None:
            try:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                                   capture_output=True)
                else:
                    proc.terminate()
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        return True

    # ---------------- validaciones previas ----------------
    def _validate_common(self, need_dpe=True, need_cfru=True):
        rom = clean_path(self.cfg.get("rom_path"))
        dpe = clean_path(self.cfg.get("dpe_dir"))
        cfru = clean_path(self.cfg.get("cfru_dir"))
        # normaliza separadores mezclados (rutas pegadas con '/') para que
        # los logs y las rutas hijas salgan limpias en Windows
        rom = os.path.normpath(rom) if rom else rom
        dpe = os.path.normpath(dpe) if dpe else dpe
        cfru = os.path.normpath(cfru) if cfru else cfru
        problems = []

        if need_dpe:
            di = RepoInspector.inspect(dpe)
            if not di.has_make:
                problems.append("La carpeta del DPE no es valida: %s" % (di.error or "falta scripts/make.py"))
        if need_cfru:
            ci = RepoInspector.inspect(cfru)
            if not ci.has_make:
                problems.append("La carpeta del CFRU no es valida: %s" % (ci.error or "falta scripts/make.py"))

        return problems, rom, dpe, cfru

    def _validate_chain(self):
        problems, rom, dpe, cfru = self._validate_common(True, True)
        if not rom or not os.path.isfile(rom):
            problems.append("Selecciona primero una ROM FireRed (BPRE) en el panel izquierdo.")
        else:
            ok, code, size, msg = valid_rom_header(rom)
            if not ok:
                self._warn("Advertencia de ROM: %s (puedes continuar bajo tu propio riesgo)." % msg)
        # offsets distintos
        o1 = normalize_hex(self.cfg.get("offset_dpe"))
        o2 = normalize_hex(self.cfg.get("offset_cfru"))
        if (o1 is not None and o2 is not None) and o1 == o2:
            problems.append("El offset del DPE y del CFRU son IGUALES (0x%X). "
                            "Deben ser distintos para no pisarse." % o1)
        return problems, rom, dpe, cfru

    # ---------------- hilo principal ----------------
    def _launch(self, mode, fn):
        if self.busy:
            self._err("Ya hay una compilacion en curso.")
            return False
        self._cancel = False
        self._pause_evt.clear()
        self._mode = mode
        log_path = self.history.new_log_file(mode)
        try:
            os.makedirs(os.path.dirname(log_path), exist_ok=True)
            self._log_fh = open(log_path, "w", encoding="utf-8")
        except Exception:
            self._log_fh = None
        self._log("=== CFRU Builder %s | modo: %s | %s ===" %
                  (APP_VERSION, mode, timestamp()), "sys")
        self._thread = threading.Thread(target=self._run, args=(fn, mode, log_path),
                                        daemon=True)
        self._thread.start()
        return True

    def _run(self, fn, mode, log_path):
        t0 = time.time()
        success = False
        rom_out = ""
        summary = ""
        try:
            self._set_state(self.STATE_RUNNING, "Compilando (%s)..." % mode)
            success, rom_out, summary = fn()
        except _CancelError as e:
            self._warn("Operacion CANCELADA por el usuario. %s" % e)
            self._set_state(self.STATE_CANCELLED, "Cancelada")
            self._finish(mode, log_path, t0, False, rom_out, "Cancelada por el usuario")
            return
        except Exception as e:
            self._err("Excepcion inesperada: %r" % e)
            summary = summary or ("Error inesperado: %r" % e)
            self._set_state(self.STATE_ERROR, "Error")
            self._finish(mode, log_path, t0, False, rom_out, summary)
            return
        if self._cancel:
            self._set_state(self.STATE_CANCELLED, "Cancelada")
            self._finish(mode, log_path, t0, False, rom_out, "Cancelada por el usuario")
            return
        self._set_state(self.STATE_DONE if success else self.STATE_ERROR,
                       "Completada" if success else "Con errores")
        self._finish(mode, log_path, t0, success, rom_out, summary)

    def _finish(self, mode, log_path, t0, success, rom_out, summary):
        dur = time.time() - t0
        entry = {
            "ts": timestamp(),
            "mode": mode,
            "duration_s": round(dur, 1),
            "success": bool(success),
            "summary": summary or "",
            "rom_out": rom_out or "",
            "log": os.path.basename(log_path) if log_path else "",
        }
        try:
            self.history.add(entry)
        except Exception:
            pass
        if self._log_fh:
            try:
                self._log_fh.close()
            except Exception:
                pass
            self._log_fh = None
        self._emit({"t": "finished", "success": bool(success), "mode": mode,
                    "summary": summary or "", "rom_out": rom_out or ""})

    def _check_cancel(self):
        if self._cancel:
            raise _CancelError("")

    # ---------------- copia robusta de archivos (v1.0.1) ----------------
    def _long_path(self, p):
        """En Windows, rutas de mas de ~240 caracteres fallan con
        FileNotFoundError a menos que se use el prefijo de ruta extendida."""
        if os.name == "nt" and p and not p.startswith("\\\\?\\"):
            try:
                ap = os.path.abspath(p)
            except Exception:
                return p
            if len(ap) > 240:
                return "\\\\?\\" + ap
        return p

    def _same_file(self, a, b):
        """True si a y b son exactamente el mismo archivo del disco."""
        if not a or not b:
            return False
        try:
            if os.path.exists(a) and os.path.exists(b):
                try:
                    return os.path.samefile(a, b)
                except (OSError, ValueError):
                    pass
        except OSError:
            pass
        try:
            return os.path.realpath(os.path.abspath(a)) == os.path.realpath(os.path.abspath(b))
        except Exception:
            try:
                return os.path.abspath(a) == os.path.abspath(b)
            except Exception:
                return False

    def _make_writable(self, path):
        """Quita el atributo de solo-lectura (Windows) o garantiza permiso
        de escritura (POSIX). Devuelve True si no hizo falta o tuvo exito."""
        if not path or not os.path.exists(path):
            return True
        for p in (self._long_path(path), path):
            try:
                if os.name == "nt":
                    os.chmod(p, stat.S_IREAD | stat.S_IWRITE)
                else:
                    os.chmod(p, os.stat(p).st_mode | stat.S_IWUSR)
                return True
            except Exception:
                continue
        return False

    def _copy_chunked(self, src, dst):
        """Copia manual por bloques de 1 MB (sin copystat: no propaga el
        atributo de solo-lectura del origen). Devuelve None si fue bien
        o la excepcion si fallo."""
        src_p, dst_p = self._long_path(src), self._long_path(dst)
        try:
            with open(src_p, "rb") as fsrc, open(dst_p, "wb") as fdst:
                while True:
                    buf = fsrc.read(1024 * 1024)
                    if not buf:
                        break
                    fdst.write(buf)
            try:
                st = os.stat(src_p)
                os.utime(dst_p, (st.st_atime, st.st_mtime))
            except Exception:
                pass
            return None
        except Exception as e:
            return e

    def _copy_via_temp(self, src, dst):
        """Copia a un temporal del mismo directorio y sustituye el destino
        al final: si la copia falla a medias, el destino anterior queda
        intacto (no se corrompe nada)."""
        dst_dir = os.path.dirname(dst) or "."
        tmp = os.path.join(dst_dir, ".cfru_tmp_%d.gba" % (int(time.time() * 1000) % 10 ** 9))
        err = self._copy_chunked(src, tmp)
        if err is not None:
            try:
                os.remove(self._long_path(tmp))
            except Exception:
                pass
            return err
        try:
            if os.path.exists(dst):
                self._make_writable(dst)
            os.replace(self._long_path(tmp), self._long_path(dst))
            return None
        except Exception as e:
            err2 = self._copy_chunked(src, dst)
            try:
                os.remove(self._long_path(tmp))
            except Exception:
                pass
            return err2 if err2 is not None else e

    def _is_lock_error(self, e):
        """True si la excepcion es un bloqueo de archivo (en uso por otro
        proceso / permiso denegado): esos fallos suelen soltarse solos tras
        unos segundos, asi que merece la pena reintentarlos mas veces."""
        winerr = getattr(e, "winerror", None)
        if winerr in (32, 33):               # en uso por otro proceso / sharing violation
            return True
        if isinstance(e, PermissionError):
            return True
        en = getattr(e, "errno", None)
        return en in (errno.EACCES, errno.EPERM)

    def _diagnose_copy_error(self, e, src, dst):
        """Traduce la excepcion de copia a causas y consejos concretos."""
        en = getattr(e, "errno", None)
        winerr = getattr(e, "winerror", None)
        lines = []
        if isinstance(e, shutil.SameFileError):
            lines.append("El origen y el destino ya son el mismo archivo; no hace falta copiar.")
        elif winerr == 32:
            lines.append("Windows dice que OTRO PROGRAMA esta usando el archivo en este")
            lines.append("momento (WinError 32). Casi siempre es uno de estos:")
            lines.append("  - Un emulador (mGBA/VBA/NO$GBA) tiene abierta esa ROM o ese test.gba:")
            lines.append("    cierralo del todo y vuelve a pulsar INICIAR.")
            lines.append("  - OneDrive/Google Drive esta sincronizando la carpeta: pausalo o")
            lines.append("    mueve los repos a una ruta local (ej.: C:\\RomHacking\\DPE).")
            lines.append("  - El antivirus esta examinando el .gba recien escrito: se suele")
            lines.append("    soltar solo en segundos (la app ya reintento 5 veces con esperas).")
            lines.append("  - Un editor hexadecimal o la vista previa del Explorer: cierralos.")
            lines.append("  Si en la carpeta de destino ya dejaste la ROM colocada a mano, la")
            lines.append("  app seguira con ella aunque esta copia no se pueda hacer.")
        elif isinstance(e, PermissionError) or en in (errno.EACCES, errno.EPERM) or winerr in (5, 19):
            lines.append("Motivo probable: el archivo o la carpeta esta BLOQUEADA o sin permisos de escritura.")
            lines.append("  - Cierra el emulador, el editor hexadecimal, el explorer o cualquier")
            lines.append("    programa que tenga abiertos el archivo o la carpeta de destino.")
            lines.append("  - Si la carpeta esta en OneDrive/Google Drive, pausa la sincronizacion")
            lines.append("    o mueve los repos a una ruta local (ej.: C:\\RomHacking\\DPE).")
            lines.append("  - Ejecuta CFRU Builder como administrador (clic derecho > Ejecutar como")
            lines.append("    administrador) o revisa los permisos de la carpeta del repo.")
            lines.append("  - Algunos antivirus bloquean la creacion/escritura de archivos .gba;")
            lines.append("    agrega una exclusion temporal para la carpeta de los repos.")
        elif isinstance(e, FileNotFoundError) or en == errno.ENOENT:
            lines.append("Motivo probable: la ruta es demasiado larga para Windows (limite de 260")
            lines.append("caracteres) o la carpeta de destino desaparecio/cambio de nombre.")
            lines.append("  - Mueve ROM y repos a rutas cortas, ej.: C:\\RomHacking\\MiHack.gba,")
            lines.append("    C:\\RomHacking\\DPE y C:\\RomHacking\\CFRU, y vuelve a elegirlas en la app.")
        elif en == errno.ENOSPC:
            lines.append("Motivo probable: no queda espacio libre en el disco.")
            lines.append("  - Libera espacio: la ROM con DPE+CFRU puede pasar de 32 MB y los")
            lines.append("    respaldos tambien ocupan espacio.")
        else:
            lines.append("Detalle tecnico del error: %s: %s" % (type(e).__name__, e))
        lines.append("Origen:   %s" % src)
        lines.append("Destino:  %s" % dst)
        return lines

    def _copy_file_robust(self, src, dst, quiet=False):
        """Copia robusta de src -> dst pensada para ROMs en Windows.

        Soporta: origen y destino ya son el mismo archivo (tipico cuando tu
        ROM ya es el BPRE0.gba del DPE), destino previo en solo-lectura,
        bloqueos transitorios (OneDrive/antivirus/emulador) con 3 reintentos,
        rutas largas (prefijo \\\\?\\), espacio de disco insuficiente y
        carpetas sin permisos de escritura, con diagnostico claro en espanol.

        Devuelve (ok, mensaje):
          - copia nueva correcta ........ (True, "")
          - ya estaba en el destino ..... (True, "ya estaba en su sitio")
          - fallo ....................... (False, mensaje del problema)
        """
        def say(msg):
            if not quiet:
                self._err(msg)

        if not src:
            say("Copia: no hay archivo de origen indicado.")
            return (False, "no hay archivo de origen")
        src = os.path.abspath(src)
        dst = os.path.abspath(dst)
        if not os.path.isfile(src):
            say("Copia: el archivo de origen no existe:\n  %s" % src)
            return (False, "el archivo de origen no existe: %s" % src)
        dst_dir = os.path.dirname(dst)
        if dst_dir and not os.path.isdir(dst_dir):
            say("Copia: la carpeta de destino no existe:\n  %s" % dst_dir)
            return (False, "la carpeta de destino no existe: %s" % dst_dir)

        # 1) origen y destino ya son el mismo archivo: no hace falta copiar
        if self._same_file(src, dst):
            self._make_writable(dst)
            self._info("El archivo de origen ya estaba en el sitio de destino (%s);" % dst)
            self._info("no hace falta copiar nada. Continuando...")
            return (True, "ya estaba en su sitio")

        size = os.path.getsize(src)

        # 2) espacio libre en el disco del destino
        try:
            free = shutil.disk_usage(dst_dir).free
            if free < size + 2 * 1024 * 1024:
                say("Copia: no hay espacio libre suficiente en el disco.\n"
                    "  Carpeta destino: %s\n  Libre: %s | Necesario: %s" %
                    (dst_dir, fmt_size(free), fmt_size(size + 2 * 1024 * 1024)))
                return (False, "sin espacio en disco (libre %s)" % fmt_size(free))
        except Exception:
            pass

        # 3) la carpeta de destino permite escribir?
        probe = os.path.join(dst_dir, ".cfru_probe_%d.tmp" % int(time.time() * 1000))
        try:
            with open(self._long_path(probe), "wb") as f:
                f.write(b"")
        except Exception as e:
            say("Copia: la carpeta de destino NO permite escribir en ella (%s).\n"
                "  Carpeta: %s\n"
                "  - Verifica que no este protegida (ej. dentro de Program Files).\n"
                "  - Ejecuta la app como administrador o elige otra carpeta." % (e, dst_dir))
            return (False, "la carpeta de destino no permite escribir (%s)" % e)
        finally:
            try:
                os.remove(self._long_path(probe))
            except Exception:
                pass

        # 4) copia con reintentos (bloqueos transitorios de OneDrive/antivirus)
        want = os.path.getsize(src)
        last_exc = None

        def _size_ok():
            try:
                return os.path.getsize(dst) == want
            except Exception:
                return False

        attempt, max_attempts = 0, 3
        while attempt < max_attempts:
            attempt += 1
            err = self._copy_via_temp(src, dst)
            if err is None and not _size_ok():
                err = OSError("la copia quedo con un tamano distinto al original")
            if err is None:
                # el destino nunca debe quedar en solo-lectura (vital para las
                # siguientes compilaciones y para clean.py de los repos)
                self._make_writable(dst)
                return (True, "")
            last_exc = err
            if self._is_lock_error(err):
                # WinError 32 (en uso por otro proceso) suele soltarse solo:
                # mas intentos y esperas crecientes (emulador/OneDrive/antivirus)
                max_attempts = max(max_attempts, 5)
                wait = (0.5, 1.5, 3.0, 5.0)[min(attempt - 1, 3)]
            else:
                wait = 0.7
            if attempt < max_attempts:
                self._warn("Intento de copia %d de %d fallo (%s). Reintentando en %.1f s..." %
                           (attempt, max_attempts, err, wait))
                time.sleep(wait)

        # 4b) ultimo recurso en Windows: el copiador nativo (pasa cuando el
        # antivirus o la proteccion de carpetas bloquea la escritura de Python)
        if os.name == "nt":
            try:
                self._info("Probando con el copiador nativo de Windows (cmd copy /y)...")
                rc = subprocess.call(["cmd", "/c", "copy", "/y", src, dst],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     timeout=90)
                if rc == 0 and _size_ok():
                    self._make_writable(dst)
                    return (True, "")
                last_exc = last_exc or OSError("cmd copy devolvio codigo %s" % rc)
            except Exception as e:
                last_exc = last_exc or e

        # 5) fallo definitivo: diagnostico claro en espanol
        say("Fallo definitivo al copiar el archivo. Detalle:")
        for line in self._diagnose_copy_error(last_exc, src, dst):
            say(line)
        return (False, "fallo la copia: %s" % last_exc)

    def _copy_rom_rescued(self, src, dst, label):
        """Copia con plan de RESCATE (v1.0.2): si la copia automatica falla
        pero el destino ya tiene una ROM colocada a mano (como dice la guia
        oficial), se continua con esa avisando claramente. Devuelve
        (ok, msg, modo): modo = 'copiado' | 'ya-estaba' | 'existente' | 'fallo'."""
        ok, msg = self._copy_file_robust(src, dst)
        if ok:
            return (True, msg, ("ya-estaba" if msg else "copiado"))
        if os.path.isfile(dst):
            try:
                size = fmt_size(os.path.getsize(dst))
            except Exception:
                size = "?"
            self._warn("La copia automatica fallo, PERO en el destino ya hay una ROM")
            self._warn("colocada manualmente:")
            try:
                if os.path.isfile(src) and os.path.getsize(dst) != os.path.getsize(src):
                    self._warn("OJO: esa ROM pesa distinto a la elegida (%s vs %s); puede ser" %
                               (size, fmt_size(os.path.getsize(src))))
                    self._warn("una version anterior. Revisa el resultado en la pausa de DPE.")
            except Exception:
                pass
            self._warn("  %s (%s)" % (dst, size))
            self._warn("SE CONTINUARA con esa ROM. Prueba el resultado en la pausa")
            self._warn("tras el DPE; si no es el esperado, cancela y coloca tu ROM")
            self._warn("a mano como BPRE0.gba.")
            self._make_writable(dst)
            return (True, "usando la ROM ya colocada", "existente")
        self._err("No se pudo copiar %s y no hay ninguna ROM previa en el destino." % label)
        self._err("SOLUCION RAPIDA (30 segundos): copia manualmente %s a" % label)
        self._err("  %s" % dst)
        self._err("(renombrala a BPRE0.gba si hace falta) y vuelve a pulsar INICIAR;")
        self._err("la app la usara automaticamente.")
        return (False, msg, "fallo")

    # ---------------- pasos auxiliares ----------------
    def _backup_file(self, src, tag):
        bdir = os.path.join(self.base_dir, "backups")
        try:
            os.makedirs(bdir, exist_ok=True)
        except Exception as e:
            self._warn("No se pudo crear la carpeta de respaldos (%s)." % e)
            return None
        dst = os.path.join(bdir, "%s_%s%s" %
                           (os.path.splitext(os.path.basename(src))[0], tag,
                            os.path.splitext(src)[1] or ".gba"))
        ok, msg = self._copy_file_robust(src, dst, quiet=True)
        if ok:
            self._ok("Respaldo creado: %s" % dst)
            return dst
        self._warn("No se pudo respaldar %s (%s); continuando sin respaldo." % (src, msg))
        return None

    def _apply_offsets(self, which="both"):
        """Escribe OFFSET_TO_PUT en scripts/make.py de los repos elegidos."""
        if not self.cfg.get("auto_apply_offsets"):
            self._info("Auto-aplicar offsets desactivado: se usan los offsets que ya tienen los make.py.")
            return True
        pairs = []
        if which in ("both", "dpe") and self.cfg.get("dpe_dir"):
            pairs.append(("DPE", os.path.join(self.cfg.get("dpe_dir"), "scripts", "make.py"),
                          normalize_hex(self.cfg.get("offset_dpe"))))
        if which in ("both", "cfru") and self.cfg.get("cfru_dir"):
            pairs.append(("CFRU", os.path.join(self.cfg.get("cfru_dir"), "scripts", "make.py"),
                          normalize_hex(self.cfg.get("offset_cfru"))))
        ok_all = True
        for label, mp, val in pairs:
            if val is None:
                self._warn("Offset de %s invalido; no se modifica make.py." % label)
                ok_all = False
                continue
            ok, msg = RepoInspector.write_offset(mp, val)
            if ok:
                self._ok("%s: %s" % (label, msg))
            else:
                self._err("%s: %s" % (label, msg))
                ok_all = False
        return ok_all

    # ---------------- módulo Shelly (v1.1.0) ----------------

    def _shelly_dir(self):
        """Carpeta del módulo Shelly. Orden: config 'shelly_modulo',
        carpeta 'Shelly-Module' junto a la app, junto al CFRU o al DPE.
        Devuelve la ruta con install_shelly.py o ''."""
        cand = []
        cfg_dir = clean_path(self.cfg.get("shelly_modulo") or "")
        if cfg_dir:
            cand.append(cfg_dir)
        cand.append(os.path.join(app_dir(), "Shelly-Module"))
        base = self.cfg.get("cfru_dir") or ""
        if base:
            cand.append(os.path.join(os.path.dirname(clean_path(base)), "Shelly-Module"))
            cand.append(os.path.join(clean_path(base), "Shelly-Module"))
        base = self.cfg.get("dpe_dir") or ""
        if base:
            cand.append(os.path.join(os.path.dirname(clean_path(base)), "Shelly-Module"))
        for d in cand:
            d = clean_path(d)
            if d and os.path.isfile(os.path.join(d, "install_shelly.py")):
                return d
        return ""

    def _run_shelly_script(self, script, args, timeout=900):
        """Corre un script del módulo Shelly con el Python de compilación.
        Devuelve (ok, salida). 'ok'=False solo si el script fallo de verdad."""
        py = default_python_for_build() \
            if not (self.cfg.get("python_for_build") or "").strip() \
            else clean_path(self.cfg.get("python_for_build"))
        if not (py and os.path.isfile(py)):
            py = sys.executable
        cmd = [py, "-u", script] + args
        env, _dk, _al = build_env_for_make(py)
        try:
            p = subprocess.run(cmd, capture_output=True, universal_newlines=True,
                                encoding="utf-8", errors="replace",
                                timeout=timeout, env=env)
        except subprocess.TimeoutExpired:
            return False, "(sin respuesta tras %ss)" % timeout
        out = ((p.stdout or "") + "\n" + (p.stderr or "")).strip()
        return (p.returncode == 0), out

    def _paso_shelly_instalar(self, dpe, cfru):
        """Instala el módulo Shelly en los repos (idempotente)."""
        mod = self._shelly_dir()
        if not mod:
            self._info("Módulo Shelly: no se encontró 'Shelly-Module' "
                       "(se compila sin Shelly). Coloca la carpeta junto a la app")
            self._info("para activarlo: ver Ayuda sección 6.")
            return True
        self._info("Módulo Shelly detectado en: %s" % mod)
        self._info("Instalando Shelly en los repos (es rápido y no se duplica si ya está)...")
        ok, out = self._run_shelly_script(
            os.path.join(mod, "install_shelly.py"), ["--dpe", dpe, "--cfru", cfru])
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            cls = classify_line(line)
            if "ERROR" in line.upper():
                self._err(line)
            elif "AVISO" in line.upper():
                self._warn(line)
            else:
                self._info(line)
        if not ok:
            self._err("El instalador de Shelly falló. Revisa los mensajes de arriba")
            self._err("(puedes restaurar con: python install_shelly.py --dpe ... --cfru ... --restore)")
        else:
            self._ok("Shelly integrada en los repos (especie 0x5D1 / dex 1026"
                      " + pasiva Vientre Divino + INICIAL compilada dentro"
                      " de la ROM).")
        return ok

    def _pick_build_python(self):
        """Elige un Python que FUNCIONE (v1.0.3): el configurado en Opciones,
        el de la propia app y el lanzador 'py', en ese orden. Se salta el
        alias FALSO de la Microsoft Store y cualquier ejecutable que no
        responda a una sonda. Devuelve (ruta, origen)."""
        conf = clean_path(self.cfg.get("python_for_build"))
        cands = []
        if conf:
            cands.append(("configurado", conf))
        dflt = default_python_for_build()
        if dflt and dflt.lower() != (conf or "").lower():
            cands.append(("python de la app", dflt))
        try:
            w = shutil.which("py")
            if w and all(w.lower() != c[1].lower() for c in cands):
                cands.append(("lanzador py", w))
        except Exception:
            pass
        for name, exe in cands:
            if is_store_stub_path(exe):
                self._warn("El python %s apunta al ALIAS FALSO de la Microsoft Store" % name)
                self._warn("  (%s); se saltara y se buscara otro." % exe)
                continue
            ok, ver = probe_python(exe)
            if ok:
                return exe, name
            self._warn("El python %s no arranca bien (%s); probando el siguiente..." %
                       (name, ver))
        self._warn("Ningun python respondio a la sonda; se intentara con el configurado.")
        return (conf or dflt or "python"), "sin verificar"

    def _run_make(self, repo_dir, label, extra_script=None):
        """Ejecuta python <script> en repo_dir transmitiendo salida en vivo.
        v1.0.3: elige un python que responda de verdad, aisla el alias falso
        de la Microsoft Store y traduce su mensaje si aun aparece."""
        script = extra_script or os.path.join("scripts", "make.py")
        if not os.path.isfile(os.path.join(repo_dir, script)):
            self._err("No se encontro '%s' dentro de %s" % (script, repo_dir))
            return False
        python, py_src = self._pick_build_python()
        cmd = [python, "-u", script]
        env, dk, alias = build_env_for_make(python)
        if py_src != "configurado":
            self._info("Python para compilar: %s (via %s)" % (python, py_src))
        if alias:
            self._info("Alias 'python' de la Microsoft Store aislado (%d en el PATH)"
                       " SOLO durante esta compilacion." % alias)
        if dk[0] and dk[0] != "PATH":
            self._info("devkitARM detectado via %s (%s); se inyectara en el PATH"
                       " solo para esta compilacion." % (dk[0], dk[1]))
        self._info("Ejecutando en %s:  %s" % (os.path.normpath(repo_dir), " ".join(cmd)))
        flags = 0
        if os.name == "nt":
            flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        try:
            proc = subprocess.Popen(
                cmd, cwd=repo_dir,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                universal_newlines=True, encoding="utf-8", errors="replace",
                bufsize=1, creationflags=flags, env=env)
        except Exception as e:
            self._err("No se pudo lanzar make.py (%s). Revisa 'Python para compilar' en Opciones." % e)
            return False
        with self._proc_lock:
            self._proc = proc
        self._check_cancel()
        stub_hit = False
        try:
            for line in proc.stdout:
                if self._cancel:
                    break
                if line.strip():
                    self._log(line)
                    if not stub_hit and is_store_stub_output(line):
                        stub_hit = True
                        self._err(">> ESO que acabas de ver NO es un error tuyo: Windows")
                        self._err(">> uso el python.exe FALSO de la Microsoft Store (alias")
                        self._err(">> de ejecucion de aplicaciones) en lugar del real.")
                        self._err(">> Esta version aísla ese alias en la compilacion; si")
                        self._err(">> vuelve a aparecer, desactiva python/python3 en")
                        self._err(">> Configuracion > Aplicaciones > Alias de ejecucion.")
            rc = proc.wait()
        except Exception as e:
            rc = -1
            self._err("Problema leyendo la salida de make.py: %s" % e)
        finally:
            with self._proc_lock:
                self._proc = None
        self._check_cancel()
        if rc != 0:
            if stub_hit:
                self._err("make.py de %s fallo porque se ejecuto el python.exe FALSO de la" % label)
                self._err("Microsoft Store. Desactiva python/python3 en Configuracion >")
                self._err("Aplicaciones > Alias de ejecucion de aplicaciones y reintenta.")
            else:
                self._err("make.py de %s termino con codigo %s. Revisa las lineas de error arriba." % (label, rc))
            return False
        self._ok("make.py de %s termino correctamente (codigo 0)." % label)
        return True

    def _clean_repo(self, repo_dir, label):
        if os.path.isfile(os.path.join(repo_dir, "scripts", "clean.py")):
            self._info("Limpiando builds previos de %s (scripts/clean.py)..." % label)
            return self._run_make(repo_dir, label, extra_script="scripts/clean.py")
        self._warn("'%s' no tiene scripts/clean.py (tipico del CFRU original de Skeli789); se omite la limpieza."
                   % label)
        return True

    # ---------------- flujo: cadena completa ----------------
    def _do_chain(self):
        problems, rom, dpe, cfru = self._validate_chain()
        if problems:
            for p in problems:
                self._err(p)
            return (False, "", "Configuracion incompleta: " + " | ".join(problems))

        # paso 0: respaldo
        self._step(0, "current")
        if self.cfg.get("backup_enabled"):
            self._backup_file(rom, stamp_compact())
        else:
            self._info("Respaldo desactivado en opciones.")
        self._step(0, "done")
        self._check_cancel()

        # paso 1: preparar
        self._step(1, "current")
        self._apply_offsets("both")
        # v1.1.0: instalar Shelly en los repos (si está activada y presente)
        if self.cfg.get("shelly_activar"):
            self._check_cancel()
            if not self._paso_shelly_instalar(dpe, cfru):
                self._step(1, "fail")
                return (False, "", "El instalador del módulo Shelly falló")
        self._step(1, "done")
        self._check_cancel()

        # paso 2: copiar ROM al DPE
        self._step(2, "current")
        dpe_rom = os.path.join(dpe, "BPRE0.gba")
        self._info("Preparando BPRE0.gba del DPE (%s)..." % fmt_size(os.path.getsize(rom)))
        ok_copy, msg, modo = self._copy_rom_rescued(rom, dpe_rom, "la ROM")
        if not ok_copy:
            self._step(2, "fail")
            return (False, "", "No se pudo copiar la ROM al DPE: %s" % msg)
        if modo == "ya-estaba":
            self._ok("La ROM ya estaba en su sitio: %s" % dpe_rom)
        elif modo == "copiado":
            self._ok("ROM copiada a %s" % dpe_rom)
        self._step(2, "done")
        self._check_cancel()

        # paso 3: make.py DPE
        self._step(3, "current")
        ok = self._run_make(dpe, "DPE")
        if not ok:
            self._step(3, "fail")
            return (False, "", "La compilacion del DPE fallo")
        dpe_out = os.path.join(dpe, "test.gba")
        if not os.path.isfile(dpe_out):
            self._err("El DPE no genero test.gba en %s" % dpe)
            self._step(3, "fail")
            return (False, "", "El DPE no genero test.gba")
        self._ok("DPE listo: %s (%s)" % (dpe_out, fmt_size(os.path.getsize(dpe_out))))
        self._step(3, "done")
        self._check_cancel()

        # paso 4: PAUSA
        self._step(4, "pause")
        self._set_state(self.STATE_PAUSED,
                        "Pausa: revisa el resultado del DPE y pulsa 'Continuar -> CFRU'")
        self._log("[PAUSA] ===============================================", "pause")
        self._log("[PAUSA] Revisa el test.gba del DPE si quieres (emulador).", "pause")
        self._log("[PAUSA] Cuando estes listo, pulsa 'Continuar -> CFRU'.", "pause")
        self._log("[PAUSA] ===============================================", "pause")
        self._pause_evt.wait()
        self._check_cancel()
        self._step(4, "done")

        # paso 5: copiar test.gba del DPE al CFRU
        self._step(5, "current")
        cfru_rom = os.path.join(cfru, "BPRE0.gba")
        ok_copy, msg, modo = self._copy_rom_rescued(dpe_out, cfru_rom, "el test.gba del DPE")
        if not ok_copy:
            self._step(5, "fail")
            return (False, "", "No se pudo copiar test.gba al CFRU: %s" % msg)
        if modo == "copiado":
            self._ok("DPE test.gba copiado a %s" % cfru_rom)
        self._step(5, "done")
        self._check_cancel()

        # paso 6: make.py CFRU
        self._step(6, "current")
        ok = self._run_make(cfru, "CFRU")
        if not ok:
            self._step(6, "fail")
            return (False, "", "La compilacion del CFRU fallo")
        cfru_out = os.path.join(cfru, "test.gba")
        if not os.path.isfile(cfru_out):
            self._err("El CFRU no genero test.gba en %s" % cfru)
            self._step(6, "fail")
            return (False, "", "El CFRU no genero test.gba")
        self._ok("CFRU listo: %s (%s)" % (cfru_out, fmt_size(os.path.getsize(cfru_out))))
        self._step(6, "done")
        self._check_cancel()

        # paso 7: ROM final
        self._step(7, "current")
        rom_out = self._save_final_rom(cfru_out)
        if not rom_out:
            self._step(7, "fail")
            return (False, "", "No se pudo guardar la ROM final")
        # v1.3.0: el inicial de Shelly va COMPILADO DENTRO de la ROM (módulo
        # v1.4+); ya no se parchea nada tras compilar.
        if self.cfg.get("shelly_activar"):
            mod = self._shelly_dir()
            if mod:
                self._ok("Shelly inicial: ya viene compilada DENTRO de la ROM "
                         "(módulo v1.4). Nada que parchear: todo listo.")
        self._step(7, "done")
        self._check_cancel()

        # paso 8: historial
        self._step(8, "done")
        self._log("", "")
        self._ok("CADENA COMPLETA FINALIZADA.")
        self._ok("ROM final lista: %s" % rom_out)
        return (True, rom_out, "Cadena completa DPE->CFRU exitosa")

    # ---------------- flujo: actualizaciones ----------------
    def _do_update_dpe(self):
        problems, rom, dpe, cfru = self._validate_common(True, False)
        if problems:
            for p in problems:
                self._err(p)
            return (False, "", "Configuracion incompleta: " + " | ".join(problems))
        dpe_rom = os.path.join(dpe, "BPRE0.gba")
        if not os.path.isfile(dpe_rom):
            if rom and os.path.isfile(rom):
                self._warn("No habia BPRE0.gba en la carpeta DPE; se copiara tu ROM configurada.")
                ok_copy, msg, _modo = self._copy_rom_rescued(rom, dpe_rom, "la ROM")
                if not ok_copy:
                    return (False, "", "No se pudo copiar la ROM al DPE: %s" % msg)
            else:
                self._err("La carpeta DPE no tiene BPRE0.gba y no hay ROM configurada.")
                return (False, "", "Falta BPRE0.gba en el DPE")
        if self.cfg.get("clean_before_update"):
            self._clean_repo(dpe, "DPE")
        self._check_cancel()
        if self.cfg.get("backup_enabled"):
            prev = os.path.join(dpe, "test.gba")
            if os.path.isfile(prev):
                self._backup_file(prev, "prev_" + stamp_compact())
        self._apply_offsets("dpe")
        self._check_cancel()
        ok = self._run_make(dpe, "DPE")
        if not ok:
            return (False, "", "La actualizacion del DPE fallo")
        out = os.path.join(dpe, "test.gba")
        self._ok("DPE actualizado: %s (%s)" % (out, fmt_size(os.path.getsize(out))))
        self._ok("Recuerda: si quieres la ROM final, ejecuta 'Reinstalar CFRU' o la cadena completa.")
        return (True, out, "DPE reinstalado correctamente")

    def _do_update_cfru(self):
        problems, rom, dpe, cfru = self._validate_common(False, True)
        if problems:
            for p in problems:
                self._err(p)
            return (False, "", "Configuracion incompleta: " + " | ".join(problems))
        cfru_rom = os.path.join(cfru, "BPRE0.gba")
        if not os.path.isfile(cfru_rom):
            # la entrada correcta del CFRU es el test.gba del DPE
            src = os.path.join(dpe, "test.gba") if dpe else ""
            if src and os.path.isfile(src):
                self._warn("No habia BPRE0.gba en el CFRU; se copiara el test.gba del DPE.")
                ok_copy, msg, _modo = self._copy_rom_rescued(src, cfru_rom, "el test.gba del DPE")
                if not ok_copy:
                    return (False, "", "No se pudo copiar test.gba al CFRU: %s" % msg)
            elif rom and os.path.isfile(rom):
                self._warn("No hay test.gba del DPE; se copiara la ROM base SIN DPE "
                           "(solo valido si el DPE ya esta dentro de esa ROM).")
                ok_copy, msg, _modo = self._copy_rom_rescued(rom, cfru_rom, "la ROM base")
                if not ok_copy:
                    return (False, "", "No se pudo copiar la ROM al CFRU: %s" % msg)
            else:
                self._err("El CFRU necesita como entrada la ROM con el DPE ya insertado "
                          "(DPE/test.gba) y no se encontro ninguna.")
                return (False, "", "Falta la ROM de entrada para el CFRU")
        if self.cfg.get("clean_before_update"):
            self._clean_repo(cfru, "CFRU")
        self._check_cancel()
        if self.cfg.get("backup_enabled"):
            prev = os.path.join(cfru, "test.gba")
            if os.path.isfile(prev):
                self._backup_file(prev, "prev_" + stamp_compact())
        self._apply_offsets("cfru")
        self._check_cancel()
        ok = self._run_make(cfru, "CFRU")
        if not ok:
            return (False, "", "La actualizacion del CFRU fallo")
        out = os.path.join(cfru, "test.gba")
        rom_out = self._save_final_rom(out)
        summary = "CFRU reinstalado correctamente"
        if rom_out:
            summary += "; ROM final: %s" % os.path.basename(rom_out)
        self._ok("CFRU actualizado: %s (%s)" % (out, fmt_size(os.path.getsize(out))))
        return (True, rom_out, summary)

    # ---------------- utilidades de flujo ----------------
    def _higiene_sav(self, rom_final):
        """v1.2.2: renombra (sin borrar) los .sav/.sgm/.ssN/.saN viejos que el
        emulador asociaría a la ROM final recién creada. Un .sav de una
        compilación ANTERIOR hace que el juego arranque con una partida ya
        creada ("ya se crea una partida"), sin Shelly y con datos
        incompatibles que pueden colgar el juego."""
        if not rom_final or not self.cfg.get("higiene_sav"):
            return
        base = os.path.splitext(rom_final)[0]
        carpeta = os.path.dirname(rom_final) or "."
        sufijos = [".sav", ".sgm"] + [".ss%d" % i for i in range(10)] + \
                  [".sa%d" % i for i in range(10)]
        stamp = stamp_compact()
        movidos = []
        fallados = []
        for suf in sufijos:
            viejo = base + suf
            if os.path.isfile(viejo):
                nuevo = "%s.bak_%s%s" % (viejo, stamp, suf)
                try:
                    os.replace(viejo, nuevo)
                    movidos.append(os.path.basename(viejo))
                except OSError:
                    fallados.append(os.path.basename(viejo))
        if movidos:
            self._warn("Guardado viejo separado: " + ", ".join(movidos) +
                       "  (era de una compilación anterior: cargarlo "
                       "confunde al juego). Si lo quieres, está como "
                       ".bak_" + stamp + " junto a la ROM.")
        for nombre in fallados:
            self._warn("Existe " + nombre +
                       " junto a la ROM final y no se pudo renombrar "
                       "(¿emulador abierto?). Ciérralo y bórralo a "
                       "mano, o el juego arrancará con la partida "
                       "vieja.")

    def _save_final_rom(self, built_rom):
        out_dir = clean_path(self.cfg.get("out_dir")) or \
            os.path.dirname(clean_path(self.cfg.get("rom_path")) or built_rom)
        if not out_dir:
            out_dir = self.base_dir
        name = (self.cfg.get("out_name") or "MiHack_CFRU").strip() or "MiHack_CFRU"
        if not name.lower().endswith(".gba"):
            name += ".gba"
        candidate = os.path.join(out_dir, name)
        base, ext = os.path.splitext(name)
        if os.path.exists(candidate):
            candidate = os.path.join(out_dir, "%s_%s%s" % (base, stamp_compact(), ext))
        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as e:
            self._err("No se pudo crear la carpeta de salida %s (%s)." % (out_dir, e))
            return None
        ok_copy, msg = self._copy_file_robust(built_rom, candidate)
        if not ok_copy:
            self._err("No se pudo guardar la ROM final en %s." % candidate)
            return None
        self._ok("ROM final guardada en: %s (%s)" % (candidate, fmt_size(os.path.getsize(candidate))))
        self._higiene_sav(candidate)
        ini = os.path.join(os.path.dirname(built_rom), "offsets.ini")
        if os.path.isfile(ini):
            self._info("El CFRU genero tambien offsets.ini con las direcciones insertadas (%s)." % ini)
        return candidate


class _CancelError(Exception):
    pass


# ---------------------------------------------------------------------------
# GUI (Tkinter) — tema dark gamer
# ---------------------------------------------------------------------------
def dark_button(parent, text, bg, fg, cmd, font=None, padx=14, pady=7, tip=None):
    b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, font=font or FONT_UI_B,
                  activebackground=C_PANEL2, activeforeground=fg, relief="flat",
                  bd=0, cursor="hand2", padx=padx, pady=pady, takefocus=0,
                  disabledforeground=C_MUTED)
    if bg != C_PANEL2:
        b.bind("<Enter>", lambda e: b.config(bg=C_PANEL2))
        b.bind("<Leave>", lambda e: b.config(bg=bg))
    return b


def ghost_button(parent, text, cmd, tip=None):
    return dark_button(parent, text, C_PANEL2, C_MUTED, cmd, font=FONT_UI, tip=tip)


def pill(parent, text, color):
    """Etiqueta pequena tipo 'pastilla' de estado."""
    l = tk.Label(parent, text=text, fg=color, bg=C_PANEL, font=FONT_SMALL,
                 padx=8, pady=3, highlightthickness=1,
                 highlightbackground=color, highlightcolor=color)
    return l


class App(tk.Tk):

    def __init__(self):
        tk.Tk.__init__(self)
        self.cfg = ConfigStore()
        self.history = History()
        self.evq = queue.Queue()
        self.engine = BuildEngine(self.evq, self.cfg, self.history)

        self.title("CFRU Builder — Compilador DPE + CFRU")
        self.configure(bg=C_BG)
        self._set_win_geometry()

        self.pipeline_rows = []
        self._build_style()
        self._build_header()
        self._build_body()
        self._build_console()
        self._build_statusbar()

        self._gui_from_config()
        self._refresh_checks()
        self._load_history()

        self.after(80, self._pump_events)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ base
    def _set_win_geometry(self):
        geo = self.cfg.get("geometry") or "1080x740"
        try:
            self.geometry(geo)
        except Exception:
            pass
        self.minsize(980, 660)

    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        base = dict(background=C_BG, foreground=C_FG, bordercolor=C_BORDER,
                    lightcolor=C_BORDER, darkcolor=C_BORDER, troughcolor=C_PANEL)
        style.configure(".", **base)
        style.configure("TNotebook", background=C_BG, borderwidth=0, tabmargins=[6, 6, 6, 0])
        style.configure("TNotebook.Tab", background=C_PANEL, foreground=C_MUTED,
                        padding=(16, 8), borderwidth=0, font=FONT_UI_B)
        style.map("TNotebook.Tab",
                  background=[("selected", C_PANEL2)],
                  foreground=[("selected", C_FG)])
        style.configure("Treeview", background=C_INPUT, foreground=C_FG,
                        fieldbackground=C_INPUT, bordercolor=C_BORDER, rowheight=26,
                        font=FONT_UI)
        style.configure("Treeview.Heading", background=C_PANEL, foreground=C_MUTED,
                        bordercolor=C_BORDER, font=FONT_UI_B, relief="flat")
        style.map("Treeview", background=[("selected", "#263041")],
                  foreground=[("selected", C_FG)])
        style.map("Treeview.Heading", background=[("active", C_PANEL2)])
        style.configure("Vertical.TScrollbar", background=C_PANEL,
                        troughcolor=C_INPUT, bordercolor=C_INPUT, arrowcolor=C_MUTED)

    def _build_header(self):
        head = tk.Frame(self, bg=C_BG)
        head.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 4))
        head.columnconfigure(1, weight=1)

        left = tk.Frame(head, bg=C_BG)
        left.grid(row=0, column=0, sticky="w")
        tk.Label(left, text="CFRU Builder", font=FONT_TITLE, bg=C_BG,
                 fg=C_GREEN).pack(side="left")
        tk.Label(left, text="  v" + APP_VERSION, font=FONT_SMALL, bg=C_BG,
                 fg=C_MUTED).pack(side="left", pady=(10, 0))
        tk.Label(head, text="DPE primero → pausa → CFRU  |  Guia oficial de Skeli789 automatizada",
                 font=FONT_UI, bg=C_BG, fg=C_MUTED).grid(row=1, column=0, sticky="w")

        self.pill_box = tk.Frame(head, bg=C_BG)
        self.pill_box.grid(row=0, column=1, sticky="e")
        self.pill_python = pill(self.pill_box, "…", C_MUTED)
        self.pill_devkit = pill(self.pill_box, "…", C_MUTED)
        self.pill_rom = pill(self.pill_box, "…", C_MUTED)
        self.pill_shelly = pill(self.pill_box, "…", C_MUTED)
        for p in (self.pill_python, self.pill_devkit, self.pill_rom, self.pill_shelly):
            p.pack(side="left", padx=(6, 0))

    def _build_body(self):
        body = tk.Frame(self, bg=C_BG)
        body.grid(row=1, column=0, sticky="nsew", padx=14, pady=4)
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)

        self._build_left_panel(body)
        self._build_right_panel(body)

    # ------------------------------------------------------------- panel izq
    def _section(self, parent, title, accent):
        fr = tk.Frame(parent, bg=C_PANEL, highlightthickness=1,
                      highlightbackground=C_BORDER, padx=12, pady=9)
        head = tk.Label(fr, text="» " + title, font=FONT_UI_B, bg=C_PANEL,
                        fg=accent, anchor="w")
        head.pack(fill="x")
        return fr

    def _build_left_panel(self, parent):
        # v1.2.0: panel con BARRA DE DESPLAZAMIENTO — en pantallas bajas la
        # sección «Opciones» quedaba fuera de la vista y parecía inexistente.
        cont = tk.Frame(parent, bg=C_BG)
        cont.grid(row=0, column=0, sticky="nsw")
        cont.rowconfigure(0, weight=1)
        self._left_canvas = tk.Canvas(cont, bg=C_BG, highlightthickness=0,
                                      width=396)
        vsb = ttk.Scrollbar(cont, orient="vertical",
                           command=self._left_canvas.yview)
        self._left_canvas.configure(yscrollcommand=vsb.set)
        self._left_canvas.grid(row=0, column=0, sticky="nsw")
        vsb.grid(row=0, column=1, sticky="ns")
        left = tk.Frame(self._left_canvas, bg=C_BG, width=396)
        _lid = self._left_canvas.create_window((0, 0), window=left, anchor="nw")
        left.bind("<Configure>", lambda e: self._left_canvas.configure(
            scrollregion=self._left_canvas.bbox("all")))
        self._left_canvas.bind("<Configure>", lambda e, lid=_lid:
            self._left_canvas.itemconfigure(lid, width=e.width))

        def _rueda(e):
            self._left_canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")

        self._left_canvas.bind("<Enter>", lambda e: left.bind_all("<MouseWheel>", _rueda))
        self._left_canvas.bind("<Leave>", lambda e: left.unbind_all("<MouseWheel>"))
        left.columnconfigure(0, weight=1)

        # --- ROM ---
        sec = self._section(left, "ROM FireRed (BPRE)", C_GREEN)
        sec.pack(fill="x", pady=(0, 8))
        self.lbl_rom = tk.Label(sec, text="Ninguna ROM seleccionada", font=FONT_UI,
                                bg=C_PANEL, fg=C_MUTED, anchor="w", wraplength=340, justify="left")
        self.lbl_rom.pack(fill="x", pady=(2, 4))
        row = tk.Frame(sec, bg=C_PANEL); row.pack(fill="x")
        dark_button(row, "Elegir ROM…", C_GREEN_D, "#ffffff",
                    self.choose_rom).pack(side="left")
        ghost_button(row, "Abrir carpeta", lambda: self._open_dir_of("rom_path")).pack(
            side="left", padx=(8, 0))
        self.lbl_rom_info = tk.Label(sec, text="", font=FONT_SMALL, bg=C_PANEL,
                                     fg=C_MUTED, anchor="w", justify="left")
        self.lbl_rom_info.pack(fill="x")

        # --- DPE ---
        sec = self._section(left, "Carpeta del DPE", C_BLUE)
        sec.pack(fill="x", pady=(0, 8))
        self.lbl_dpe = tk.Label(sec, text="Sin carpeta", font=FONT_UI, bg=C_PANEL,
                                fg=C_MUTED, anchor="w", wraplength=340, justify="left")
        self.lbl_dpe.pack(fill="x", pady=(2, 4))
        row = tk.Frame(sec, bg=C_PANEL); row.pack(fill="x")
        dark_button(row, "Elegir carpeta…", "#1f4c78", "#ffffff",
                    self.choose_dpe).pack(side="left")
        self.lbl_dpe_badge = tk.Label(sec, text="", font=FONT_SMALL, bg=C_PANEL,
                                       fg=C_BLUE, anchor="w")
        self.lbl_dpe_badge.pack(fill="x")

        # --- CFRU ---
        sec = self._section(left, "Carpeta del CFRU", C_RED)
        sec.pack(fill="x", pady=(0, 8))
        self.lbl_cfru = tk.Label(sec, text="Sin carpeta", font=FONT_UI, bg=C_PANEL,
                                 fg=C_MUTED, anchor="w", wraplength=340, justify="left")
        self.lbl_cfru.pack(fill="x", pady=(2, 4))
        row = tk.Frame(sec, bg=C_PANEL); row.pack(fill="x")
        dark_button(row, "Elegir carpeta…", "#7a2b32", "#ffffff",
                    self.choose_cfru).pack(side="left")
        self.lbl_cfru_badge = tk.Label(sec, text="", font=FONT_SMALL, bg=C_PANEL,
                                       fg=C_RED, anchor="w")
        self.lbl_cfru_badge.pack(fill="x")

        # --- Offsets ---
        sec = self._section(left, "Offsets de insercion", C_PURPLE)
        sec.pack(fill="x", pady=(0, 8))
        off = tk.Frame(sec, bg=C_PANEL); off.pack(fill="x"); off.columnconfigure(1, weight=1)
        tk.Label(off, text="DPE", font=FONT_UI, bg=C_PANEL, fg=C_MUTED).grid(row=0, column=0, sticky="w")
        self.ent_off_dpe = tk.Entry(off, font=FONT_MONO, bg=C_INPUT, fg=C_FG,
                                    insertbackground=C_FG, relief="flat",
                                    highlightthickness=1, highlightbackground=C_BORDER)
        self.ent_off_dpe.grid(row=0, column=1, sticky="ew", padx=(8, 0), pady=2)
        tk.Label(off, text="CFRU", font=FONT_UI, bg=C_PANEL, fg=C_MUTED).grid(row=1, column=0, sticky="w")
        self.ent_off_cfru = tk.Entry(off, font=FONT_MONO, bg=C_INPUT, fg=C_FG,
                                     insertbackground=C_FG, relief="flat",
                                     highlightthickness=1, highlightbackground=C_BORDER)
        self.ent_off_cfru.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=2)
        self.lbl_offset_state = tk.Label(sec, text="", font=FONT_SMALL, bg=C_PANEL,
                                         fg=C_MUTED, anchor="w", justify="left")
        self.lbl_offset_state.pack(fill="x", pady=(2, 0))
        dark_button(sec, "Aplicar offsets a los make.py", C_PANEL2, C_PURPLE,
                    self.apply_offsets_now, font=FONT_UI).pack(fill="x", pady=(4, 0))

        # --- Salida ---
        sec = self._section(left, "ROM final", C_GREEN)
        sec.pack(fill="x", pady=(0, 8))
        out = tk.Frame(sec, bg=C_PANEL); out.pack(fill="x"); out.columnconfigure(0, weight=1)
        self.ent_out_name = tk.Entry(out, font=FONT_UI, bg=C_INPUT, fg=C_FG,
                                     insertbackground=C_FG, relief="flat",
                                     highlightthickness=1, highlightbackground=C_BORDER)
        self.ent_out_name.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        self.ent_out_name.insert(0, "MiHack_CFRU.gba")
        self.lbl_out_dir = tk.Label(sec, text="", font=FONT_SMALL, bg=C_PANEL,
                                    fg=C_MUTED, anchor="w", wraplength=340, justify="left")
        self.lbl_out_dir.pack(fill="x")
        dark_button(sec, "Elegir carpeta de salida…", C_PANEL2, C_FG,
                    self.choose_out_dir, font=FONT_UI).pack(fill="x", pady=(4, 0))

        # --- Opciones ---
        sec = self._section(left, "Opciones", C_YELLOW)
        sec.pack(fill="x", pady=(0, 8))
        self.var_auto_off = tk.BooleanVar(value=True)
        self.var_backup = tk.BooleanVar(value=True)
        self.var_clean = tk.BooleanVar(value=False)
        self.var_shelly = tk.BooleanVar(value=True)
        self.var_sav = tk.BooleanVar(value=True)
        for var, txt in ((self.var_auto_off, "Aplicar offsets automaticamente antes de compilar"),
                         (self.var_backup, "Respaldar ROM antes de cada compilacion"),
                         (self.var_clean, "Ejecutar clean.py antes de actualizar (fork)"),
                         (self.var_shelly, "Módulo Shelly: integrarla en los repos; el inicial se COMPILA DENTRO de la ROM (v1.4+)"),
                         (self.var_sav, "Renombrar el .sav/.sgm viejo de la ROM final (recomendado)")):
            cb = tk.Checkbutton(sec, text=txt, variable=var, command=self._save_options,
                               font=FONT_UI, bg=C_PANEL, fg=C_FG,
                               selectcolor=C_INPUT, activebackground=C_PANEL,
                               activeforeground=C_FG, relief="flat",
                               anchor="w", highlightthickness=0, bd=0)
            cb.pack(fill="x", pady=1)
        row = tk.Frame(sec, bg=C_PANEL); row.pack(fill="x", pady=(4, 0))
        row.columnconfigure(0, weight=1)
        tk.Label(row, text="Python para compilar (vacio = el de esta app, recomendado):", font=FONT_SMALL,
                 bg=C_PANEL, fg=C_MUTED, anchor="w").grid(row=0, column=0, sticky="w")
        tk.Label(row, text="Original de Skeli789: Python 3.7.x. Fork de Shiny-Miner: Python moderno.",
                 font=FONT_SMALL, bg=C_PANEL, fg=C_MUTED, anchor="w").grid(row=1, column=0, sticky="w")
        pr = tk.Frame(sec, bg=C_PANEL); pr.pack(fill="x"); pr.columnconfigure(0, weight=1)
        self.ent_python = tk.Entry(pr, font=FONT_SMALL, bg=C_INPUT, fg=C_FG,
                                   insertbackground=C_FG, relief="flat",
                                   highlightthickness=1, highlightbackground=C_BORDER)
        self.ent_python.grid(row=0, column=0, sticky="ew", pady=2)
        ghost_button(pr, "Elegir…", self.choose_python).grid(row=0, column=1, padx=(6, 0))

    # ----> el panel derecho y el resto de la GUI se construyen en _build_right_panel

    # ---------------------------------------------------------- panel derecho
    def _build_right_panel(self, parent):
        right = tk.Frame(parent, bg=C_BG)
        right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        right.rowconfigure(0, weight=1)
        right.columnconfigure(0, weight=1)

        self.nb = ttk.Notebook(right)
        self.nb.grid(row=0, column=0, sticky="nsew")
        self.tab_build = tk.Frame(self.nb, bg=C_PANEL)
        self.tab_update = tk.Frame(self.nb, bg=C_PANEL)
        self.tab_hist = tk.Frame(self.nb, bg=C_PANEL)
        self.tab_help = tk.Frame(self.nb, bg=C_PANEL)
        self.nb.add(self.tab_build, text="  Compilar  ")
        self.nb.add(self.tab_update, text="  Actualizar  ")
        self.nb.add(self.tab_hist, text="  Historial  ")
        self.nb.add(self.tab_help, text="  Ayuda  ")
        self._build_tab_build(self.tab_build)
        self._build_tab_update(self.tab_update)
        self._build_tab_hist(self.tab_hist)
        self._build_tab_help(self.tab_help)
        self._set_run_buttons(idle=True)

    # -------------------------------------------------------------- p. compilar
    def _build_tab_build(self, parent):
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)

        top = tk.Frame(parent, bg=C_PANEL); top.grid(row=0, column=0, sticky="ew", padx=10, pady=8)
        tk.Label(top, text="Pipeline de compilacion completa",
                 font=FONT_UI_B, bg=C_PANEL, fg=C_FG).pack(anchor="w")
        tk.Label(top, text="La cadena se detendra tras compilar el DPE para que revises el test.gba "
                            "(puedes probarlo en un emulador) antes de insertar el CFRU.",
                 font=FONT_SMALL, bg=C_PANEL, fg=C_MUTED, wraplength=560, justify="left").pack(anchor="w")

        steps = tk.Frame(parent, bg=C_PANEL2, highlightthickness=1,
                         highlightbackground=C_BORDER)
        steps.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 8))
        steps.columnconfigure(1, weight=1)
        self.pipeline_rows = []
        for i, name in enumerate(BuildEngine.CHAIN_STEPS):
            ico = tk.Label(steps, text="○", font=FONT_UI_B, bg=C_PANEL2, fg=C_MUTED, width=3)
            ico.grid(row=i, column=0, sticky="w", padx=(10, 0), pady=3)
            lbl = tk.Label(steps, text=name, font=FONT_UI, bg=C_PANEL2, fg=C_MUTED, anchor="w")
            lbl.grid(row=i, column=1, sticky="w", padx=(0, 10), pady=3)
            self.pipeline_rows.append((ico, lbl))

        actions = tk.Frame(parent, bg=C_PANEL); actions.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.btn_start = dark_button(actions, "▶  INICIAR CADENA DPE → CFRU", C_GREEN_D, "#ffffff",
                                     self.start_chain, padx=18, pady=9)
        self.btn_start.pack(side="left")
        self.btn_continue = dark_button(actions, "➡  CONTINUAR → CFRU", "#1f4c78", "#ffffff",
                                        self.continue_chain, padx=18, pady=9)
        self.btn_continue.pack(side="left", padx=(8, 0))
        self.btn_cancel = dark_button(actions, "⏹  CANCELAR", "#7a2b32", "#ffffff",
                                      self.cancel_chain, padx=18, pady=9)
        self.btn_cancel.pack(side="left", padx=(8, 0))

    # -------------------------------------------------------------- p. actualizar
    def _build_tab_update(self, parent):
        parent.columnconfigure(0, weight=1)
        tk.Label(parent, text="Modo actualizacion",
                 font=("Segoe UI", 12, "bold"), bg=C_PANEL, fg=C_FG).grid(
            row=0, column=0, sticky="w", padx=12, pady=(12, 2))
        tk.Label(parent, text="Editaste habilidades, movimientos, items o mecanicas en los archivos fuente "
                              "de un repo? Reinstala SOLO ese motor sin tocar el otro. El CFRU tomara como "
                              "entrada el test.gba que genero el DPE la ultima vez.",
                 font=FONT_UI, bg=C_PANEL, fg=C_MUTED, wraplength=580, justify="left").grid(
            row=1, column=0, sticky="w", padx=12)

        cards = tk.Frame(parent, bg=C_PANEL); cards.grid(row=2, column=0, sticky="ew", padx=12, pady=10)
        cards.columnconfigure(0, weight=1); cards.columnconfigure(1, weight=1)

        # --- tarjeta DPE ---
        c1 = tk.Frame(cards, bg=C_PANEL2, highlightthickness=1, highlightbackground=C_BORDER,
                      padx=14, pady=12)
        c1.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        tk.Label(c1, text="Reinstalar solo DPE", font=FONT_UI_B, bg=C_PANEL2,
                 fg=C_BLUE, anchor="w").pack(fill="x")
        tk.Label(c1, text="Usalo cuando cambiaste especies, stats, sprites o datos del DPE "
                          "(ej. agregaste un Pokemon Gen 9). Re-ejecuta make.py en la carpeta del DPE.",
                 font=FONT_SMALL, bg=C_PANEL2, fg=C_MUTED, wraplength=250, justify="left").pack(
            fill="x", pady=(4, 8))
        self.btn_upd_dpe = dark_button(c1, "🔄  Reinstalar DPE", "#1f4c78", "#ffffff",
                                       self.update_dpe)
        self.btn_upd_dpe.pack(fill="x")

        # --- tarjeta CFRU ---
        c2 = tk.Frame(cards, bg=C_PANEL2, highlightthickness=1, highlightbackground=C_BORDER,
                      padx=14, pady=12)
        c2.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        tk.Label(c2, text="Reinstalar solo CFRU", font=FONT_UI_B, bg=C_PANEL2,
                 fg=C_RED, anchor="w").pack(fill="x")
        tk.Label(c2, text="Usalo cuando cambiaste habilidades, moves, items o mecanicas del CFRU "
                          "(ej. editaste src/abilities o Data). Al terminar se guarda la ROM final "
                          "en tu carpeta de salida.",
                 font=FONT_SMALL, bg=C_PANEL2, fg=C_MUTED, wraplength=250, justify="left").pack(
            fill="x", pady=(4, 8))
        self.btn_upd_cfru = dark_button(c2, "🔄  Reinstalar CFRU", "#7a2b32", "#ffffff",
                                        self.update_cfru)
        self.btn_upd_cfru.pack(fill="x")

        note = tk.Frame(parent, bg=C_PANEL); note.grid(row=3, column=0, sticky="ew", padx=12)
        tk.Label(note, text="Tips:  · activa 'Respaldar ROM' en Opciones para guardar una copia antes de recompilar"
                            "      · 'clean.py antes de actualizar' aplica solo si tu repo es el fork "
                            "Shiny-Miner (el original de Skeli789 no trae clean.py)",
                 font=FONT_SMALL, bg=C_PANEL, fg=C_MUTED, justify="left").pack(anchor="w")

    # -------------------------------------------------------------- p. historial
    def _build_tab_hist(self, parent):
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        wrap = tk.Frame(parent, bg=C_PANEL); wrap.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        wrap.rowconfigure(0, weight=1); wrap.columnconfigure(0, weight=1)

        cols = ("fecha", "modo", "duracion", "resultado", "resumen")
        self.tree = ttk.Treeview(wrap, columns=cols, show="headings", selectmode="browse")
        for cid, txt, w, anchor in (("fecha", "Fecha", 150, "w"),
                                    ("modo", "Modo", 120, "w"),
                                    ("duracion", "Duracion", 70, "center"),
                                    ("resultado", "Resultado", 80, "center"),
                                    ("resumen", "Resumen", 320, "w")):
            self.tree.heading(cid, text=txt)
            self.tree.column(cid, width=w, anchor=anchor, stretch=(cid == "resumen"))
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self.tree.tag_configure("ok", foreground=C_GREEN)
        self.tree.tag_configure("bad", foreground=C_RED)

        bar = tk.Frame(parent, bg=C_PANEL); bar.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        ghost_button(bar, "Ver log…", self.view_history_log).pack(side="left")
        ghost_button(bar, "Abrir carpeta de logs", lambda: open_path(self.history.logs_dir)).pack(
            side="left", padx=(8, 0))
        ghost_button(bar, "Refrescar", self._load_history).pack(side="left", padx=(8, 0))
        ghost_button(bar, "Borrar historial", self.clear_history).pack(side="right")

    # -------------------------------------------------------------- p. ayuda
    def _build_tab_help(self, parent):
        parent.rowconfigure(0, weight=1)
        parent.columnconfigure(0, weight=1)
        self.help_text = ScrolledText(parent, bg=C_INPUT, fg=C_FG, font=("Consolas", 10),
                                     relief="flat", insertbackground=C_FG, borderwidth=0,
                                     padx=14, pady=12, state="disabled", wrap="word")
        self.help_text.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        for tag, color in (("h1", C_GREEN), ("h2", C_BLUE), ("ok", C_GREEN),
                           ("warn", C_YELLOW), ("err", C_RED), ("muted", C_MUTED)):
            self.help_text.tag_configure(tag, foreground=color)
        self.help_text.tag_configure("h1", font=("Consolas", 13, "bold"))
        self.help_text.tag_configure("h2", font=("Consolas", 11, "bold"))
        self._fill_help()

    HELP_MD = [
        ("h1", "CFRU Builder — Ayuda rapida"),
        ("", ""),
        ("h2", "1) Requisitos (una sola vez, igual que la guia oficial de Skeli789)"),
        ("ok", "   * Python 3.7.x en el sistema (el CFRU/DPE originales NO aceptan 3.8+)."),
        ("ok", "   * devkitPro con devkitARM instalado."),
        ("ok", "   * La app lo busca en PATH, variables, registro y disco"),
        ("ok", "       (ejemplo: C:\\devkitPro\\devkitARM\\bin) y lo inyecta"),
        ("ok", "       sola en la compilacion si hace falta."),
        ("ok", "   * Una ROM de Pokemon FireRed US 1.0 (codigo interno BPRE)."),
        ("warn", "   Nota: deja 'Python para compilar' VACIO y la app usara su propio"),
        ("warn", "   Python real para los make.py. Solo pon 3.7.6 si compilas los repos"),
        ("warn", "   ORIGINALES de Skeli789 (los forks de Shiny-Miner piden Python moderno)."),
        ("", ""),
        ("h2", "2) Configuracion del panel izquierdo"),
        ("", "   * Elegir ROM......... tu FireRed 1.0 limpia (o tu hack binario BPRE)."),
        ("", "   * Carpeta del DPE ... la raiz del repo Dynamic Pokemon Expansion"),
        ("", "                           (Shiny-Miner Gen 9 o Skeli789 original)."),
        ("", "   * Carpeta del CFRU .. la raiz del repo Complete Fire Red Upgrade"),
        ("", "                           (CFRU-expansion de Shiny-Miner o Skeli789 original)."),
        ("", "   * Offsets........... DPE y CFRU DEBEN usar offsets distintos"),
        ("", "                           (ej. DPE 0x750000 / CFRU 0x900000). La app los"),
        ("", "                           escribe sola en scripts/make.py (OFFSET_TO_PUT)."),
        ("", "   * ROM final......... nombre y carpeta de la ROM compilada resultante."),
        ("", ""),
        ("h2", "3) Compilar (pestaña Compilar)"),
        ("", "   1. Pulsa INICIAR CADENA DPE → CFRU."),
        ("", "   2. La app respalda tu ROM, copia BPRE0.gba al DPE y corre make.py en vivo."),
        ("", "   3. PAUSA: proba el test.gba del DPE en un emulador si queres."),
        ("", "   4. Pulsa CONTINUAR → CFRU: copia ese test.gba al CFRU y compila el CFRU."),
        ("", "   5. Al terminar, la ROM final queda en tu carpeta de salida."),
        ("", "      La app guarda ademas offsets.ini con las direcciones insertadas."),
        ("", ""),
        ("h2", "4) Actualizar (pestaña Actualizar)"),
        ("", "   * Reinstalar solo DPE .... si editaste datos de especies/sprites del DPE."),
        ("", "   * Reinstalar solo CFRU ... si editaste habilidades, moves, items, mecanicas"),
        ("", "                               o cualquier archivo del CFRU. Al finalizar guarda"),
        ("", "                               la ROM final directamente (usa el test.gba del DPE)."),
        ("", "   * Si cambian MUCHAS cosas, usa la cadena completa para partir de cero."),
        ("", ""),
        ("h2", "5) Módulo Shelly (v1.4.0) — inicial COMPILADO en la ROM + pasiva"),
        ("", "   Shelly (Team Aqua) se une al juego como especie propia:"),
        ("ok", "   * Especie 0x5D1 (1489) / Pokédex nacional 1026 / tipo NORMAL."),
        ("ok", "   * Llega a TU CUARTO al arrancar partida (nv. 5, con mensaje y"),
        ("ok", "     fanfarria). El flujo de Oak se mantiene igual."),
        ("ok", "   * NUEVO v1.4: el evento de llegada vive en los ARCHIVOS del CFRU"),
        ("ok", "     (src/shelly_module.c + shelly_inicial.s + shelly_inicial.string)"),
        ("ok", "     y se COMPILA DENTRO de la ROM con make.py. Ya NO EXISTE"),
        ("ok", "     parche_inicial.py ni se toca la ROM tras compilar: la ROM"),
        ("ok", "     final sale con Shelly inicial ya integrada."),
        ("ok", "   * Follower activo (camina detrás de ti como chica LASS)."),
        ("ok", "   * Pasiva «VIENTRE DIVINO» (exclusiva, v1.1 del módulo):"),
        ("", "       - Esquiva el 65% de TODOS los movimientos (también"),
        ("", "         movimientos de estado como Hipnosis, Rayo o Tóxico)."),
        ("", "       - Refleja el 45% del daño que recibe de vuelta al atacante."),
        ("", "       - Congelada: un 25% de los daños se anulan por completo."),
        ("", "       - Burbuja/Burbuja Lente/Rayo Hielo y familia: 25% de"),
        ("", "         atraparla en una burbuja 3-6 turnos (no puede cambiar"),
        ("", "         de Pokémon y la burbuja no le hace daño por turnos)."),
        ("", "       - Golpe Cuerpo/Placaje/Pisotón y familia: 25% de aplanarla"),
        ("", "         3-5 turnos (no puede moverse mientras siga aplanada)."),
        ("", "   Dónde está «Opciones»: es la última sección del PANEL IZQUIERDO"),
        ("", "   (debajo de «ROM final»). Desde v1.2.0 el panel tiene barra de"),
        ("", "   desplazamiento y rueda del ratón; si no la ves, baja con la rueda."),
        ("", "   La casilla «Módulo Shelly» viene MARCADA por defecto: no tienes"),
        ("", "   que tocar nada. La pastilla verde «Shelly lista ✓» arriba a la"),
        ("", "   derecha confirma que la carpeta fue detectada."),
        ("", "   Cómo activarla: coloca la carpeta 'Shelly-Module' junto a esta"),
        ("", "   app (o junto a los repos). La cadena la integra sola ANTES de"),
        ("", "   compilar; el inicial se compila DENTRO de la ROM (todo es"),
        ("", "   idempotente: puedes recompilar mil veces sin duplicar nada)."),
        ("", "   El instalador crea respaldos .shelly_backup/ dentro de cada repo"),
        ("", "   y también corrige el bug de Windows de 'python3 no se encontró'"),
        ("", "   en los make.py. Para desinstalar: python install_shelly.py --restore."),
        ("", "   (La versión v1.3.1 y anteriores usaban parche_inicial.py sobre la"),
        ("", "   ROM final; con v1.4 eso desapareció: todo va compilado dentro.)"),
        ("", ""),
        ("h2", "6) Problemas frecuentes"),
        ("err", "   * 'No se pudo copiar la ROM al DPE' ..."),
        ("", "       la app reintenta hasta 5 veces y te dice la causa exacta. Lo tipico:"),
        ("", "       - Elegiste como ROM el BPRE0.gba que ya esta dentro del DPE:"),
        ("", "         ahora se detecta y sigue sin problema (no hace falta copiar)."),
        ("", "       - El archivo esta abierto en un emulador/editor hexadecimal: cierralo."),
        ("", "       - La carpeta del repo esta en OneDrive/Drive o el antivirus bloquea"),
        ("", "         la escritura: pausa la sincronizacion o mueve los repos a C:\\RomHacking."),
        ("", "       - Destino en solo-lectura: la app lo quita sola antes de copiar."),
        ("", "       - Ruta demasiado larga: usa rutas cortas (Windows limita a 260)."),
        ("err", "   * 'make.py termino con codigo 1' ..."),
        ("", "       mira las lineas rojas de la consola: suelen ser rom no encontrada,"),
        ("", "       Python equivocado (usa 3.7.x para los originales) o devkitARM ausente."),
        ("err", "   * 'no se encontro Python ... Microsoft Store' ..."),
        ("", "       NO es tu Python: es el python.exe FALSO de la Tienda que Windows pone"),
        ("", "       en el PATH (alias de ejecucion de aplicaciones). La app ya aislara ese"),
        ("", "       alias durante la compilacion y forzara tu Python real; si vuelve a"),
        ("", "       aparecer, desactiva python/python3 en Configuracion > Aplicaciones >"),
        ("", "       Configuracion avanzada > Alias de ejecucion de aplicaciones."),
        ("err", "   * 'WinError 32: lo esta usando otro proceso' ..."),
        ("", "       otro programa tiene abierto el archivo (emulador con la ROM puesta,"),
        ("", "       OneDrive, antivirus). Cierralo: la app reintenta 5 veces con esperas"),
        ("", "       crecientes y, si ya dejaste la ROM a mano en el destino, sigue con esa"),
        ("", "       sin detener la cadena."),
        ("err", "   * 'libwinpthread-1.dll' no encontrada ..."),
        ("", "       descarga la version de 64 bits de esa DLL y ponla en la raiz del repo."),
        ("warn", "   * Muchos warnings al compilar un CFRU limpio ..."),
        ("warn", "       la guia oficial sugiere reemplazar la carpeta devkitPro por la del foro."),
        ("warn", "   * Los offsets se pisan ..."),
        ("warn", "       verifica que DPE y CFRU no usen el mismo offset, y que tampoco choquen"),
        ("warn", "       con datos de tu hack (usa 0x100000 de holgura entre ellos)."),
        ("warn", "   * El save de mi hack dejo de funcionar ..."),
        ("warn", "       normal: CFRU/DPE cambian la estructura de guardado; partida nueva."),
        ("err", "   * El juego abre con una PARTIDA YA CREADA y no me deja"),
        ("err", "     empezar de cero / poner mi nombre ..."),
        ("", "       es el .sav (guardado de batería) que tu emulador dejó de una"),
        ("", "       compilación ANTERIOR con el mismo nombre de ROM: el juego lo"),
        ("", "       carga como si fuera tuyo, sin Shelly y con datos incompatibles"),
        ("", "       que además pueden colgar el juego."),
        ("", "       SOLUCIÓN: borra o renombra el .sav que está junto a la ROM"),
        ("", "       (MiHack_CFRU.sav, test.sav...) y vuelve a abrir la ROM."),
        ("", "       Desde v1.2.2 el builder lo hace SOLO: separa los .sav/.sgm"),
        ("", "       viejos como .bak_ (quedan junto a la ROM por si los quieres)."),
        ("err", "   * El juego se congela al arrancar / al elegir mi primer"),
        ("err", "     Pokémon / al entrar a la casa del rival ..."),
        ("", "       era un bug REAL del antiguo parche de inicial v1.1 (cuando el"),
        ("", "       evento se inyectaba en la ROM compilada): entregaba a Shelly"),
        ("", "       en la casa del RIVAL, usaba comandos que cuelgan el motor al"),
        ("", "       cargar el mapa y un flag fuera de rango que corrompía el save."),
        ("", "       SOLUCIÓN: usa el módulo v1.4 (incluido aquí) y recompila la"),
        ("", "       cadena COMPLETA con el builder: el inicial ahora se compila"),
        ("", "       DENTRO de la ROM (src/shelly_module.c) y ese parche ya no"),
        ("", "       existe, así que esos cuelgues tampoco. Borra el .sav viejo."),
        ("err", "   * 'ESTE NO ES EL CUARTO DEL JUGADOR: abortando' al parchear ..."),
        ("", "       falso rechazo del antiguo parche v1.2 (warp leído con offsets"),
        ("", "       corridos): TU CUARTO SIEMPRE FUE EL CORRECTO. Ese mensaje ya"),
        ("", "       no puede volver a salir: desde el módulo v1.4 no existe ningún"),
        ("", "       parche tras compilar — el evento de llegada es código del CFRU"),
        ("", "       que se dispara solo en tu cuarto (grupo 4, mapa 1). Recompila"),
        ("", "       la cadena con el builder y listo."),
        ("err", "   * Mi ROM es FireRed 1.1 / española / de otra región ..."),
        ("", "       el CFRU SOLO funciona con FireRed US 1.0 (BPRE0, rev 0, byte"),
        ("", "       0xBC=00). Con la 1.1 o la española puede compilar y aun así"),
        ("", "       colgar el juego en cualquier momento. Consigue la 1.0 US."),
        ("", ""),
        ("h2", "7) Links utiles"),
        ("", "   CFRU original ...: github.com/Skeli789/Complete-Fire-Red-Upgrade"),
        ("", "   CFRU-expansion ..: github.com/Shiny-Miner/CFRU-expansion"),
        ("", "   DPE Gen 9 .......: github.com/Shiny-Miner/Dynamic-Pokemon-Expansion-Gen-9"),
        ("", "   Guia Windows ....: wiki de Skeli789 > Windows Installation Instructions"),
        ("", ""),
        ("muted", "   Esta app solo automatiza comandos publicos de esos repos; no distribuye ROMs."),
    ]

    def _fill_help(self):
        self.help_text.configure(state="normal")
        self.help_text.delete("1.0", "end")
        for tag, line in self.HELP_MD:
            if tag:
                self.help_text.insert("end", line + "\n", tag)
            else:
                self.help_text.insert("end", line + "\n")
        self.help_text.configure(state="disabled")

    # -------------------------------------------------------------- consola
    def _build_console(self):
        wrap = tk.Frame(self, bg=C_BG)
        wrap.grid(row=2, column=0, sticky="nsew", padx=14, pady=(2, 2))
        self.rowconfigure(2, weight=3)
        self.columnconfigure(0, weight=1)
        wrap.rowconfigure(1, weight=1)
        wrap.columnconfigure(0, weight=1)

        head = tk.Frame(wrap, bg=C_BG); head.grid(row=0, column=0, sticky="ew")
        tk.Label(head, text="CONSOLA EN VIVO", font=FONT_SMALL, bg=C_BG,
                 fg=C_MUTED).pack(side="left")
        tk.Button(head, text="Limpiar", command=self._clear_console, font=FONT_SMALL,
                  bg=C_PANEL, fg=C_MUTED, activebackground=C_PANEL2,
                  activeforeground=C_FG, relief="flat", bd=0, cursor="hand2",
                  padx=8).pack(side="right")

        self.console = ScrolledText(wrap, bg=C_INPUT, fg=C_FG, font=FONT_MONO,
                                    relief="flat", insertbackground=C_FG, borderwidth=0,
                                    padx=12, pady=10, state="disabled", wrap="char")
        self.console.grid(row=1, column=0, sticky="nsew")
        for tag, color in (("err", C_RED), ("warn", C_YELLOW), ("ok", C_GREEN),
                           ("info", C_BLUE), ("sys", C_MUTED), ("pause", C_PURPLE)):
            self.console.tag_configure(tag, foreground=color)
        self.console.tag_configure("err", font=("Consolas", 9, "bold"))
        self._sysline("Bienvenido a CFRU Builder. Configura el panel izquierdo y pulsa INICIAR CADENA.")

    def _sysline(self, msg):
        self._append_console("[CFRU Builder] " + msg, "sys")

    def _append_console(self, line, level):
        self.console.configure(state="normal")
        self.console.insert("end", line.rstrip("\r\n") + "\n", level or None)
        # limitar cantidad de lineas visibles
        if float(self.console.index("end-1c").split(".")[0]) > MAX_LOG_HISTORY:
            self.console.delete("1.0", "200.0")
        self.console.see("end")
        self.console.configure(state="disabled")

    def _clear_console(self):
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")

    # -------------------------------------------------------------- status bar
    def _build_statusbar(self):
        bar = tk.Frame(self, bg=C_PANEL, highlightthickness=1,
                       highlightbackground=C_BORDER)
        bar.grid(row=3, column=0, sticky="ew")
        bar.columnconfigure(0, weight=1)
        self.lbl_state = tk.Label(bar, text="Estado: en espera", font=FONT_SMALL,
                                  bg=C_PANEL, fg=C_MUTED, anchor="w", padx=10)
        self.lbl_state.pack(side="left", pady=3)
        tk.Label(bar, text="DPE → CFRU  ·  FireRed BPRE  ·  %s" % APP_VERSION,
                 font=FONT_SMALL, bg=C_PANEL, fg=C_MUTED, padx=10).pack(side="right")

    # ================================================== config <-> GUI
    def _gui_from_config(self):
        rom = self.cfg.get("rom_path")
        if rom:
            self.lbl_rom.config(text=os.path.basename(rom), fg=C_FG)
        dpe = self.cfg.get("dpe_dir")
        cfru = self.cfg.get("cfru_dir")
        if dpe:
            self.lbl_dpe.config(text=dpe, fg=C_FG)
        if cfru:
            self.lbl_cfru.config(text=cfru, fg=C_FG)
        self.ent_off_dpe.delete(0, "end")
        self.ent_off_dpe.insert(0, self.cfg.get("offset_dpe") or "")
        self.ent_off_cfru.delete(0, "end")
        self.ent_off_cfru.insert(0, self.cfg.get("offset_cfru") or "")
        name = self.cfg.get("out_name") or "MiHack_CFRU.gba"
        self.ent_out_name.delete(0, "end")
        self.ent_out_name.insert(0, name)
        outd = self.cfg.get("out_dir")
        self.lbl_out_dir.config(text=("Carpeta: " + outd) if outd else
                                "Carpeta: (la misma de la ROM)")
        self.var_auto_off.set(bool(self.cfg.get("auto_apply_offsets")))
        self.var_backup.set(bool(self.cfg.get("backup_enabled")))
        self.var_clean.set(bool(self.cfg.get("clean_before_update")))
        self.var_shelly.set(bool(self.cfg.get("shelly_activar")))
        self.var_sav.set(bool(self.cfg.get("higiene_sav")))
        self.ent_python.delete(0, "end")
        self.ent_python.insert(0, self.cfg.get("python_for_build") or "")
        self._refresh_repo_labels()

    def _collect_config(self):
        """Guarda en config.json todo lo visible en el panel izquierdo."""
        self.cfg.set("offset_dpe", self.ent_off_dpe.get().strip())
        self.cfg.set("offset_cfru", self.ent_off_cfru.get().strip())
        name = self.ent_out_name.get().strip() or "MiHack_CFRU.gba"
        self.cfg.set("out_name", name)
        self.cfg.set("python_for_build", self.ent_python.get().strip())
        self._save_options()
        self._refresh_checks()

    def _save_options(self):
        self.cfg.set("auto_apply_offsets", bool(self.var_auto_off.get()))
        self.cfg.set("backup_enabled", bool(self.var_backup.get()))
        self.cfg.set("clean_before_update", bool(self.var_clean.get()))
        self.cfg.set("shelly_activar", bool(self.var_shelly.get()))
        self.cfg.set("higiene_sav", bool(self.var_sav.get()))

    def _open_dir_of(self, key):
        p = self.cfg.get(key)
        if p and os.path.isdir(p):
            open_path(p)
        elif p and os.path.isfile(p):
            open_path(os.path.dirname(p))

    # ================================================== selectores
    def choose_rom(self):
        initial = os.path.dirname(self.cfg.get("rom_path") or "") or "/"
        path = filedialog.askopenfilename(
            title="Elige tu ROM de Pokemon FireRed (BPRE)",
            initialdir=initial,
            filetypes=[("ROM Game Boy Advance", "*.gba"), ("Todos los archivos", "*.*")])
        if not path:
            return
        self.cfg.set("rom_path", path)
        self.lbl_rom.config(text=os.path.basename(path), fg=C_FG)
        if not self.cfg.get("out_dir"):
            self.lbl_out_dir.config(text="Carpeta: " + os.path.dirname(path))
        self._refresh_checks()

    def _pick_folder(self, title, key):
        initial = self.cfg.get(key) or "/"
        path = filedialog.askdirectory(title=title, initialdir=initial)
        if not path:
            return None
        self.cfg.set(key, path)
        return path

    def choose_dpe(self):
        path = self._pick_folder("Elige la carpeta del DPE (Dynamic Pokemon Expansion)", "dpe_dir")
        if path:
            self.lbl_dpe.config(text=path, fg=C_FG)
            info = RepoInspector.inspect(path)
            if info.current_offset is not None:
                self.ent_off_dpe.delete(0, "end")
                self.ent_off_dpe.insert(0, "0x%X" % info.current_offset)
                self._sysline("Offset actual del DPE detectado: 0x%X" % info.current_offset)
            self._refresh_checks()

    def choose_cfru(self):
        path = self._pick_folder("Elige la carpeta del CFRU (Complete Fire Red Upgrade)", "cfru_dir")
        if path:
            self.lbl_cfru.config(text=path, fg=C_FG)
            info = RepoInspector.inspect(path)
            if info.current_offset is not None:
                self.ent_off_cfru.delete(0, "end")
                self.ent_off_cfru.insert(0, "0x%X" % info.current_offset)
                self._sysline("Offset actual del CFRU detectado: 0x%X" % info.current_offset)
            self._refresh_checks()

    def choose_out_dir(self):
        path = self._pick_folder("Carpeta donde guardar la ROM final", "out_dir")
        if path:
            self.lbl_out_dir.config(text="Carpeta: " + path)

    def choose_python(self):
        current = self.ent_python.get().strip() or default_python_for_build()
        path = filedialog.askopenfilename(
            title="Elige python.exe que usaran los make.py (recomendado 3.7.6)",
            initialdir=os.path.dirname(current),
            filetypes=[("Ejecutable de Python", "python.exe"), ("Todos", "*.*")])
        if path:
            self.ent_python.delete(0, "end")
            self.ent_python.insert(0, path)

    # ================================================== pre-checks
    def _refresh_repo_labels(self):
        dpe = RepoInspector.inspect(self.cfg.get("dpe_dir"))
        cfru = RepoInspector.inspect(self.cfg.get("cfru_dir"))
        self.lbl_dpe_badge.config(
            text=("Detectado: " + dpe.label) if dpe.has_make else
                  (dpe.error or "Sin carpeta valida"),
            fg=C_BLUE if dpe.has_make else C_MUTED)
        self.lbl_cfru_badge.config(
            text=("Detectado: " + cfru.label) if cfru.has_make else
                  (cfru.error or "Sin carpeta valida"),
            fg=C_RED if cfru.has_make else C_MUTED)
        self.dpe_info = dpe
        self.cfru_info = cfru

    def _refresh_checks(self):
        self._refresh_repo_labels()
        # pastilla módulo Shelly (v1.2.0): verde si detecta la carpeta
        mod = ""
        try:
            mod = self.engine._shelly_dir()
        except Exception:
            pass
        if mod and self.cfg.get("shelly_activar"):
            self.pill_shelly.config(text="Shelly lista ✓", fg=C_GREEN)
        elif mod:
            self.pill_shelly.config(text="Shelly: casilla desactivada", fg=C_YELLOW)
        else:
            self.pill_shelly.config(text="Shelly: sin módulo", fg=C_MUTED)
        # pastilla python: el que USARAN los make.py (vacio = el de la app);
        # se salta el alias falso de la Microsoft Store y avisa si no responde
        py = clean_path(self.cfg.get("python_for_build")) or default_python_for_build()
        if is_store_stub_path(py):
            self.pill_python.config(text="Python: alias de la Tienda!", fg=C_RED)
        else:
            okp, verp = probe_python(py)
            if okp:
                self.pill_python.config(text="Python %s" % verp, fg=C_GREEN)
            else:
                self.pill_python.config(text="Python no responde", fg=C_YELLOW)
        # pastilla devkitARM
        src, loc = find_devkitarm()
        if loc:
            via = "" if src == "PATH" else " via %s" % src
            self.pill_devkit.config(text="devkitARM OK%s" % via, fg=C_GREEN)
        else:
            self.pill_devkit.config(text="devkitARM no detectado", fg=C_YELLOW)
        # pastilla ROM
        rom = self.cfg.get("rom_path")
        if rom and os.path.isfile(rom):
            ok, code, size, msg = valid_rom_header(rom)
            txt = "%s · %s" % (os.path.basename(rom), fmt_size(size))
            if ok:
                self.pill_rom.config(text=txt + " · BPRE", fg=C_GREEN)
                self.lbl_rom_info.config(text=msg, fg=C_MUTED)
            else:
                self.pill_rom.config(text=txt + " · NO es BPRE", fg=C_RED)
                self.lbl_rom_info.config(text=msg, fg=C_YELLOW)
        else:
            self.pill_rom.config(text="Sin ROM", fg=C_MUTED)
            self.lbl_rom_info.config(text="")
        # estado de offsets
        o1 = normalize_hex(self.ent_off_dpe.get())
        o2 = normalize_hex(self.ent_off_cfru.get())
        txts = []
        if o1 is not None and self.dpe_info and self.dpe_info.current_offset is not None:
            txts.append("make.py DPE tiene ahora 0x%X (GUI: 0x%X)" %
                        (self.dpe_info.current_offset, o1))
        if o2 is not None and self.cfru_info and self.cfru_info.current_offset is not None:
            txts.append("make.py CFRU tiene ahora 0x%X (GUI: 0x%X)" %
                        (self.cfru_info.current_offset, o2))
        if o1 is not None and o2 is not None and o1 == o2:
            self.lbl_offset_state.config(fg=C_RED,
                text="ADVERTENCIA: ambos offsets son IGUALES; deben ser distintos.")
        else:
            if o1 is not None and o2 is not None:
                self.lbl_offset_state.config(fg=C_MUTED, text="\n".join(txts) or
                    ("DPE 0x%X / CFRU 0x%X" % (o1, o2)))
            else:
                self.lbl_offset_state.config(fg=C_MUTED, text="\n".join(txts))
        # aviso de carpetas intercambiadas
        if getattr(self, "dpe_info", None) and getattr(self, "cfru_info", None):
            if self.dpe_info.has_make and self.cfru_info.has_make:
                if self.dpe_info.kind == "cfru" and self.cfru_info.kind == "dpe":
                    self._sysline("Aviso: parece que las carpetas DPE y CFRU estan intercambiadas.")

    def apply_offsets_now(self):
        self._collect_config()
        o1 = normalize_hex(self.ent_off_dpe.get())
        o2 = normalize_hex(self.ent_off_cfru.get())
        if o1 is None or o2 is None:
            messagebox.showerror("Offsets invalidos",
                "Escribe los offsets en formato hex, ej. 0x750000 y 0x900000.")
            return
        if o1 == o2:
            messagebox.showerror("Offsets iguales",
                "El DPE y el CFRU no pueden insertarse en el mismo offset (0x%X)." % o1)
            return
        results = []
        ok_any = False
        for label, key, mp_key in (("DPE", o1, "dpe_dir"), ("CFRU", o2, "cfru_dir")):
            d = self.cfg.get(mp_key)
            mp = os.path.join(d, "scripts", "make.py") if d else ""
            ok, msg = (False, "Carpeta no configurada") if not mp else \
                RepoInspector.write_offset(mp, o1 if label == "DPE" else o2)
            results.append("%s: %s" % (label, msg))
            ok_any = ok_any or ok
        self._sysline("Aplicar offsets -> " + " | ".join(results))
        self._refresh_checks()
        (messagebox.showinfo if ok_any else messagebox.showerror)(
            "Offsets", "\n".join(results))

    # ================================================== acciones
    def _set_run_buttons(self, idle=True, paused=False):
        st = "normal" if idle else "disabled"
        self.btn_start.config(state=st)
        self.btn_upd_dpe.config(state=st)
        self.btn_upd_cfru.config(state=st)
        self.btn_continue.config(state="normal" if paused else "disabled")
        self.btn_cancel.config(state="disabled" if idle else "normal")

    def _confirm_devkit(self):
        src, loc = find_devkitarm()
        if not src:
            return messagebox.askyesno(
                "devkitARM no detectado",
                "No encuentro devkitARM en ningun sitio: ni en el PATH, ni en las\n"
                "variables DEVKITARM/DEVKITPRO, ni en el registro de Windows, ni en\n"
                "las rutas tipicas (C:\\devkitPro\\devkitARM\\bin, etc.).\n\n"
                "Sin devkitPro los make.py no podran compilar el codigo.\n\n"
                "Si acabas de instalarlo, cierra y vuelve a abrir la app.\n\n"
                "Quieres continuar de todos modos?")
        return True

    def start_chain(self):
        if self.engine.busy:
            messagebox.showwarning("Ocupado", "Ya hay una compilacion en curso.")
            return
        self._collect_config()
        rom = self.cfg.get("rom_path")
        if not rom or not os.path.isfile(rom):
            messagebox.showerror("Falta la ROM", "Elige tu ROM FireRed (BPRE) primero.")
            return
        dpe = self.cfg.get("dpe_dir")
        cfru = self.cfg.get("cfru_dir")
        if not (dpe and RepoInspector.inspect(dpe).has_make):
            messagebox.showerror("Falta el DPE", "Selecciona la carpeta del DPE primero.")
            return
        if not (cfru and RepoInspector.inspect(cfru).has_make):
            messagebox.showerror("Falta el CFRU", "Selecciona la carpeta del CFRU primero.")
            return
        if not self._confirm_devkit():
            return
        self._reset_pipeline()
        self.nb.select(self.tab_build)
        self._set_run_buttons(idle=False)
        self._sysline("Iniciando cadena completa DPE -> CFRU...")
        self.engine.full_chain()

    def continue_chain(self):
        if not self.engine.continue_after_pause():
            messagebox.showinfo("Nada que continuar",
                               "La pausa solo aparece tras compilar el DPE en la cadena completa.")

    def cancel_chain(self):
        if self.engine.busy:
            self.engine.cancel()
            self._sysline("Cancelando...")

    def update_dpe(self):
        if self.engine.busy:
            messagebox.showwarning("Ocupado", "Ya hay una compilacion en curso.")
            return
        self._collect_config()
        if not (self.cfg.get("dpe_dir") and RepoInspector.inspect(self.cfg.get("dpe_dir")).has_make):
            messagebox.showerror("Falta el DPE", "Selecciona la carpeta del DPE primero.")
            return
        if not self._confirm_devkit():
            return
        self._sysline("Modo actualizacion: reinstalando SOLO el DPE...")
        self._set_run_buttons(idle=False)
        self.engine.update_dpe()

    def update_cfru(self):
        if self.engine.busy:
            messagebox.showwarning("Ocupado", "Ya hay una compilacion en curso.")
            return
        self._collect_config()
        if not (self.cfg.get("cfru_dir") and RepoInspector.inspect(self.cfg.get("cfru_dir")).has_make):
            messagebox.showerror("Falta el CFRU", "Selecciona la carpeta del CFRU primero.")
            return
        if not self._confirm_devkit():
            return
        self._sysline("Modo actualizacion: reinstalando SOLO el CFRU...")
        self._set_run_buttons(idle=False)
        self.engine.update_cfru()

    # ================================================== pipeline
    def _reset_pipeline(self):
        for i, (ico, lbl) in enumerate(self.pipeline_rows):
            ico.config(text="○", fg=C_MUTED)
            lbl.config(fg=C_MUTED)

    def _on_step(self, i, st):
        if not (0 <= i < len(self.pipeline_rows)):
            return
        ico, lbl = self.pipeline_rows[i]
        styles = {
            "pending": ("○", C_MUTED),
            "current": ("▶", C_YELLOW),
            "done":    ("✔", C_GREEN),
            "fail":    ("✘", C_RED),
            "pause":   ("⏸", C_PURPLE),
        }
        icon, color = styles.get(st, ("○", C_MUTED))
        ico.config(text=icon, fg=color)
        lbl.config(fg=color if st != "pending" else C_MUTED)

    # ================================================== bomba de eventos
    def _pump_events(self):
        try:
            while True:
                ev = self.evq.get_nowait()
                t = ev.get("t")
                if t == "log":
                    self._append_console(ev["line"], ev.get("level", ""))
                elif t == "step":
                    self._on_step(ev["i"], ev["state"])
                elif t == "state":
                    msg = ev.get("msg", "")
                    color = {"running": C_BLUE, "paused": C_PURPLE,
                             "done": C_GREEN, "error": C_RED,
                             "cancelled": C_YELLOW, "idle": C_MUTED}.get(ev["state"], C_MUTED)
                    self.lbl_state.config(text="Estado: " + (msg or ev["state"]), fg=color)
                    if ev["state"] == "paused":
                        self._set_run_buttons(idle=False, paused=True)
                        self.nb.select(self.tab_build)
                elif t == "finished":
                    ok = ev.get("success")
                    self._set_run_buttons(idle=True)
                    if ok:
                        self._sysline("COMPLETADO: " + ev.get("summary", ""))
                    else:
                        self._sysline("TERMINO CON ERRORES: " + ev.get("summary", ""))
                    self._load_history()
                    if ev.get("rom_out"):
                        self._sysline("ROM final: " + ev["rom_out"])
        except queue.Empty:
            pass
        self.after(80, self._pump_events)

    # ================================================== historial
    def _load_history(self):
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        for e in self.history.entries():
            tag = "ok" if e.get("success") else "bad"
            self.tree.insert("", "end", iid=str(e.get("ts", "")) + str(e.get("log", "")),
                             tags=(tag,), values=(
                e.get("ts", "?"),
                e.get("mode", "?"),
                "%ss" % e.get("duration_s", "?"),
                "OK" if e.get("success") else "FALLO",
                (e.get("summary") or "")[:200]))

    def view_history_log(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Historial", "Selecciona una entrada del historial.")
            return
        vals = self.tree.item(sel[0], "values")
        log_name = None
        # buscar la entrada correspondiente por fecha
        for e in self.history.entries():
            if e.get("ts") == vals[0]:
                log_name = e.get("log")
                break
        if not log_name:
            messagebox.showwarning("Log", "No encontre el archivo de log de esa entrada.")
            return
        path = os.path.join(self.history.logs_dir, log_name)
        if not os.path.isfile(path):
            messagebox.showwarning("Log", "El archivo %s ya no existe." % path)
            return
        win = tk.Toplevel(self)
        win.title("Log: " + log_name)
        win.geometry("900x600")
        win.configure(bg=C_INPUT)
        txt = ScrolledText(win, bg=C_INPUT, fg=C_FG, font=FONT_MONO,
                           relief="flat", insertbackground=C_FG, padx=12, pady=10)
        txt.pack(fill="both", expand=True)
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            txt.insert("1.0", f.read())
        txt.tag_configure("err", foreground=C_RED)
        txt.tag_configure("ok", foreground=C_GREEN)
        txt.tag_configure("warn", foreground=C_YELLOW)

    def clear_history(self):
        if messagebox.askyesno("Borrar historial",
                                "Se borrara el registro de compilaciones (los archivos de log no se borran). Continuar?"):
            self.history.clear()
            self._load_history()

    # ================================================== cierre
    def _on_close(self):
        try:
            self.cfg.set("geometry", self.geometry())
        except Exception:
            pass
        if self.engine.busy:
            if not messagebox.askyesno(
                    "Compilacion en curso",
                    "Hay una compilacion en curso. Si cierras se cancelara. Salir?"):
                return
            self.engine.cancel()
        self.destroy()


# ---------------------------------------------------------------------------
# Entrada principal
# ---------------------------------------------------------------------------
def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
