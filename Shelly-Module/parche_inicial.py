#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
════════════════════════════════════════════════════════════════════════
  Módulo Shelly — Parche de Inicial v1.2.1 (ROM final)
════════════════════════════════════════════════════════════════════════
  Agrega a Shelly (nv. 5) al equipo NADA MÁS arrancar la partida, en tu
  cuarto (Casa del Jugador 2F, Pallet), con fanfare y mensaje en español.

  Correcciones v1.2/v1.2.1 (bugs de la v1.1 en juego + bug de PC):
   1. MAPA EQUIVOCADO: la v1.1 parcheaba el mapa 4.2 (¡la CASA del RIVAL!)
      porque el cuarto del jugador es el mapa 4.1. Por eso Shelly nunca
      llegaba al arrancar. Ahora se apunta al 4.1 y se VALIDA su identidad
      por el warp (la escalera baja al 1F del jugador: grupo 4, mapa 0).
   2. CUELLE IRREVERSIBLE: la v1.1 usaba un level script kind 1 (ON_LOAD),
      que el motor ejecuta con RunScriptImmediately (bucle cerrado, sin
      bucle principal). Los comandos waitmsg/waitfanfare/closeonkeypress
      dependen del bucle principal -> bucle infinito -> juego congelado.
      Ahora se usa kind 2 (ON_FRAME_TABLE), que corre en el contexto
      GLOBAL y soporta mensajes sin colgar (mismo mecanismo vanilla de
      las escenas de Oak en Pallet).
   3. FLAG FUERA DE RANGO: la v1.1 usaba el flag 0x10F0, pero FireRed
      solo tiene 0x900 bits de flags (hasta 0x8FF): setflag 0x10F0
      escribía EN la variable 0x407F (¡la escena del Mt. Ember!) y la
      corrompía. Ahora se usa el flag 0x2AE (marcado UNUSED por el
      decomp) y el código RECHAZA cualquier flag >= 0x900, que
      escribiría memoria ajena al array.
   4. Charmap: 'á' era 0x16 (= 'à'); el charmap real de FireRed es 0x17.
   5. OFF-BY-ONE EN EL WARP (v1.2.1): el WarpEvent REAL de FireRed es
      {x, y, elevation, warpId, mapNum, mapGroup} (decomp: global.fieldmap.h):
      mapNum vive en +6 y mapGroup en +7. La v1.2 leía +5/+6 — o sea el
      warpId y el byte de mapNum — y por eso RECHAZABA tu cuarto legítimo
      con "warp 0 apunta a (grupo 0, mapa 2)" (= warpId 2 + mapNum 0
      REALES de la ROM). El mapa 4.1 SIEMPRE fue el correcto; fallaba el
      lector, no el mapa. Corregido y verificado campo a campo contra el
      decomp oficial (struct MapEvents / WarpEvent / MapHeader).

  Cómo funciona (v1.2.1):
   - Localiza el map header del cuarto del jugador (banco 4, mapa 1)
     navegando la tabla de bancos en 0x3526A8, con validación
     estructural: música MUS_PALLET=300, tipo INDOOR=8, y el warp 0
     apuntando a (grupo 4, mapa 0) — el 1F de TU casa. La casa del
     rival también tiene música Pallet: el warp es lo que los
     distingue.
   - Construye una tabla de level scripts NUEVA que conserva los dos
     scripts vanilla del cuarto (kind 3 = respawn al dormir, kind 4 =
     primer warp-in que te voltea al norte) y añade:
       kind 2 (ON_FRAME_TABLE) -> tabla secundaria {var 0x4090, 0, ptr}
     que dispara UNA VEZ (la var se consume con setvar 1 dentro del
     propio script) el primer frame de juego en tu cuarto.
   - El script corre en contexto global (seguro para mensajes):
       setvar 0x4090=1 (consume el disparador ya),
       checkflag 0x2AE -> si está, end (una sola vez por partida),
       setflag 0x2AE, givepokemon SHELLY(0x5D1) nv.5,
       lockall, fanfare MUS_OBTAIN_ITEM, preparemsg, waitmsg,
       waitfanfare, waitbuttonpress (cierras el cartel con A/B),
       closemessage, releaseall, end.

  Uso:
   python parche_inicial.py <ROM_final.gba> [opciones]
   --dry-run      solo muestra el plan, no escribe
   --sin-mensaje  entrega silenciosa (sin texto ni fanfare)
   --flag 0x2AE   flag de control (rango duro 0x01-0x8FF, no tocar)
   --var  0x4090   var disparadora (rango 0x4000-0x7FFF)
════════════════════════════════════════════════════════════════════════
"""
import argparse
import os
import shutil
import struct
import sys
import time

# ─────────────────────────── constantes del parche ───────────────────────
BANK_TABLE = 0x3526A8          # tabla de bancos de mapas (BPRE)
PALLET_BANK = 4                # gMapGroup_IndoorPallet
PALLET_MAP = 1                 # 4.1 = PlayersHouse_2F (¡el CUARTO!)
MAPSEC_MUSIC_PALLET = 300     # MUS_PALLET (validación)
MAP_TYPE_INDOOR = 8           # validación
SPECIES_SHELLY = 0x5D1        # 1489
NIVEL_SHELLY = 5
FLAG_CONTROL = 0x2AE          # UNUSED en vanilla (banda 0x2AA-0x2AE)
VAR_DISPARO = 0x4090          # sin uso en vanilla, fuera del quest-log
FANFARE_OBTAIN = 0x102        # MUS_OBTAIN_ITEM (258)
ROM_MAX = 0x2000000           # 32 MB
FLAG_MIN, FLAG_MAX = 0x01, 0x900  # límites del array de flags (duro)

MENSAJE = "¡Recibiste a SHELLY!\n¡Tu aventura comienza!"

# charmap FireRed (verificado contra charmap.txt del decomp pokefirered)
CHARMAP = {
    ' ': 0x00, 'A': 0xBB, 'B': 0xBC, 'C': 0xBD, 'D': 0xBE, 'E': 0xBF,
    'F': 0xC0, 'G': 0xC1, 'H': 0xC2, 'I': 0xC3, 'J': 0xC4, 'K': 0xC5,
    'L': 0xC6, 'M': 0xC7, 'N': 0xC8, 'O': 0xC9, 'P': 0xCA, 'Q': 0xCB,
    'R': 0xCC, 'S': 0xCD, 'T': 0xCE, 'U': 0xCF, 'V': 0xD0, 'W': 0xD1,
    'X': 0xD2, 'Y': 0xD3, 'Z': 0xD4, 'a': 0xD5, 'b': 0xD6, 'c': 0xD7,
    'd': 0xD8, 'e': 0xD9, 'f': 0xDA, 'g': 0xDB, 'h': 0xDC, 'i': 0xDD,
    'j': 0xDE, 'k': 0xDF, 'l': 0xE0, 'm': 0xE1, 'n': 0xE2, 'o': 0xE3,
    'p': 0xE4, 'q': 0xE5, 'r': 0xE6, 's': 0xE7, 't': 0xE8, 'u': 0xE9,
    'v': 0xEA, 'w': 0xEB, 'x': 0xEC, 'y': 0xED, 'z': 0xEE,
    '0': 0xA1, '1': 0xA2, '2': 0xA3, '3': 0xA4, '4': 0xA5, '5': 0xA6,
    '6': 0xA7, '7': 0xA8, '8': 0xA9, '9': 0xAA, '!': 0xAB, '?': 0xAC,
    '.': 0xAD, '-': 0xAE, ',': 0xB8, ':': 0xF0, '¡': 0x52, '¿': 0x51,
    'á': 0x17, 'é': 0x1B, 'í': 0x6F, 'ó': 0x23, 'ú': 0x27, 'ñ': 0x29,
    'Á': 0x02, 'É': 0x06, 'Í': 0x5A, 'Ó': 0x0E, 'Ú': 0x12, 'Ñ': 0x14,
    '\n': 0xFE, '♂': 0xB5, '♀': 0xB6,
}

# comandos de script FireRed (verificados contra el engine del decomp)
CMD_END = b'\x02'
CMD_GOTO = b'\x05'             # + u32 destino
CMD_IF_GOTO = b'\x06'          # + byte condición + u32 destino (0x01 = igual)
CMD_SETVAR = b'\x16'           # + u16 var + u16 valor
CMD_SETFLAG = b'\x29'          # + u16
CMD_CHECKFLAG = b'\x2B'        # + u16
CMD_FANFARE = b'\x31'          # + u16
CMD_WAITFANFARE = b'\x32'
CMD_WAITMSG = b'\x66'
CMD_PREPAREMSG = b'\x67'       # + u32 puntero
CMD_CLOSEONKEYPRESS = b'\x68'   # closemessage (decomp): oculta el cartel
CMD_WAITBUTTONPRESS = b'\x6D'   # waitbuttonpress: espera A/B antes de cerrar
CMD_LOCKALL = b'\x69'
CMD_RELEASEALL = b'\x6B'
CMD_GIVEPOKEMON = b'\x79'      # + u16 especie + u8 nivel + u16 item
                               #   + u32 + u32 + u8  (layout verificado)


class C:
    OK = "\033[92m[OK]\033[0m"
    INFO = "\033[96m[INFO]\033[0m"
    WARN = "\033[93m[AVISO]\033[0m"
    ERR = "\033[91m[ERROR]\033[0m"


def log(k, m):
    print(f"{k} {m}")


def rom_ptr_le(off):
    return struct.pack('<I', 0x08000000 + off)


class Parchador:
    def __init__(self, ruta, dry=False, con_mensaje=True,
                 flag=FLAG_CONTROL, var=VAR_DISPARO):
        self.ruta = ruta
        self.dry = dry
        self.con_mensaje = con_mensaje
        self.flag = flag
        self.var = var
        self.rom = None
        self.ya_aplicado = False
        self.viejo_parche = []

    # ------------------------------------------------------------- lecturas
    def u8(self, off):
        return self.rom[off]

    def u16(self, off):
        return struct.unpack_from('<H', self.rom, off)[0]

    def u32(self, off):
        return struct.unpack_from('<I', self.rom, off)[0]

    def puntero_rom(self, off):
        """Lee un puntero; devuelve offset en ROM o None si no es válido."""
        v = self.u32(off)
        if 0x08000000 <= v < 0x08000000 + ROM_MAX:
            return v - 0x08000000
        return None

    # ------------------------------------------------------------ validación
    def validar_rom(self):
        if not os.path.isfile(self.ruta):
            log(C.ERR, f"No existe: {self.ruta}")
            return False
        with open(self.ruta, 'rb') as f:
            self.rom = bytearray(f.read())
        log(C.INFO, f"ROM: {self.ruta} ({len(self.rom)/1024/1024:.1f} MB)")
        if len(self.rom) > ROM_MAX:
            log(C.ERR, "La ROM supera los 32 MB.")
            return False
        if self.rom[0xAC:0xB0] != b'BPRE':
            log(C.WARN, f"El código interno no es BPRE "
                        f"({self.rom[0xAC:0xB0]!r}); FireRed en inglés esperado.")
        rev = self.u8(0xBC)  # byte de versión: 0x00 = FireRed 1.0 (rev 0)
        if rev != 0:
            log(C.WARN, f"La ROM parece FireRed rev {rev}. El CFRU oficial "
                        "requiere FireRed US 1.0 (rev 0, byte 0xBC=00). "
                        "Si el juego se congela en cualquier momento, "
                        "conseguí la versión 1.0.")
        else:
            log(C.OK, "FireRed 1.0 (rev 0) — la requerida por el CFRU.")
        return True

    def _header_mapa(self, banco, mapa):
        """Devuelve el offset del header (banco, mapa) o None."""
        arr = self.puntero_rom(BANK_TABLE + banco * 4)
        if arr is None:
            return None
        return self.puntero_rom(arr + mapa * 4)

    def localizar_header(self):
        """Navega banco 4 → mapa 1 → header, con validaciones duras."""
        for i in (0, 1, 2, 3, 4):
            if self.puntero_rom(BANK_TABLE + i * 4) is None:
                log(C.ERR, f"0x{BANK_TABLE:X} no parece la tabla de bancos "
                           "(puntero inválido).")
                return None
        header = self._header_mapa(PALLET_BANK, PALLET_MAP)
        if header is None:
            log(C.ERR, "No se pudo leer el header del mapa 4.1.")
            return None
        log(C.OK, f"Header del mapa 4.{PALLET_MAP} @ 0x{header:07X}")

        musica = self.u16(header + 0x10)
        tipo = self.u8(header + 0x17)
        if musica != MAPSEC_MUSIC_PALLET:
            log(C.ERR, f"La música del mapa no es MUS_PALLET ({musica}). "
                       "¿No es una casa de Pallet?")
            return None
        if tipo != MAP_TYPE_INDOOR:
            log(C.ERR, f"El tipo de mapa no es INDOOR ({tipo}).")
            return None
        log(C.OK, f"Música {musica} + tipo {tipo} OK")

        # ── validación de IDENTIDAD por el warp (lo que distingue tu casa
        #    de la del rival): el cuarto tiene 1 solo warp y baja al 1F
        #    del JUGADOR (grupo 4, mapa 0). La casa del rival warpea a
        #    Pallet (grupo 3, mapa 0).
        eventos = self.puntero_rom(header + 0x04)
        if eventos is None:
            log(C.ERR, "El header no tiene un puntero de eventos válido.")
            return None
        num_warps = self.u8(eventos + 1)          # MapEvents.warpCount
        warps = self.puntero_rom(eventos + 8)     # MapEvents.warps
        if num_warps != 1 or warps is None:
            log(C.ERR, f"El mapa 4.{PALLET_MAP} tiene {num_warps} warps; el "
                       "cuarto del jugador debe tener exactamente 1 (la "
                       "escalera). ¿No será la casa del rival?")
            return None
        # struct WarpEvent REAL (decomp global.fieldmap.h):
        #   s16 x, y; u8 elevation; u8 warpId; u8 mapNum; u8 mapGroup
        wwarpid = self.u8(warps + 5)              # warpId   (+0x05)
        wmapnum = self.u8(warps + 6)             # mapNum   (+0x06) ← v1.2.1
        wmapgroup = self.u8(warps + 7)            # mapGroup (+0x07) ← v1.2.1
        if (wmapgroup, wmapnum) != (PALLET_BANK, 0):
            log(C.ERR, f"El warp 0 (escalera) apunta a (grupo {wmapgroup}, "
                       f"mapa {wmapnum}, warp {wwarpid}); el cuarto del "
                       "jugador debe apuntar a (grupo 4, mapa 0) = tu 1F. "
                       "ESTE NO ES EL CUARTO DEL JUGADOR: abortando para no "
                       "parchear el mapa equivocado (bug de la v1.1).")
            return None
        log(C.OK, f"Identidad confirmada: 1 warp -> (grupo {wmapgroup}, "
                  f"mapa {wmapnum}, warp {wwarpid}) = tu 1F. Es el CUARTO "
                  "del jugador.")
        return header

    def _analizar_tabla(self, header):
        """Lee la tabla de level scripts de un header. Devuelve (tabla, entradas)."""
        off_ptr = header + 0x08
        tabla = self.puntero_rom(off_ptr)
        if tabla is None:
            return None, []
        entradas = []
        p = tabla
        for _ in range(16):
            kind = self.u8(p)
            if kind == 0:
                break
            ptr = self.puntero_rom(p + 1)
            if ptr is None:
                log(C.ERR, f"Entrada de level script corrupta en 0x{p:07X}")
                return None, None
            entradas.append((kind, ptr))
            p += 5
        return tabla, entradas

    def _buscar_parche_viejo(self):
        """Busca el parche v1.1 roto (kind 1 + checkflag 0x10F0) en los
        mapas 4.1 y 4.2. Si existe, la ROM congela al entrar a esa casa."""
        for mapa in (1, 2):
            header = self._header_mapa(PALLET_BANK, mapa)
            if header is None:
                continue
            _, entradas = self._analizar_tabla(header)
            if not entradas:
                continue
            for kind, ptr in entradas:
                if kind == 1 and self.rom[ptr:ptr + 3] == b'\x2B\xF0\x10':
                    donde = "4.1 (tu cuarto)" if mapa == 1 else \
                            "4.2 (¡la casa del RIVAL!)"
                    self.viejo_parche.append(donde)
        return self.viejo_parche

    def leer_tabla_scripts(self, header):
        """Lee la tabla actual del cuarto y detecta parches previos."""
        tabla, entradas = self._analizar_tabla(header)
        if tabla is None and entradas is None:
            return None, None
        if entradas:
            log(C.OK, f"Tabla vanilla del cuarto @ 0x{tabla:07X}: "
                      + ", ".join(f"kind {k}" for k, _ in entradas))
        else:
            log(C.INFO, "El cuarto no tiene level scripts; se creará la tabla.")
        # parche v1.1/v1.1 roto: FATAL, hay que recompilar
        if self._buscar_parche_viejo():
            for donde in self.viejo_parche:
                log(C.ERR, f"Detectado el parche de inicial v1.1 (ROTO) en el "
                           f"mapa {donde}: congela el juego y corrompe la "
                           "variable del Mt. Ember.")
            log(C.ERR, "Esta ROM hay que RECOMPILARLA desde el builder con el "
                       "módulo v1.3+ (una ROM ya parcheada con v1.1 no se "
                       "puede reparar en sitio de forma segura).")
            return None, None
        # ¿ya está aplicado el parche v1.2? (kind 2 con nuestra tabla secundaria
        # cuyo script empieza por setvar var,1 y luego checkflag flag)
        for kind, ptr in entradas:
            if kind == 2:
                v1 = self.u16(ptr)
                v2 = self.u16(ptr + 2)
                scr = self.puntero_rom(ptr + 4)
                if v1 == self.var and v2 == 0 and scr is not None:
                    sig_ini = bytes(CMD_SETVAR) + \
                        struct.pack('<H', self.var) + b'\x01\x00'
                    sig_flag = bytes(CMD_CHECKFLAG) + \
                        struct.pack('<H', self.flag)
                    gp = bytes(CMD_GIVEPOKEMON) + \
                        struct.pack('<H', SPECIES_SHELLY)
                    if self.rom[scr:scr + 5] == sig_ini and \
                       sig_flag in bytes(self.rom[scr:scr + 12]) and \
                       gp in bytes(self.rom[scr:scr + 40]):
                        log(C.OK, "El parche v1.2 de Shelly YA está aplicado. "
                                  "Nada que hacer.")
                        self.ya_aplicado = True
                        break
        return tabla, entradas

    # ------------------------------------------------------------ construcción
    def codificar_texto(self, texto):
        out = bytearray()
        for ch in texto:
            if ch not in CHARMAP:
                log(C.ERR, f"Carácter sin charmap: {ch!r}")
                return None
            out.append(CHARMAP[ch])
        out.append(0xFF)  # terminador de texto
        return bytes(out)

    def construir_script(self, dir_script, dir_texto):
        """Bytes del script de entrega (dos pasadas para los punteros)."""
        def construir(ptr_fin, ptr_texto):
            b = bytearray()
            # 1. consumir el disparador YA (evita re-disparo por frame)
            b += CMD_SETVAR + struct.pack('<H', self.var) + \
                struct.pack('<H', 1)
            # 2. una sola vez por partida
            b += CMD_CHECKFLAG + struct.pack('<H', self.flag)
            b += CMD_IF_GOTO + b'\x01' + struct.pack('<I', ptr_fin)
            b += CMD_SETFLAG + struct.pack('<H', self.flag)
            # 3. la entrega (síncrona y segura en cualquier contexto)
            b += CMD_GIVEPOKEMON + struct.pack('<H', SPECIES_SHELLY) + \
                 bytes([NIVEL_SHELLY]) + struct.pack('<H', 0) + \
                 struct.pack('<I', 0) + struct.pack('<I', 0) + b'\x00'
            # 4. la fanfarria + mensaje (SOLO contexto global: el frame
            #    script garantiza que nunca corramos en RunScriptImmediately)
            if self.con_mensaje:
                b += CMD_LOCKALL
                b += CMD_FANFARE + struct.pack('<H', FANFARE_OBTAIN)
                b += CMD_PREPAREMSG + struct.pack('<I', ptr_texto)
                b += CMD_WAITMSG
                b += CMD_WAITFANFARE
                b += CMD_WAITBUTTONPRESS   # tú cierras el cartel con A/B
                b += CMD_CLOSEONKEYPRESS
                b += CMD_RELEASEALL
            b += CMD_END          # <- el salto del "if" cae AQUÍ
            return b
        dummy = construir(0x08000000, 0x08000000)
        fin = 0x08000000 + dir_script + len(dummy) - 1   # pos del END
        return construir(fin, 0x08000000 + dir_texto)

    def construir_secundaria(self, dir_script):
        """Tabla de verificación ON_FRAME: {u16 var, u16 valor, u32 ptr} + fin.
        Dispara cuando VarGet(var) == 0 (partida nueva: vars en cero)."""
        return struct.pack('<HH', self.var, 0) + \
            rom_ptr_le(dir_script) + b'\x00\x00'

    def buscar_espacio(self, necesario, desde=0x1700000):
        """Espacio libre: si hay margen, se agrega al final de la ROM."""
        if len(self.rom) + necesario + 0x100 <= ROM_MAX:
            return len(self.rom)          # anexar al final
        # buscar corrida de 0xFF (ROM ya en el tope)
        run = 0
        for off in range(desde, len(self.rom) - necesario):
            if self.rom[off] == 0xFF:
                run += 1
                if run >= necesario and off - run + 1 >= desde:
                    inicio = ((off - run + 1) + 3) & ~3
                    return inicio
            else:
                run = 0
        return None

    # ------------------------------------------------------------ aplicación
    def aplicar(self):
        if not self.validar_rom():
            return 1
        if not (FLAG_MIN <= self.flag < FLAG_MAX):
            log(C.ERR, f"Flag 0x{self.flag:X} fuera del rango válido "
                       f"(0x{FLAG_MIN:X}-0x{FLAG_MAX - 1:X}): FireRed solo "
                       "tiene 0x900 bits de flags y setflag con un valor "
                       "mayor ESCRIBE en variables ajenas del save (bug de "
                       "la v1.1, que usaba 0x10F0 y corrompía la variable "
                       "del Mt. Ember).")
            return 1
        if not (0x4000 <= self.var < 0x8000):
            log(C.ERR, f"Var 0x{self.var:X} fuera del rango válido "
                       "(0x4000-0x7FFF).")
            return 1
        header = self.localizar_header()
        if header is None:
            return 1
        tabla_vieja, entradas = self.leer_tabla_scripts(header)
        if tabla_vieja is None and entradas is None:
            return 1
        if self.ya_aplicado:
            return 0

        texto = self.codificar_texto(MENSAJE) if self.con_mensaje else b''
        if texto is None:
            return 1
        # ── plan de espacio (todo alineado a 4) ──
        tabla_nueva_sz = sum(5 for _ in entradas) + 5 + 1   # entradas+mía+fin
        script_dummy = self.construir_script(0, 0)
        script_sz = len(script_dummy)
        secundaria_sz = len(self.construir_secundaria(0))
        texto_sz = (len(texto) + 3) & ~3 if texto else 0
        total = (((tabla_nueva_sz + 3) & ~3) + ((secundaria_sz + 3) & ~3)
                 + script_sz + texto_sz + 16)
        base = self.buscar_espacio(total)
        if base is None:
            log(C.ERR, "No hay espacio libre en la ROM.")
            return 1
        dir_tabla = base
        dir_secundaria = (base + tabla_nueva_sz + 3) & ~3
        dir_script = (dir_secundaria + secundaria_sz + 3) & ~3
        dir_texto = ((dir_script + script_sz + 3) & ~3) if texto else 0
        log(C.INFO, f"Nuevo bloque @ 0x{base:07X} "
                    f"(tabla 0x{dir_tabla:07X}, "
                    f"secundaria 0x{dir_secundaria:07X}, "
                    f"script 0x{dir_script:07X}"
                    + (f", texto 0x{dir_texto:07X}" if texto else "") + ")")
        if self.dry:
            log(C.INFO, "[MODO SIMULACIÓN] No se escribió nada.")
            return 0

        # respaldo
        ts = time.strftime("%Y%m%d_%H%M%S")
        respaldo = f"{self.ruta}.respaldo_{ts}"
        shutil.copy2(self.ruta, respaldo)
        log(C.OK, f"Respaldo: {os.path.basename(respaldo)}")

        necesario = max(dir_texto + texto_sz if texto else 0,
                        dir_script + script_sz,
                        dir_secundaria + secundaria_sz)
        if len(self.rom) < necesario:
            self.rom.extend(b'\xFF' * (necesario - len(self.rom)))

        # tabla de level scripts nueva: vanilla (kinds 3 y 4 intactos) +
        # nuestro kind 2 (ON_FRAME) + terminador
        t = bytearray()
        for kind, ptr in entradas:
            t += bytes([kind]) + rom_ptr_le(ptr)
        t += b'\x02' + rom_ptr_le(dir_secundaria)   # kind 2 = ON_FRAME_TABLE
        t += b'\x00'                                # fin de tabla
        self.rom[dir_tabla:dir_tabla + len(t)] = t

        # tabla secundaria {var, valor, script} + fin (u16 0)
        s = self.construir_secundaria(dir_script)
        self.rom[dir_secundaria:dir_secundaria + len(s)] = s

        # script de entrega
        sc = self.construir_script(dir_script, dir_texto)
        assert len(sc) == script_sz
        self.rom[dir_script:dir_script + len(sc)] = sc

        # texto
        if texto:
            self.rom[dir_texto:dir_texto + len(texto)] = texto

        # repuntar el header
        struct.pack_into('<I', self.rom, header + 0x08,
                         0x08000000 + dir_tabla)

        # verificación de lectura inversa
        assert self.puntero_rom(header + 0x08) == dir_tabla
        assert self.u8(dir_tabla + sum(5 for _ in entradas)) == 2
        assert self.u8(dir_script) == CMD_SETVAR[0]
        assert self.u16(dir_secundaria) == self.var
        log(C.OK, "Verificación de escritura: correcta")

        with open(self.ruta, 'wb') as f:
            f.write(self.rom)
        log(C.OK, f"ROM actualizada: {self.ruta}")
        print()
        print("  ¡Listo! Al iniciar una partida NUEVA, Shelly (nv. 5)")
        print("  llegará a tu cuarto apenas tomes control. 🏴‍☠️")
        print("  (El flujo de Oak se mantiene: podrás elegir inicial además)")
        print()
        print("  IMPORTANTE: si tu emulador tiene un .sav de una compilación")
        print("  anterior, bórralo (o renómbralo) antes de abrir la ROM,")
        print("  o el juego seguirá cargando la partida vieja.")
        return 0


def main():
    ap = argparse.ArgumentParser(
        description="Parche de inicial v1.2.1: Shelly al arrancar la partida")
    ap.add_argument("rom", help="ruta de la ROM final (.gba)")
    ap.add_argument("--dry-run", action="store_true", help="no escribir nada")
    ap.add_argument("--sin-mensaje", action="store_true",
                    help="entrega silenciosa (sin texto/fanfare)")
    ap.add_argument("--flag", default=hex(FLAG_CONTROL),
                    help="flag de control (default 0x2AE, rango seguro)")
    ap.add_argument("--var", default=hex(VAR_DISPARO),
                    help="var disparadora (default 0x4090)")
    args = ap.parse_args()

    print("╔" + "═" * 60 + "╗")
    print("║  🏴‍☠️  PARCHE DE INICIAL v1.2.1 — Shelly al arrancar        ║")
    print("╚" + "═" * 60 + "╝")
    flag = int(args.flag, 0)
    var = int(args.var, 0)
    p = Parchador(args.rom, dry=args.dry_run,
                  con_mensaje=not args.sin_mensaje, flag=flag, var=var)
    sys.exit(p.aplicar())


if __name__ == "__main__":
    main()
