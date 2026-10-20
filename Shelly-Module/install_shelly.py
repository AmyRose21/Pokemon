#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
════════════════════════════════════════════════════════════════════════
  Módulo Shelly v1.4 — Instalador de la especie SHELLY (ID 0x5D1 / 1489)
  Para: DPE Gen-9 (Shiny-Miner) + CFRU-expansion (Shiny-Miner)
════════════════════════════════════════════════════════════════════════
  Shelly, la Administradora del Team Aqua, se capturó a sí misma con una
  Poké Ball especial y llegó por PC como inicial de la protagonista.

  Qué hace:
   - Agrega la especie SPECIES_SHELLY (0x5D1) y dex nacional 1026.
   - Inserta sprites (frontal/trasero/icono) generados desde su arte oficial.
   - Estadísticas, movimientos, entrada de Pokédex (español), grito (Jigglypuff).
   - Follower: camina tras ti con el sprite de una chica (LASS).
   - Pasiva «VIENTRE DIVINO» (ability 317, exclusiva de Shelly; v1.1):
       · Esquiva el 65% de TODOS los movimientos (incluidos los de estado).
       · Refleja el 45% del daño recibido de vuelta al atacante.
       · Congelada: un 25% de los daños que recibe se anulan por completo.
       · Burbuja/Burbuja Lente/Rayo Hielo y familia: 25% de atraparla en una
         burbuja 3-6 turnos (no puede huir ni cambiar; la burbuja no la daña).
       · Golpe Cuerpo/Placaje/Pisotón y familia: 25% de aplanarla 3-5 turnos
         (no puede moverse mientras permanezca aplanada).
   - NUEVO v1.4 — INICIAL COMPILADA DENTRO DE LA ROM (adiós a los parches):
       · El evento de llegada ahora vive en los PROPIOS ARCHIVOS del CFRU:
         src/shelly_module.c (disparo en TryRunOnFrameMapScript),
         assembly/overworld_scripts/shelly_inicial.s (evento con givepokemon
         nv.5 + fanfarria + mensaje) y strings/Scripts/shelly_inicial.string.
       · make.py produce la ROM con Shelly inicial YA INTEGRADA: ya no
         existe parche_inicial.py ni se toca la ROM tras compilar.
       · Migración: arregla el typo «refleó» → «reflejó» en los textos de
         la pasiva de repos parcheados con versiones anteriores.
   - Arregla el bug de Windows "python3 no se encontró" en make.py de ambos repos.

  Uso:
   python install_shelly.py --dpe <ruta DPE> --cfru <ruta CFRU> [opciones]
   Opciones: --dry-run (solo simular)  --restore (deshacer)  --assets <ruta>
   Es IDEMPOTENTE: puede re-ejecutarse sobre repos ya parcheados para
   actualizarlos (sprites nuevos, pasiva, inicial, etc.) sin duplicar nada.
════════════════════════════════════════════════════════════════════════
"""
import argparse
import os
import re
import shutil
import sys
import time

# ═════════════════════════ DATOS DE SHELLY ═════════════════════════════
SPECIES_ID = 0x5D1          # 1489: justo después de SPECIES_GLIMMORA_MEGA
NATIONAL_DEX = 1026         # después de Pecharunt (1025)
SPRITE_NUM = 1489           # numeración de archivo de sprite (libre)

CATEGORIA = "Pirata"        # categoría de Pokédex

BASE_STATS = {
    "hp": 70, "atk": 60, "dfs": 65, "spa": 95, "spd": 80, "spe": 95,
}

# Learnset por nivel (nivel, MOVE_X) — temático: una chica-pirata caótica
LEARNSET = [
    (1,   "MOVE_POUND"),
    (1,   "MOVE_GROWL"),
    (5,   "MOVE_DOUBLESLAP"),
    (9,   "MOVE_SWEETKISS"),
    (13,  "MOVE_ENCORE"),
    (17,  "MOVE_METRONOME"),
    (21,  "MOVE_ATTRACT"),
    (25,  "MOVE_BATONPASS"),
    (29,  "MOVE_SWIFT"),
    (33,  "MOVE_TRUMPCARD"),
    (37,  "MOVE_ROLEPLAY"),
    (41,  "MOVE_PSYCHIC"),
    (45,  "MOVE_CALMMIND"),
    (49,  "MOVE_LASTRESORT"),
    (53,  "MOVE_RECOVER"),
    (57,  "MOVE_HYPERVOICE"),
]

# Entrada de Pokédex (español; 3 líneas con \n literal — el compilador
# de strings del DPE/CFRU corta el texto en líneas reales, así que deben
# ir unidas con la secuencia \n, no con saltos de línea)
DEX_ENTRY_ES = (
    "Se atrapó a sí misma con una Poké\\nBall especial. Nadie sabe cómo lo\\n"
    "logró, pero llegó por PC a su niña."
)

# TMs que Shelly puede aprender (nombre de archivo en src/tm_compatibility)
TMS_APRENDER = [
    "3 - Water Pulse.txt",      # pirata aquática
    "4 - Calm Mind.txt",
    "6 - Toxic.txt",
    "13 - Ice Beam.txt",
    "15 - Hyper Beam.txt",
    "16 - Light Screen.txt",
    "17 - Protect.txt",
    "20 - Safeguard.txt",
    "27 - Return.txt",
    "29 - Psychic.txt",
    "30 - Shadow Ball.txt",
    "32 - Double Team.txt",
    "33 - Reflect.txt",
    "42 - Facade.txt",
    "43 - Secret Power.txt",
    "44 - Rest.txt",
    "45 - Attract.txt",
    "48 - Skill Swap.txt",
    "90 - Substitute.txt",
    "102 - Dazzling Gleam.txt",
]

# Tutores (nombre de archivo en src/tutor_compatibility, prefijo flexible)
TUTORES_APRENDER = ["Role Play", "Razor Shell", "Hydro Pump", "Helping Hand", "Covet", "Weather Ball"]

FOLLOWER_GFX = "EVENT_OBJ_GFX_LASS"   # cómo camina tras de ti

# ─── Pasiva «Vientre Divino» (ability 317, exclusiva de SPECIES_SHELLY) ───
ABILITY_ID = 317
NOMBRE_PASIVA = "Vientre Divino"
DESC_PASIVA_ES = (
    "Esquiva el 65% de todos los\\nmovimientos, incluso los de estado.\\n"
    "Refleja el 45% del daño recibido.\\nCongelada, un 25% de los daños se\\n"
    "anulan. La burbuja y el hielo la\\natrapan; los golpes la aplanan."
)

# ─── Inicial al arrancar (v1.4): TODO compilado dentro de la ROM ───
SHELLY_FLAG_INICIAL = 0x2AE      # flag vanilla SIN USO (rango seguro < 0x900)
MAP_GRUPO_CUARTO = 4             # gMapGroup_IndoorPallet (Pallet interior)
MAP_NUM_CUARTO = 1               # [0]=1F, [1]=2F del jugador, [2]=rival, [3]=lab

# src/shelly_module.c — disparo del evento (llamado por TryRunOnFrameMapScript)
ARCHIVO_C_INICIAL = (
"// ================================================================\n"
"// SHELLY MODULE v1.4 - inicial de Shelly COMPILADA DENTRO DE LA ROM.\n"
"// (antes: parche_inicial.py aplicado sobre la ROM final; ya no existe)\n"
"//\n"
"// La primera vez que entras a TU CUARTO (grupo 4, mapa 1 = Casa del\n"
"// Jugador 2F de Pallet) con el flag 0x2AE sin fijar, Shelly llega:\n"
"// givepokemon nv.5 con fanfarria y mensaje en espanol.\n"
"//\n"
"// Se invoca desde TryRunOnFrameMapScript (src/overworld.c), el mismo\n"
"// mecanismo vanilla que las escenas de Oak en Pallet: el script corre\n"
"// en el contexto GLOBAL del motor, asi que los comandos de espera\n"
"// (waitmsg / waitfanfare / waitbuttonpress) son seguros aqui.\n"
"// ================================================================\n"
"#include \"defines.h\"\n"
"#include \"../include/script.h\"\n"
"\n"
"// Flag vanilla SIN USO en FireRed US 1.0 (validado contra el decomp),\n"
"// dentro del rango seguro [0x1, 0x900). Las flags propias de la CFRU\n"
"// (NUZLOCKE etc.) viven en 0x900+, asi que no se pisan con nadie.\n"
"#define SHELLY_FLAG_INICIAL 0x2AE\n"
"\n"
"// El evento de llegada vive en assembly/overworld_scripts/shelly_inicial.s\n"
"// y su texto en strings/Scripts/shelly_inicial.string.\n"
"extern const u8 EventScript_ShellyArrival[];\n"
"\n"
"// TRUE si acaba de lanzar el evento de llegada (el llamador debe\n"
"// detenerse ese frame, igual que con los level scripts ON_FRAME).\n"
"bool8 ShellyTryArrival(void)\n"
"{\n"
"\t// Reproduccion del quest-log (2=PLAYBACK, 3=PLAYBACK_LAST):\n"
"\t// no entregar ni gastar el flag durante la repeticion.\n"
"\tif (gQuestLogMode == 2 || gQuestLogMode == 3)\n"
"\t\treturn FALSE;\n"
"\n"
"\t// Estamos en el CUARTO DEL JUGADOR? Grupo 4 = IndoorPallet:\n"
"\t// [0]=1F, [1]=2F del jugador, [2]=casa del rival, [3]=laboratorio.\n"
"\tif (gSaveBlock1->location.mapGroup == 4\n"
"\t && gSaveBlock1->location.mapNum == 1)\n"
"\t{\n"
"\t\tif (!FlagGet(SHELLY_FLAG_INICIAL))\n"
"\t\t{\n"
"\t\t\tFlagSet(SHELLY_FLAG_INICIAL);\n"
"\t\t\tScriptContext1_SetupScript(EventScript_ShellyArrival);\n"
"\t\t\treturn TRUE;\n"
"\t\t}\n"
"\t}\n"
"\n"
"\treturn FALSE;\n"
"}\n"
)

# assembly/overworld_scripts/shelly_inicial.s — el evento (bytes = secuencia
# v1.2.1 verificada; el mismo mecanismo vanilla de las escenas de Oak)
ARCHIVO_S_INICIAL = (
"@ ================================================================\n"
"@ SHELLY MODULE v1.4 - EventScript_ShellyArrival\n"
"@ Shelly llega por PC a tu cuarto en la primera partida nueva.\n"
"@\n"
"@ Disparado desde src/shelly_module.c (ShellyTryArrival) al entrar por\n"
"@ primera vez al CUARTO DEL JUGADOR (grupo 4, mapa 1) con el flag 0x2AE\n"
"@ sin fijar. Corre en el contexto GLOBAL del motor (SetupScript), el\n"
"@ mismo mecanismo vanilla de las escenas de Oak en Pallet: seguro para\n"
"@ mensajes con espera (waitmsg/waitfanfare/waitbuttonpress).\n"
"@\n"
"@ El texto gText_ShellyArrival vive en strings/Scripts/shelly_inicial.string\n"
"@ ================================================================\n"
".align 2\n"
".thumb\n"
"\n"
".include \"../xse_commands.s\"\n"
".include \"../xse_defines.s\"\n"
".include \"../asm_defines.s\"\n"
"\n"
"@ MUS_OBTAIN_ITEM (258) del juego base: fanfarria de objeto recibido.\n"
".equ MUS_OBTAIN_ITEM, 0x102\n"
"\n"
".global EventScript_ShellyArrival\n"
"EventScript_ShellyArrival:\n"
"\tgivepokemon SPECIES_SHELLY 5 ITEM_NONE 0 0 0\n"
"\tlockall\n"
"\tfanfare MUS_OBTAIN_ITEM\n"
"\tpreparemsg gText_ShellyArrival\n"
"\twaitmsg\n"
"\twaitfanfare\n"
"\twaitbuttonpress\n"
"\tcloseonkeypress\n"
"\treleaseall\n"
"\tend\n"
)

# strings/Scripts/shelly_inicial.string — mensaje de llegada (español)
ARCHIVO_STRING_INICIAL = (
"#org @gText_ShellyArrival\n"
"¡Recibiste a SHELLY!\n" "¡Tu aventura comienza!\n"
)

# Textos de batalla (español, codificados vía charmap del CFRU)
TEXTOS_BATALLA_ES = [
    ("gText_VientreDivinoReflejo",
     "¡El vientre divino de [TARGET]\\nreflejó el ataque!"),
    ("gText_VientreDivinoBurbuja",
     "¡[TARGET] quedó atrapada\\ndentro de una burbuja!"),
    ("gText_VientreDivinoBurbujaFin",
     "¡La burbuja estalló y\\n[TARGET] quedó libre!"),
    ("gText_VientreDivinoAplanadaGolpe",
     "¡El ataque dejó a [TARGET]\\ncompletamente aplanada!"),
    ("gText_VientreDivinoAplanadaTurno",
     "¡[TARGET] está aplanada\\ny no puede moverse!"),
]

AYUDANTES_C = (
"\n\n"
"// ================================================================\n"
"// SHELLY:HELPERS VIENTRE DIVINO - efecto exclusivo de SPECIES_SHELLY.\n"
"//  - Esquiva el 65% de TODOS los movimientos (tambien los de estado).\n"
"//  - Refleja el 45% del dano recibido de vuelta al atacante.\n"
"//  - Congelada: un 25% de los danos contra ella se anulan por completo.\n"
"//  - Burbuja/Burbuja Lente/Rayo Hielo y familia: 25% de atraparla en una\n"
"//    burbuja 3-6 turnos (sin dano por turnos; no puede huir ni cambiar).\n"
"//  - Placaje/Pisoton/Golpe Cuerpo y familia: 25% de aplanarla 3-5 turnos\n"
"//    (pierde esos turnos; no puede moverse mientras siga aplanada).\n"
"// ================================================================\n"
"\n"
"bool8 ShellyEsPirataDivina(u8 bank)\n"
"{\n"
"\treturn SPECIES(bank) == SPECIES_SHELLY\n"
"\t    && ABILITY(bank) == ABILITY_VIENTRE_DIVINO;\n"
"}\n"
"\n"
"static bool8 ShellyEsMovimientoBurbuja(u16 move)\n"
"{\n"
"\tswitch (move) {\n"
"\t\tcase MOVE_BUBBLE:\n"
"\t\tcase MOVE_BUBBLEBEAM:\n"
"\t\tcase MOVE_ICEBEAM:\n"
"\t\tcase MOVE_POWDERSNOW:\n"
"\t\tcase MOVE_ICYWIND:\n"
"\t\tcase MOVE_AVALANCHE:\n"
"\t\tcase MOVE_ICESHARD:\n"
"\t\t\treturn TRUE;\n"
"\t}\n"
"\treturn FALSE;\n"
"}\n"
"\n"
"static bool8 ShellyEsMovimientoAplanador(u16 move)\n"
"{\n"
"\tswitch (move) {\n"
"\t\tcase MOVE_SLAM:\n"
"\t\tcase MOVE_STOMP:\n"
"\t\tcase MOVE_BODYSLAM:\n"
"\t\tcase MOVE_STEAMROLLER:\n"
"\t\tcase MOVE_HEAVYSLAM:\n"
"\t\tcase MOVE_HEATCRASH:\n"
"\t\tcase MOVE_DRAGONRUSH:\n"
"\t\t\treturn TRUE;\n"
"\t}\n"
"\treturn FALSE;\n"
"}\n"
"\n"
"bool8 ShellyEsBurbuja(u8 bank)\n"
"{\n"
"\tif (!ShellyEsPirataDivina(bank))\n"
"\t\treturn FALSE;\n"
"\tif (!(gBattleMons[bank].status2 & STATUS2_WRAPPED))\n"
"\t\treturn FALSE;\n"
"\treturn ShellyEsMovimientoBurbuja(gBattleStruct->wrappedMove[bank]);\n"
"}\n"
"\n"
"const u8* ShellyBurbujaFinScript(u8 bank)\n"
"{\n"
"\t// v1.2: solo se invoca cuando ShellyEsBurbuja(bank) ya es cierto (la\n"
"\t// decisión vive en end_turn.c). Los wraps normales usan ALLÍ la macro\n"
"\t// BattleScript_WrapEnds: en este CFRU es una dirección fija de la ROM,\n"
"\t// no un símbolo del enlazador, y no puede referenciarse desde aquí.\n"
"\t(void)bank;\n"
"\tgBattleStringLoader = gText_VientreDivinoBurbujaFin;\n"
"\treturn BattleScript_PrintCustomString;\n"
"}\n"
"\n"
"bool8 ShellyTryAplanada(u8 bank)\n"
"{\n"
"\tif (!ShellyEsPirataDivina(bank) || gNewBS->shellyAplanada[bank] == 0)\n"
"\t\treturn FALSE;\n"
"\n"
"\tgNewBS->shellyAplanada[bank]--;\n"
"\tgBattleStringLoader = gText_VientreDivinoAplanadaTurno;\n"
"\tgBattlescriptCurrInstr = BattleScript_ShellyAplanada;\n"
"\treturn TRUE;\n"
"}\n"
"\n"
"void ShellyVientreDivinoAlSerGolpeada(u8 bank, u16 move)\n"
"{\n"
"\t// 45%: el vientre divino refleja TODO el dano de este movimiento\n"
"\t// de vuelta hacia el atacante.\n"
"\tif (BATTLER_ALIVE(gBankAttacker)\n"
"\t&& gBankAttacker != bank\n"
"\t&& ABILITY(gBankAttacker) != ABILITY_MAGICGUARD\n"
"\t&& Random() % 100 < 45\n"
"\t&& gNewBS->turnDamageTaken[bank] > 0)\n"
"\t{\n"
"\t\tgBattleMoveDamage = gNewBS->turnDamageTaken[bank];\n"
"\t\tBattleScriptPushCursor();\n"
"\t\tgBattlescriptCurrInstr = BattleScript_ShellyRefleja;\n"
"\t\treturn; // el reflejo eclipsa al resto de efectos este golpe\n"
"\t}\n"
"\n"
"\t// 25%: la burbuja o el hielo la atrapan 3-6 turnos (sin dano por turnos).\n"
"\tif (ShellyEsMovimientoBurbuja(move)\n"
"\t&& !(gBattleMons[bank].status2 & STATUS2_WRAPPED)\n"
"\t&& Random() % 100 < 25)\n"
"\t{\n"
"\t\tu8 turnos = 3 + (Random() % 4); // 3..6 turnos\n"
"\t\tgBattleMons[bank].status2 &= ~STATUS2_WRAPPED;\n"
"\t\tgBattleMons[bank].status2 |= (STATUS2_WRAPPED / 7) * turnos;\n"
"\t\tgBattleStruct->wrappedMove[bank] = move;\n"
"\t\tgBattleStruct->wrappedBy[bank] = gBankAttacker;\n"
"\t\tgBattleStringLoader = gText_VientreDivinoBurbuja;\n"
"\t\tBattleScriptPushCursor();\n"
"\t\tgBattlescriptCurrInstr = BattleScript_PrintCustomString;\n"
"\t\treturn;\n"
"\t}\n"
"\n"
"\t// 25%: el golpe aplastante la deja aplanada 3-5 turnos.\n"
"\tif (ShellyEsMovimientoAplanador(move)\n"
"\t&& gNewBS->shellyAplanada[bank] == 0\n"
"\t&& Random() % 100 < 25)\n"
"\t{\n"
"\t\tgNewBS->shellyAplanada[bank] = 3 + (Random() % 3); // 3..5 turnos\n"
"\t\tgBattleStringLoader = gText_VientreDivinoAplanadaGolpe;\n"
"\t\tBattleScriptPushCursor();\n"
"\t\tgBattlescriptCurrInstr = BattleScript_PrintCustomString;\n"
"\t}\n"
"}\n"
)



# ════════════════════════════════════════════════════════════════════════

# v1.2 — bloque que sustituye a la línea de fin de wrap en end_turn.c.
# BattleScript_WrapEnds SOLO existe como macro a dirección fija de la ROM
# (include/new/end_turn_battle_scripts.h, visible únicamente en end_turn.c),
# por eso la decisión burbuja-vs-wrap-normal debe vivir en ese archivo.
BURBUJA_FIN_V12 = ("\t\t\t\t\t// SHELLY v1.2: mensaje propio al romperse la burbuja;\n"
                   "\t\t\t\t\t// los wraps normales siguen con la macro local.\n"
                   "\t\t\t\t\tif (ShellyEsBurbuja(gActiveBattler))\n"
                   "\t\t\t\t\t\tgBattlescriptCurrInstr = ShellyBurbujaFinScript(gActiveBattler);\n"
                   "\t\t\t\t\telse\n"
                   "\t\t\t\t\t\tgBattlescriptCurrInstr = BattleScript_WrapEnds;")


MARKER = "SPECIES_SHELLY"   # indicador de instalación previa


class C:
    OK = "\033[92m[OK]\033[0m"
    INFO = "\033[96m[INFO]\033[0m"
    WARN = "\033[93m[AVISO]\033[0m"
    ERR = "\033[91m[ERROR]\033[0m"


def log(kind, msg):
    print(f"{kind} {msg}")


def encabezado(texto):
    print("\n" + "─" * 62)
    print(f"  {texto}")
    print("─" * 62)


class Installer:
    def __init__(self, dpe, cfru, assets, dry=False):
        self.dpe = dpe
        self.cfru = cfru
        self.assets = assets
        self.dry = dry
        self.backups = []
        self.modified = []
        self.errors = []

    # --------------------------------------------------------- utilidades
    def path(self, repo, rel):
        return os.path.join(repo, *rel.split("/"))

    def read(self, repo, rel):
        p = self.path(repo, rel)
        if not os.path.isfile(p):
            raise FileNotFoundError(p)
        with open(p, encoding="utf-8", errors="surrogateescape") as f:
            return f.read()

    def write(self, repo, rel, content):
        p = self.path(repo, rel)
        if not self.dry:
            with open(p, "w", encoding="utf-8", newline="") as f:
                f.write(content)
        self.modified.append(rel)

    def backup(self, repo, rel):
        p = self.path(repo, rel)
        ts_dir = os.path.join(repo, ".shelly_backup",
                              time.strftime("%Y%m%d_%H%M%S"))
        dst = os.path.join(ts_dir, rel.replace("/", "__"))
        if not self.dry:
            os.makedirs(ts_dir, exist_ok=True)
            if not os.path.exists(dst):
                shutil.copy2(p, dst)
        self.backups.append((p, dst))

    def sub(self, repo, rel, old, new, desc, required=True, count=1):
        """Reemplaza `old` (texto exacto) por `new` una vez."""
        content = self.read(repo, rel)
        if old not in content:
            if required:
                self.errors.append(f"{rel}: no se encontró patrón de «{desc}»")
            else:
                log(C.WARN, f"{rel}: se omite «{desc}» (patrón no encontrado)")
            return False
        nuevo = content.replace(old, new, count)
        self.backup(repo, rel)
        self.write(repo, rel, nuevo)
        log(C.OK, f"{rel}: {desc}")
        return True

    def insert_after(self, repo, rel, anchor, addition, desc, required=True):
        content = self.read(repo, rel)
        i = content.find(anchor)
        if i < 0:
            if required:
                self.errors.append(f"{rel}: ancla no encontrada para «{desc}»")
            else:
                log(C.WARN, f"{rel}: se omite «{desc}» (ancla no encontrada)")
            return False
        pos = i + len(anchor)
        nuevo = content[:pos] + addition + content[pos:]
        self.backup(repo, rel)
        self.write(repo, rel, nuevo)
        log(C.OK, f"{rel}: {desc}")
        return True

    def insert_before(self, repo, rel, anchor, addition, desc, required=True):
        content = self.read(repo, rel)
        i = content.find(anchor)
        if i < 0:
            if required:
                self.errors.append(f"{rel}: ancla no encontrada para «{desc}»")
            else:
                log(C.WARN, f"{rel}: se omite «{desc}» (ancla no encontrada)")
            return False
        nuevo = content[:i] + addition + content[i:]
        self.backup(repo, rel)
        self.write(repo, rel, nuevo)
        log(C.OK, f"{rel}: {desc}")
        return True

    def append(self, repo, rel, addition, desc):
        content = self.read(repo, rel)
        if not content.endswith("\n"):
            content += "\n"
        self.backup(repo, rel)
        self.write(repo, rel, content + addition)
        log(C.OK, f"{rel}: {desc}")
        return True

    def sub_desde_marca(self, repo, rel, marca, old, new, desc, ventana=2000,
                        required=True):
        """Reemplaza `old` por `new` SOLO en su primera aparición tras `marca`
        (p. ej. dentro del bloque [SPECIES_SHELLY] sin tocar otras especies)."""
        content = self.read(repo, rel)
        i = content.find(marca)
        if i < 0:
            msg = f"{rel}: marca «{marca}» no encontrada"
            (self.errors.append(msg) if required else log(C.WARN, msg))
            return False
        j = content.find(old, i)
        if j < 0 or j > i + ventana:
            msg = f"{rel}: «{desc}» ya aplicado o fuera del bloque"
            (self.errors.append(msg) if required else log(C.WARN, msg + " (omitido)"))
            return False
        nuevo = content[:j] + new + content[j + len(old):]
        self.backup(repo, rel)
        self.write(repo, rel, nuevo)
        log(C.OK, f"{rel}: {desc}")
        return True

    def already(self, repo, rel, token=MARKER):
        try:
            return token in self.read(repo, rel)
        except FileNotFoundError:
            return False

    # --------------------------------------------------------- verificación
    def verificar(self):
        encabezado("1/9 · Verificando repositorios")
        ok = True
        for repo, nombre, files in [
            (self.dpe, "DPE", ["include/species.h", "src/Base_Stats.c",
                              "scripts/make.py", "include/pokedex.h"]),
            (self.cfru, "CFRU", ["include/constants/species.h",
                                 "src/config.h", "scripts/make.py",
                                 "src/Tables/level_up_learnsets.c"]),
        ]:
            for rel in files:
                if not os.path.isfile(self.path(repo, rel)):
                    log(C.ERR, f"{nombre}: falta {rel} — ¿es la ruta correcta?")
                    ok = False
        if ok:
            dpe_sp = self.read(self.dpe, "include/species.h")
            if "NUM_SPECIES (SPECIES_GLIMMORA_MEGA + 1)" not in dpe_sp:
                log(C.WARN, "DPE: NUM_SPECIES no coincide con lo esperado "
                            "(¿versión distinta del repo?). Se intentará igualmente.")
            if self.already(self.dpe, "include/species.h"):
                log(C.INFO, "Shelly ya parece instalada; se omitirán duplicados.")
        return ok

    # --------------------------------------------------------- DPE
    def parchear_dpe(self):
        encabezado("2/9 · Parcheando DPE (datos de la especie)")

        # --- include/species.h
        rel = "include/species.h"
        if self.already(self.dpe, rel):
            log(C.INFO, "species.h: SHELLY ya presente (omitido)")
        else:
            self.sub(self.dpe, rel,
                     "#define NUM_SPECIES (SPECIES_GLIMMORA_MEGA + 1)",
                     f"#define SPECIES_SHELLY {hex(SPECIES_ID)}\n"
                     "#define NUM_SPECIES (SPECIES_SHELLY + 1)",
                     "especie + NUM_SPECIES")

        # --- include/sprite_data.h (declaraciones de los graficos)
        rel = "include/sprite_data.h"
        if self.already(self.dpe, rel):
            log(C.INFO, "sprite_data.h: SHELLY ya presente (omitido)")
        else:
            self.sub(self.dpe, rel,
                     "extern const u8 gIconSprite252Tiles[];",
                     "extern const u8 gIconSprite252Tiles[];\n\n"
                     f"extern const u8 gFrontSprite{SPRITE_NUM}ShellyTiles[];\n"
                     f"extern const u8 gFrontSprite{SPRITE_NUM}ShellyPal[];\n"
                     f"extern const u8 gBackShinySprite{SPRITE_NUM}ShellyTiles[];\n"
                     f"extern const u8 gBackShinySprite{SPRITE_NUM}ShellyPal[];\n"
                     f"extern const u8 gIconSprite{SPRITE_NUM}ShellyTiles[];\n",
                     "declaraciones extern de los sprites de Shelly")

        # --- include/pokedex.h
        rel = "include/pokedex.h"
        if not self.already(self.dpe, rel, "NATIONAL_DEX_SHELLY"):
            self.sub(self.dpe, rel,
                     "#define NATIONAL_DEX_PECHARUNT 1025",
                     f"#define NATIONAL_DEX_PECHARUNT 1025\n"
                     f"#define NATIONAL_DEX_SHELLY {NATIONAL_DEX}",
                     "dex nacional 1026")
            self.sub(self.dpe, rel,
                     "#define FINAL_DEX_ENTRY NATIONAL_DEX_PECHARUNT",
                     "#define FINAL_DEX_ENTRY NATIONAL_DEX_SHELLY",
                     "FINAL_DEX_ENTRY -> SHELLY")
            self.sub(self.dpe, rel,
                     "extern const u8 DEX_ENTRY_PECHARUNT[];",
                     "extern const u8 DEX_ENTRY_PECHARUNT[];\n"
                     "extern const u8 DEX_ENTRY_SHELLY[];",
                     "extern DEX_ENTRY_SHELLY")

        # --- src/Base_Stats.c
        rel = "src/Base_Stats.c"
        if self.already(self.dpe, rel):
            log(C.INFO, "Base_Stats.c: SHELLY ya presente (omitido)")
        else:
            content = self.read(self.dpe, rel)
            i = content.rfind("\n};")
            bloque = (
                "\n\t[SPECIES_SHELLY] =\n\t{\n"
                f"\t\t.baseHP = {BASE_STATS['hp']},\n"
                f"\t\t.baseAttack = {BASE_STATS['atk']},\n"
                f"\t\t.baseDefense = {BASE_STATS['dfs']},\n"
                f"\t\t.baseSpAttack = {BASE_STATS['spa']},\n"
                f"\t\t.baseSpDefense = {BASE_STATS['spd']},\n"
                f"\t\t.baseSpeed = {BASE_STATS['spe']},\n"
                "\t\t.type1 = TYPE_NORMAL,\n"
                "\t\t.type2 = TYPE_NORMAL,\n"
                "\t\t.catchRate = 45,\n"
                "\t\t.expYield = 148,\n"
                "\t\t.evYield_HP = 0,\n\t\t.evYield_Attack = 0,\n"
                "\t\t.evYield_Defense = 0,\n\t\t.evYield_SpAttack = 2,\n"
                "\t\t.evYield_SpDefense = 0,\n\t\t.evYield_Speed = 1,\n"
                "\t\t.item1 = ITEM_NONE,\n\t\t.item2 = ITEM_NONE,\n"
                "\t\t.genderRatio = PERCENT_FEMALE(100),\n"
                "\t\t.eggCycles = 120,\n\t\t.friendship = 140,\n"
                "\t\t.growthRate = GROWTH_MEDIUM_SLOW,\n"
                "\t\t.eggGroup1 = EGG_GROUP_NONE,\n"
                "\t\t.eggGroup2 = EGG_GROUP_NONE,\n"
                "\t\t.ability1 = ABILITY_VIENTRE_DIVINO,\n"
                "\t\t.ability2 = ABILITY_NONE,\n"
                "\t\t.safariZoneFleeRate = 0,\n"
                "\t\t.hiddenAbility = ABILITY_NONE,\n"
                "\t\t.noFlip = TRUE,\n"
                "\t},\n"
            )
            nuevo = content[:i] + bloque + content[i:]
            self.backup(self.dpe, rel)
            self.write(self.dpe, rel, nuevo)
            log(C.OK, f"Base_Stats.c: stats de Shelly "
                      f"(HP{BASE_STATS['hp']}/AT{BASE_STATS['atk']}/"
                      f"DF{BASE_STATS['dfs']}/SA{BASE_STATS['spa']}/"
                      f"SD{BASE_STATS['spd']}/VE{BASE_STATS['spe']})")

        # --- src/Learnsets.c (array + tabla)
        rel = "src/Learnsets.c"
        if self.already(self.dpe, rel):
            log(C.INFO, "Learnsets.c: SHELLY ya presente (omitido)")
        else:
            learnset_txt = ",\n".join(
                f"\tLEVEL_UP_MOVE({lvl:2d}, {mv})" for lvl, mv in LEARNSET)
            arr = (
                "static const struct LevelUpMove sShellyLevelUpLearnset[] = {\n"
                + learnset_txt + ",\n\tLEVEL_UP_END\n};\n\n"
            )
            self.insert_before(
                self.dpe, rel,
                "static const struct LevelUpMove sBulbasaurLevelUpLearnset[] = {",
                arr, "array sShellyLevelUpLearnset")
            self.sub(self.dpe, rel,
                     "\t[SPECIES_GLIMMORA_MEGA] = sGlimmoraLevelUpLearnset,",
                     "\t[SPECIES_GLIMMORA_MEGA] = sGlimmoraLevelUpLearnset,\n"
                     "\t[SPECIES_SHELLY] = sShellyLevelUpLearnset,",
                     "entrada en tabla de learnsets")

        # --- tablas de gráficos y coordenadas
        graficos = [
            ("src/Front_Pic_Table.c",
             f"\t[SPECIES_SHELLY] =            {{gFrontSprite{SPRITE_NUM}ShellyTiles, (64 * 64) / 2, SPECIES_SHELLY}},\n",
             "[SPECIES_GLIMMORA_MEGA] = {gFrontSprite1450GlimmoraMegaTiles, (64 * 64) / 2, SPECIES_GLIMMORA_MEGA},"),
            ("src/Back_Pic_Table.c",
             f"\t[SPECIES_SHELLY] = {{gBackShinySprite{SPRITE_NUM}ShellyTiles, (64 * 64) / 2, SPECIES_SHELLY}},\n",
             "[SPECIES_GLIMMORA_MEGA] = {gBackShinySprite1450GlimmoraMegaTiles, (64 * 64) / 2, SPECIES_GLIMMORA_MEGA},"),
            ("src/Palette_Table.c",
             f"\t[SPECIES_SHELLY] =            {{gFrontSprite{SPRITE_NUM}ShellyPal, SPECIES_SHELLY, 0x0}},\n",
             "[SPECIES_GLIMMORA_MEGA] = {gFrontSprite1450GlimmoraMegaPal, SPECIES_GLIMMORA_MEGA, 0x0},"),
            ("src/Shiny_Palette_Table.c",
             f"\t[SPECIES_SHELLY] = {{gBackShinySprite{SPRITE_NUM}ShellyPal, SPECIES_SHELLY + NUM_SPECIES, 0x0}},\n",
             "[SPECIES_GLIMMORA_MEGA] = {gBackShinySprite1450GlimmoraMegaPal, SPECIES_GLIMMORA_MEGA + NUM_SPECIES, 0x0},"),
            ("src/Icon_Table.c",
             f"\t[SPECIES_SHELLY] = gIconSprite{SPRITE_NUM}ShellyTiles,\n",
             "[SPECIES_GLIMMORA_MEGA] = gIconSprite1450GlimmoraMegaTiles,"),
            ("src/Icon_Palette_Table.c",
             "\t[SPECIES_SHELLY] = 0x0,\n",
             "[SPECIES_GLIMMORA_MEGA] = 0x0,"),
            ("src/Front_Pic_Coords_Table.c",
             "\t[SPECIES_SHELLY] =\n\t{\n\t\t.size = 0x0,\n\t\t.y_offset = 0x2,\n\t},\n",
             "[SPECIES_GLIMMORA_MEGA] =\n\t{\n\t\t.size = 0x0,\n\t\t.y_offset = 0x2,\n\t},"),
            ("src/Back_Pic_Coords_Table.c",
             "\t[SPECIES_SHELLY] =\n\t{\n\t\t.size = 0x0,\n\t\t.y_offset = 0xc,\n\t},\n",
             "[SPECIES_GLIMMORA_MEGA] =\n\t{\n\t\t.size = 0x0,\n\t\t.y_offset = 0xc,\n\t},"),
            ("src/Enemy_Elevation_Table.c",
             "\t[SPECIES_SHELLY] = 0x0,\n",
             "[SPECIES_GLIMMORA_MEGA] = 0x8,"),
        ]
        for rel, extra, ancla in graficos:
            if self.already(self.dpe, rel):
                log(C.INFO, f"{rel}: SHELLY ya presente (omitido)")
            else:
                self.sub(self.dpe, rel, ancla, ancla + extra,
                         f"entrada en {rel.split('/')[-1]}")

        # --- gritos: clonar la entrada de Jigglypuff
        for rel in ("src/Cry_Table.c", "src/Cry_Table_2.c"):
            if self.already(self.dpe, rel):
                log(C.INFO, f"{rel}: SHELLY ya presente (omitido)")
            else:
                content = self.read(self.dpe, rel)
                m = re.search(r"(\[SPECIES_JIGGLYPUFF\] =\n\t\{.*?\n\t\},)",
                              content, re.S)
                if not m:
                    self.errors.append(f"{rel}: entrada de Jigglypuff no encontrada")
                    continue
                clon = m.group(1).replace("SPECIES_JIGGLYPUFF", "SPECIES_SHELLY")
                ancla = re.search(r"\[SPECIES_GLIMMORA_MEGA\] =\n\t\{.*?\n\t\},",
                                  content, re.S)
                if not ancla:
                    self.errors.append(f"{rel}: ancla GLIMMORA_MEGA no encontrada")
                    continue
                nuevo = content[:ancla.end()] + "\n" + clon + content[ancla.end():]
                self.backup(self.dpe, rel)
                self.write(self.dpe, rel, nuevo)
                log(C.OK, f"{rel}: grito de Shelly (heredado de Jigglypuff)")

    # ------------------------------------------------- DPE: dex y textos
    def parchear_dpe_dex(self):
        encabezado("3/9 · Parcheando DPE (Pokédex, textos y órdenes)")

        # --- src/Pokedex_Data_Table.c
        rel = "src/Pokedex_Data_Table.c"
        # v1.1: REPARAR duplicados de reejecuciones v1.0 (el marcador antiguo
        # nunca coincidia y cada pasada insertaba la entrada otra vez).
        content = self.read(self.dpe, rel)
        dups = re.findall(r"\n\t\[NATIONAL_DEX_SHELLY\] =\n\t\{.*?\n\t\},",
                          content, re.S)
        if len(dups) > 1:
            for extra in dups[1:]:
                content = content.replace(extra, "", 1)
            self.backup(self.dpe, rel)
            self.write(self.dpe, rel, content)
            log(C.OK, f"Pokedex_Data_Table.c: eliminadas {len(dups) - 1} "
                      "entradas duplicadas de reejecuciones anteriores")
        if self.already(self.dpe, rel, "NATIONAL_DEX_SHELLY"):
            log(C.INFO, "Pokedex_Data_Table.c: SHELLY ya presente (omitido)")
        else:
            ancla = "[NATIONAL_DEX_PECHARUNT] ="
            content = self.read(self.dpe, rel)
            i = content.find(ancla)
            j = content.find("\t},", i)
            bloque = (
                "\n\t[NATIONAL_DEX_SHELLY] =\n\t{\n"
                "\t\t.categoryName = {_P, _i, _r, _a, _t, _a, _END, _SPACE,"
                " _SPACE, _SPACE, _SPACE, _SPACE},\n"
                "\t\t.height = 16,\n"
                "\t\t.weight = 460,\n"
                "\t\t.description = DEX_ENTRY_SHELLY,\n"
                "\t\t.unusedDescription = (const u8*) 0x8444cb1,\n"
                "\t\t.pokemonScale = 256,\n"
                "\t\t.pokemonOffset = 0,\n"
                "\t\t.trainerScale = 256,\n"
                "\t\t.trainerOffset = 0,\n"
                "\t},"
            )
            nuevo = content[:j + 3] + bloque + content[j + 3:]
            self.backup(self.dpe, rel)
            self.write(self.dpe, rel, nuevo)
            log(C.OK, "Pokedex_Data_Table.c: entrada de Shelly "
                     "(Pirata · 1,6 m · 46,0 kg)")

        # --- src/Species_To_Pokdex_Table.c
        rel = "src/Species_To_Pokdex_Table.c"
        if self.already(self.dpe, rel):
            log(C.INFO, "Species_To_Pokdex_Table.c: SHELLY ya presente")
        else:
            self.sub(self.dpe, rel,
                     "[SPECIES_GLIMMORA_MEGA - 1] = NATIONAL_DEX_GLIMMORA,",
                     "[SPECIES_GLIMMORA_MEGA - 1] = NATIONAL_DEX_GLIMMORA,\n"
                     "[SPECIES_SHELLY - 1] = NATIONAL_DEX_SHELLY,",
                     "mapeo especie→dex nacional")

        # --- src/Pokedex_Orders.c (5 listas)
        rel = "src/Pokedex_Orders.c"
        if self.already(self.dpe, rel):
            log(C.INFO, "Pokedex_Orders.c: SHELLY ya presente")
        else:
            content = self.read(self.dpe, rel)
            # 1) lista principal (Regional/nacional): al final
            m = re.search(r"const u16 gPokedexOrder_Regional\[\] =\n\{\n"
                          r"(.*?)\n\};", content, re.S)
            if m:
                lista = m.group(1).rstrip().rstrip(",")
                nueva = lista + ",\n\tSPECIES_SHELLY"
                content = content.replace(m.group(0),
                    "const u16 gPokedexOrder_Regional[] =\n{\n" + nueva + "\n};")
                log(C.OK, "Pokedex_Orders.c: Shelly en la dex principal (final)")
            else:
                self.errors.append("Pokedex_Orders.c: lista Regional no encontrada")
            # 2-5) listas de búsqueda: al final de cada una (orden cosmético)
            for nombre in ("Alphabetical", "Weight", "Height", "Type"):
                mm = re.search(rf"const u16 gPokedexOrder_{nombre}\[\] =\n\{{\n"
                               r"(.*?)\n};", content, re.S)
                if mm:
                    content = content.replace(
                        mm.group(0),
                        f"const u16 gPokedexOrder_{nombre}[] =\n{{\n"
                        + mm.group(1).rstrip().rstrip(",")
                        + ",\n\tSPECIES_SHELLY\n};")
                    log(C.OK, f"Pokedex_Orders.c: Shelly añadida a lista {nombre}")
                else:
                    log(C.WARN, f"Pokedex_Orders.c: lista {nombre} no encontrada"
                                " (omitida)")
            self.backup(self.dpe, rel)
            self.write(self.dpe, rel, content)

        # --- strings/Pokedex_Data.string
        rel = "strings/Pokedex_Data.string"
        if self.already(self.dpe, rel, "DEX_ENTRY_SHELLY"):
            log(C.INFO, "Pokedex_Data.string: SHELLY ya presente")
            # v1.1: reparar entradas v1.0 escritas con saltos de linea reales
            # (el compilador de strings solo muestra la primera linea).
            content = self.read(self.dpe, rel)
            i = content.find("#org @DEX_ENTRY_SHELLY")
            j = content.find("#org", i + 10)
            bloque = content[i:(j if j > 0 else len(content))]
            cuerpo = [l for l in bloque.split("\n")[1:] if l.strip()]
            if len(cuerpo) > 1:
                self.sub(self.dpe, rel, "\n".join(cuerpo), DEX_ENTRY_ES,
                         "entrada de Pokédex v1.1 (saltos corregidos)", required=False)
        else:
            texto = (
                "\n#org @DEX_ENTRY_SHELLY\n"
                f"{DEX_ENTRY_ES}\n"
                "\n#org @DEX_CATEGORY_SHELLY\n"
                f"{CATEGORIA}\n"
            )
            content = self.read(self.dpe, rel)
            if not content.endswith("\n"):
                content += "\n"
            self.backup(self.dpe, rel)
            self.write(self.dpe, rel, content + texto)
            log(C.OK, "Pokedex_Data.string: entrada de Pokédex en español")

        # --- strings/Pokemon_Name_Table.string
        rel = "strings/Pokemon_Name_Table.string"
        if self.already(self.dpe, rel, "NAME_SHELLY"):
            log(C.INFO, "Pokemon_Name_Table.string: SHELLY ya presente")
        else:
            content = self.read(self.dpe, rel)
            if not content.endswith("\n"):
                content += "\n"
            content += "\n#org @NAME_SHELLY\nShelly\n"
            self.backup(self.dpe, rel)
            self.write(self.dpe, rel, content)
            log(C.OK, "Pokemon_Name_Table.string: nombre «Shelly»")

    # -------------------------------------------- DPE: TMs, tutores, sprites
    def parchear_dpe_tms_sprites(self):
        encabezado("4/9 · Parcheando DPE (TMs, tutores, sprites, make.py)")

        # --- TMs
        carpeta = self.path(self.dpe, "src/tm_compatibility")
        aplicados = 0
        for fname in TMS_APRENDER:
            rel = f"src/tm_compatibility/{fname}"
            p = self.path(self.dpe, rel)
            if not os.path.isfile(p):
                log(C.WARN, f"TM omitido (no existe): {fname}")
                continue
            with open(p, encoding="utf-8", errors="surrogateescape") as f:
                contenido = f.read()
            if "SHELLY" in contenido:
                continue
            if not contenido.endswith("\n"):
                contenido += "\n"
            self.backup(self.dpe, rel)
            self.write(self.dpe, rel, contenido + "SHELLY\n")
            aplicados += 1
        log(C.OK, f"TM compatibilidad: Shelly aprende {aplicados} TMs")

        # --- tutores (búsqueda flexible de nombre de archivo)
        carpeta = self.path(self.dpe, "src/tutor_compatibility")
        if os.path.isdir(carpeta):
            for tutor in TUTORES_APRENDER:
                archivo = None
                for f in os.listdir(carpeta):
                    base = f.lower()
                    if base.endswith(".txt") and \
                       base.split(".txt")[0].split("-", 1)[-1].strip() == tutor.lower():
                        archivo = f
                        break
                if not archivo:
                    log(C.WARN, f"Tutor omitido (no encontrado): {tutor}")
                    continue
                rel = f"src/tutor_compatibility/{archivo}"
                contenido = self.read(self.dpe, rel)
                if "SHELLY" in contenido:
                    continue
                if not contenido.endswith("\n"):
                    contenido += "\n"
                self.backup(self.dpe, rel)
                self.write(self.dpe, rel, contenido + "SHELLY\n")
                log(C.OK, f"Tutor: {archivo} -> Shelly")

        # --- sprites (assets -> graphics)
        assets = [
            (f"gFrontSprite{SPRITE_NUM}Shelly.png", "graphics/frontspr"),
            (f"gBackShinySprite{SPRITE_NUM}Shelly.png", "graphics/backspr"),
            (f"gIconSprite{SPRITE_NUM}Shelly.png", "graphics/pokeicon"),
        ]
        for fname, carpeta in assets:
            src = os.path.join(self.assets, fname)
            dst = self.path(self.dpe, f"{carpeta}/{fname}")
            if not os.path.isfile(src):
                self.errors.append(f"asset faltante: {fname} (¿--assets?)")
                continue
            if os.path.isfile(dst):
                if os.path.getsize(dst) == os.path.getsize(src) and \
                        open(dst, "rb").read() == open(src, "rb").read():
                    continue
                if not self.dry:
                    shutil.copy2(src, dst)
                log(C.OK, f"{carpeta}: {fname} actualizado a la versión nueva")
                continue
            if not self.dry:
                shutil.copy2(src, dst)
            log(C.OK, f"{carpeta}: {fname} copiado")

        # --- make.py: fix del bug de python3 (stub de Microsoft Store)
        self.fix_makepy(self.dpe)

    def fix_makepy(self, repo):
        rel = "scripts/make.py"
        content = self.read(repo, rel)
        if "SHELLY_FIX_PYTHON" in content:
            log(C.INFO, f"{repo}/make.py: fix python ya presente")
            return
        nuevo = content.replace(
            "def BuildCode():\n"
            "    if shutil.which('python3') is not None:\n"
            "        result = os.system(\"python3 scripts/build.py\")\n"
            "    else:\n"
            "        result = os.system(\"python scripts/build.py\")\n",
            "# SHELLY_FIX_PYTHON: usa el interprete actual (evita el stub de\n"
            "# la Microsoft Store, que responde \"no se encontro Python\").\n"
            "def BuildCode():\n"
            "    result = os.system('\"' + sys.executable + '\" scripts/build.py')\n",
        )
        nuevo = nuevo.replace(
            "def InsertCode():\n"
            "    if shutil.which('python3') is not None:\n"
            "        os.system(\"python3 scripts/insert.py\")\n"
            "    else:\n"
            "        os.system(\"python scripts/insert.py\")\n",
            "def InsertCode():\n"
            "    os.system('\"' + sys.executable + '\" scripts/insert.py')\n",
        )
        if "SHELLY_FIX_PYTHON" not in nuevo:
            log(C.WARN, f"{repo}/make.py: patrón inesperado; fix no aplicado"
                        " (puedes arreglarlo a mano: usa sys.executable)")
            return
        self.backup(repo, rel)
        self.write(repo, rel, nuevo)
        log(C.OK, f"{repo}/scripts/make.py: fix de python (sys.executable)")

    # --------------------------------------------------------- CFRU
    def parchear_cfru(self):
        encabezado("5/9 · Parcheando CFRU (límites, learnset, follower)")

        # --- include/constants/species.h
        rel = "include/constants/species.h"
        if self.already(self.cfru, rel):
            log(C.INFO, "CFRU species.h: SHELLY ya presente")
        else:
            self.sub(self.cfru, rel,
                     "#define NUM_SPECIES (SPECIES_GLIMMORA_MEGA + 1)",
                     f"#define SPECIES_SHELLY {hex(SPECIES_ID)}\n"
                     "#define NUM_SPECIES (SPECIES_SHELLY + 1)",
                     "especie + NUM_SPECIES")

        # --- src/config.h: NATIONAL_DEX_COUNT
        rel = "src/config.h"
        contenido = self.read(self.cfru, rel)
        m = re.search(r"#define NATIONAL_DEX_COUNT\s+(\d+)", contenido)
        if not m:
            self.errors.append("CFRU config.h: NATIONAL_DEX_COUNT no encontrado")
        else:
            nuevo_valor = NATIONAL_DEX + 1
            if int(m.group(1)) >= nuevo_valor:
                log(C.INFO, f"CFRU config.h: NATIONAL_DEX_COUNT ya es {m.group(1)}")
            else:
                self.sub(self.cfru, rel, m.group(0),
                         f"#define NATIONAL_DEX_COUNT {nuevo_valor}",
                         f"NATIONAL_DEX_COUNT {m.group(1)} → {nuevo_valor}")

        # --- src/Tables/level_up_learnsets.c
        rel = "src/Tables/level_up_learnsets.c"
        if self.already(self.cfru, rel):
            log(C.INFO, "CFRU learnsets: SHELLY ya presente")
        else:
            learnset_txt = ",\n".join(
                f"\tLEVEL_UP_MOVE({lvl:2d}, {mv})" for lvl, mv in LEARNSET)
            arr = (
                "static const struct LevelUpMove sShellyLevelUpLearnset[] = {\n"
                + learnset_txt + ",\n\tLEVEL_UP_END\n};\n\n"
            )
            self.insert_before(
                self.cfru, rel,
                "static const struct LevelUpMove sBulbasaurLevelUpLearnset[] = {",
                arr, "array sShellyLevelUpLearnset (CFRU)")
            self.sub(self.cfru, rel,
                     "\t[SPECIES_CALYREX_ICE_RIDER] = sCalyrexIceRiderLevelUpLearnset,",
                     "\t[SPECIES_CALYREX_ICE_RIDER] = sCalyrexIceRiderLevelUpLearnset,\n"
                     "\t[SPECIES_SHELLY] = sShellyLevelUpLearnset,",
                     "entrada en tabla gLevelUpLearnsets (CFRU)")

        # --- src/Tables/follower_mon_sprites.c
        rel = "src/Tables/follower_mon_sprites.c"
        if self.already(self.cfru, rel):
            log(C.INFO, "CFRU follower: SHELLY ya presente")
        else:
            self.sub(self.cfru, rel,
                     "[SPECIES_PALKIA_ORIGIN] = EVENT_OBJ_GFX_PALKIA,",
                     "[SPECIES_PALKIA_ORIGIN] = EVENT_OBJ_GFX_PALKIA,\n"
                     f"    [SPECIES_SHELLY] = {FOLLOWER_GFX},",
                     f"follower: Shelly camina como {FOLLOWER_GFX}")

        # --- make.py fix
        self.fix_makepy(self.cfru)

    # ---------------------------------------- pasiva «Vientre Divino»
    def parchear_pasiva_dpe(self):
        encabezado("6/9 · Pasiva Vientre Divino — DPE (ability 317)")

        # --- include/abilities.h: ID 317 + ABILITIES_COUNT 318
        rel = "include/abilities.h"
        if self.already(self.dpe, rel, "ABILITY_VIENTRE_DIVINO"):
            log(C.INFO, "abilities.h: VIENTRE_DIVINO ya presente (omitido)")
        else:
            self.sub(self.dpe, rel,
                     "#define ABILITY_SPICY_SPRAY                          316",
                     "#define ABILITY_SPICY_SPRAY                          316\n"
                     "#define ABILITY_VIENTRE_DIVINO                      317",
                     "ABILITY_VIENTRE_DIVINO = 317")
            self.sub(self.dpe, rel,
                     "#define ABILITIES_COUNT                              317",
                     "#define ABILITIES_COUNT                              318",
                     "ABILITIES_COUNT 317 -> 318")

        # --- scripts/build.py: la pasiva es >255 -> lista canónica 16 bits
        rel = "scripts/build.py"
        if self.already(self.dpe, rel, "ABILITY_VIENTRE_DIVINO"):
            log(C.INFO, "build.py: ya figura en CANONICAL_U16_ABILITIES (omitido)")
        else:
            self.insert_after(self.dpe, rel, "CANONICAL_U16_ABILITIES = {",
                              "\n    'ABILITY_VIENTRE_DIVINO',",
                              "ABILITY_VIENTRE_DIVINO en CANONICAL_U16_ABILITIES")

        # --- src/Base_Stats.c: migrar la pasiva aunque ya estuviera instalada
        self.sub_desde_marca(
            self.dpe, "src/Base_Stats.c", "[SPECIES_SHELLY] =",
            ".ability1 = ABILITY_CUTECHARM,",
            ".ability1 = ABILITY_VIENTRE_DIVINO,",
            "ability1 de Shelly -> VIENTRE_DIVINO", required=False)
        self.sub_desde_marca(
            self.dpe, "src/Base_Stats.c", "[SPECIES_SHELLY] =",
            ".hiddenAbility = ABILITY_SERENEGRACE,",
            ".hiddenAbility = ABILITY_NONE,",
            "hiddenAbility de Shelly -> NONE", required=False)

    def parchear_pasiva_cfru(self):
        encabezado("7/9 · Pasiva Vientre Divino — CFRU (mecánica en el motor)")
        R = self.cfru

        # --- include/constants/abilities.h: ID 317 + ABILITIES_COUNT 318
        rel = "include/constants/abilities.h"
        if self.already(R, rel, "ABILITY_VIENTRE_DIVINO"):
            log(C.INFO, "abilities.h: VIENTRE_DIVINO ya presente (omitido)")
        else:
            self.sub(R, rel,
                     "#define ABILITY_SPICY_SPRAY                          316",
                     "#define ABILITY_SPICY_SPRAY                          316\n"
                     "#define ABILITY_VIENTRE_DIVINO                      317",
                     "ABILITY_VIENTRE_DIVINO = 317")
            self.sub(R, rel,
                     "#define ABILITIES_COUNT                              317",
                     "#define ABILITIES_COUNT                              318",
                     "ABILITIES_COUNT 317 -> 318")

        # --- strings/ability_name_table.string: registro 317 (¡el orden
        #     de los #org ES el índice del array!; va antes del marcador)
        rel = "strings/ability_name_table.string"
        if not self.already(R, rel, "NAME_ABILITY_317"):
            self.insert_before(R, rel, "#org @NAME_LAST_ABILITY",
                               "#org @NAME_ABILITY_317_VIENTRE_DIVINO\n"
                               + NOMBRE_PASIVA + "\n\n",
                               "nombre de la pasiva (registro 317)")

        # --- strings/ability_descriptions.string + tabla de punteros .s
        rel = "strings/ability_descriptions.string"
        if not self.already(R, rel, "DESC_VIENTRE_DIVINO"):
            self.append(R, rel,
                        "\n#org @DESC_VIENTRE_DIVINO\n" + DESC_PASIVA_ES + "\n",
                        "descripción de la pasiva")
        rel = "assembly/data/ability_description_table.s"
        if not self.already(R, rel, "DESC_VIENTRE_DIVINO"):
            self.append(R, rel,
                        ".word DESC_VIENTRE_DIVINO                           "
                        "@ 317 ABILITY_VIENTRE_DIVINO\n",
                        "puntero 317 en la tabla de descripciones")

        # --- strings/ability_strings.string: textos de batalla en español
        rel = "strings/ability_strings.string"
        if not self.already(R, rel, "gText_VientreDivinoReflejo"):
            trozo = ""
            for etiqueta, texto in TEXTOS_BATALLA_ES:
                trozo += "\n#org @%s\n%s\n" % (etiqueta, texto)
            self.append(R, rel, trozo, "textos de batalla de la pasiva (5)")
        else:
            # v1.4: migración del typo «refleó» en repos parcheados con v1.1+
            self.sub(R, rel, "refleó", "reflejó",
                     "migración v1.4: typo «refleó» -> «reflejó»",
                     required=False)

        # --- include/battle.h: turnos de «aplanada» en NewBattleStruct
        #     (Calloc por batalla -> se limpia solo)
        rel = "include/battle.h"
        if not self.already(R, rel, "shellyAplanada"):
            self.insert_after(R, rel, "    } midBattleEvolution;",
                              "\n\n    // SHELLY MODULE: turnos restantes de aplanada\n"
                              "    // (pasiva Vientre Divino, solo SPECIES_SHELLY)\n"
                              "    u8 shellyAplanada[MAX_BATTLERS_COUNT];",
                              "campo shellyAplanada en NewBattleStruct")

        # --- src/accuracy_calc.c: esquiva el 65% de TODOS los movimientos
        #     (ataques y movimientos de estado; los que «siempre aciertan»
        #     del original se colocan después y la siguen acertando)
        rel = "src/accuracy_calc.c"
        if not self.already(R, rel, "ShellyEsPirataDivina"):
            self.insert_before(
                R, rel,
                "\tif (gBattleMoves[move].accuracy == 0) //Always hit",
                "\t{ // SHELLY MODULE: Vientre Divino esquiva el 65% de TODOS los\n"
                "\t  // movimientos, incluidos los de estado (Hipnosis, Rayo, Toxic...).\n"
                "\t\textern bool8 ShellyEsPirataDivina(u8 bank);\n"
                "\t\tif (ShellyEsPirataDivina(bankDef))\n"
                "\t\t\tcalc = udivsi((calc * 35), 100);\n"
                "\t}\n"
                "\n",
                "esquiva del 65% en el cálculo de precisión")

        # --- src/damage_calc.c: congelada, un 25% de los daños = 0
        rel = "src/damage_calc.c"
        if not self.already(R, rel, "VIENTRE_DIVINO"):
            self.insert_after(
                R, rel,
                "\t\tu16 item = ITEM(bankDef);\n"
                "\t\tu8 itemEffect = ITEM_EFFECT(bankDef);\n"
                "\t\tu8 itemQuality = ITEM_QUALITY(bankDef);\n"
                "\t\tability_t defAbility = ABILITY(bankDef);",
                "\n\n           // SHELLY MODULE: mientras Shelly está congelada, un 25% de los\n"
                "               // daños que recibe se anulan por completo (vientre divino).\n"
                "               if (defAbility == ABILITY_VIENTRE_DIVINO\n"
                "               && (gBattleMons[bankDef].status1 & STATUS1_FREEZE)\n"
                "               && damage > 0\n"
                "               && Random() % 100 < 25)\n"
                "                       damage = 0;",
                "inmunidad del 25% mientras está congelada")

        # --- src/ability_battle_effects.c: externs + case + rating + helpers
        rel = "src/ability_battle_effects.c"
        if not self.already(R, rel, "SHELLY MODULE: externs de la pasiva"):
            self.insert_after(
                R, rel,
                '#include "../include/new/terastallization.h"',
                "\n\n// SHELLY MODULE: externs de la pasiva Vientre Divino (ability 317)\n"
                "extern const u8 gText_VientreDivinoReflejo[];\n"
                "extern const u8 gText_VientreDivinoBurbuja[];\n"
                "extern const u8 gText_VientreDivinoBurbujaFin[];\n"
                "extern const u8 gText_VientreDivinoAplanadaGolpe[];\n"
                "extern const u8 gText_VientreDivinoAplanadaTurno[];\n"
                "extern const u8 BattleScript_ShellyRefleja[];\n"
                "extern const u8 BattleScript_ShellyAplanada[];\n"
                "extern const u8 BattleScript_PrintCustomString[];\n"
                "bool8 ShellyEsPirataDivina(u8 bank);\n"
                "bool8 ShellyEsBurbuja(u8 bank);\n"
                "const u8* ShellyBurbujaFinScript(u8 bank);\n"
                "bool8 ShellyTryAplanada(u8 bank);\n"
                "void ShellyVientreDivinoAlSerGolpeada(u8 bank, u16 move);\n",
                "externs de la pasiva")
        if not self.already(R, rel, "case ABILITY_VIENTRE_DIVINO:"):
            self.insert_before(
                R, rel,
                "\t\t\tcase ABILITY_STAMINA:",
                "\t\t\tcase ABILITY_VIENTRE_DIVINO: // SHELLY: Vientre Divino\n"
                "\t\t\t\tif (MOVE_HAD_EFFECT\n"
                "\t\t\t\t&& TOOK_DAMAGE(bank))\n"
                "\t\t\t\t\tShellyVientreDivinoAlSerGolpeada(bank, move);\n"
                "\t\t\t\tbreak;\n"
                "\n",
                "case VIENTRE_DIVINO en el dispatcher de contacto")
        if not self.already(R, rel, "[ABILITY_VIENTRE_DIVINO] = 10,"):
            self.insert_after(R, rel, "\t[ABILITY_SERENEGRACE] = 8,",
                              "\n\t[ABILITY_VIENTRE_DIVINO] = 10,",
                              "rating 10 para la IA")
        if not self.already(R, rel, "SHELLY:HELPERS VIENTRE DIVINO"):
            self.append(R, rel, AYUDANTES_C,
                        "funciones de la pasiva (Vientre Divino)")

        # --- src/end_turn.c: la burbuja no daña por turnos + mensaje propio
        rel = "src/end_turn.c"
        if not self.already(R, rel, "ShellyEsBurbuja"):
            self.insert_after(
                R, rel,
                '#include "../include/new/util.h"',
                "\n\n// SHELLY MODULE: pasiva Vientre Divino\n"
                "extern bool8 ShellyEsBurbuja(u8 bank);\n"
                "extern const u8* ShellyBurbujaFinScript(u8 bank);\n",
                "prototipos de la pasiva en end_turn")
            self.sub(R, rel,
                     "if (ABILITY(gActiveBattler) != ABILITY_MAGICGUARD)\n"
                     "\t\t\t\t\t{\n"
                     "\t\t\t\t\t\t//Damaged by wrap",
                     "if (ABILITY(gActiveBattler) != ABILITY_MAGICGUARD\n"
                     "\t\t\t\t\t&& !ShellyEsBurbuja(gActiveBattler)) // SHELLY: burbuja sin dano\n"
                     "\t\t\t\t\t{\n"
                     "\t\t\t\t\t\t//Damaged by wrap",
                     "la burbuja no causa daño por turnos")
            self.sub(R, rel,
                     "\t\t\t\t\tgBattlescriptCurrInstr = BattleScript_WrapEnds;",
                     BURBUJA_FIN_V12,
                     "mensaje propio al romperse la burbuja (if/else v1.2)")

        # --- src/attackcanceler.c: pierde el turno mientras está aplanada
        rel = "src/attackcanceler.c"
        if not self.already(R, rel, "ShellyTryAplanada"):
            self.insert_after(
                R, rel,
                '#include "../include/new/util.h"',
                "\n\n// SHELLY MODULE: pasiva Vientre Divino\n"
                "extern bool8 ShellyTryAplanada(u8 bank);\n",
                "prototipo de aplanada en attackcanceler")
            self.sub(R, rel,
                     "case CANCELLER_FLINCH: // flinch\n"
                     "\t\t\tif (gBattleMons[gBankAttacker].status2 & STATUS2_FLINCHED && !IsDynamaxed(gBankAttacker))",
                     "case CANCELLER_FLINCH: // flinch\n"
                     "\t\t\tif (ShellyTryAplanada(gBankAttacker)) // SHELLY: aplanada pierde el turno\n"
                     "\t\t\t{\n"
                     "\t\t\t\tgProtectStructs[gBankAttacker].flinchImmobility = 1;\n"
                     "\t\t\t\tCancelMultiTurnMoves(gBankAttacker);\n"
                     "\t\t\t\tgHitMarker |= HITMARKER_UNABLE_TO_USE_MOVE;\n"
                     "\t\t\t\teffect = 1;\n"
                     "\t\t\t}\n"
                     "\t\t\telse if (gBattleMons[gBankAttacker].status2 & STATUS2_FLINCHED && !IsDynamaxed(gBankAttacker))",
                     "rama de aplanada en CANCELLER_FLINCH")

        # --- assembly: battle scripts del reflejo y de aplanada
        rel = "assembly/battle_scripts/ability_battle_scripts.s"
        if not self.already(R, rel, "BattleScript_ShellyRefleja:"):
            self.append(R, rel,
                        "\n.align 2\n"
                        "@ SHELLY MODULE: el vientre divino refleja el dano al atacante\n"
                        ".global BattleScript_ShellyRefleja\n"
                        "BattleScript_ShellyRefleja:\n"
                        "\tcall BattleScript_AbilityPopUp\n"
                        "\torword HIT_MARKER, HITMARKER_IGNORE_SUBSTITUTE | HITMARKER_NON_ATTACK_DMG\n"
                        "\thealthbarupdate BANK_ATTACKER\n"
                        "\tdatahpupdate BANK_ATTACKER\n"
                        "\tprintstring 0x184\n"
                        "\twaitmessage DELAY_1SECOND\n"
                        "\tcall BattleScript_AbilityPopUpRevert\n"
                        "\tfaintpokemon BANK_ATTACKER 0x0 0x0\n"
                        "\treturn\n",
                        "script del reflejo (BattleScript_ShellyRefleja)")
        rel = "assembly/battle_scripts/attackcanceler_battle_scripts.s"
        if not self.already(R, rel, "BattleScript_ShellyAplanada:"):
            self.append(R, rel,
                        "\n.align 2\n"
                        "@ SHELLY MODULE: aplanada, no puede moverse este turno\n"
                        ".global BattleScript_ShellyAplanada\n"
                        "BattleScript_ShellyAplanada:\n"
                        "\tprintstring 0x184\n"
                        "\twaitmessage DELAY_1SECOND\n"
                        "\tgoto BS_MOVE_END\n",
                        "script de aplanada (BattleScript_ShellyAplanada)")

    # ------------------------------------- inicial al arrancar (v1.4)
    def parchear_inicial_cfru(self):
        """v1.4 — Shelly como inicial, COMPILADA DENTRO DE LA ROM.

        El evento de entrega deja de ser un parche sobre la ROM final y
        pasa a vivir en los archivos del propio CFRU:
          * src/shelly_module.c            (disparo: ShellyTryArrival)
          * assembly/overworld_scripts/shelly_inicial.s  (evento)
          * strings/Scripts/shelly_inicial.string         (mensaje)
          * src/overworld.c                (llamada desde el hook del motor)
          * asm_defines.s                  (.equ SPECIES_SHELLY para el .s)
        El make.py del CFRU los compila y enlaza solos (build.py usa
        glob sobre src/**, assembly/** y strings/**), así que la ROM
        sale con el inicial integrado y NO se toca nada tras compilar.
        """
        encabezado("8/9 · Inicial de Shelly — CFRU (compilada dentro de la ROM)")
        R = self.cfru

        # --- asm_defines.s: SPECIES_SHELLY visible para los scripts .s
        rel = "asm_defines.s"
        if not self.already(R, rel, ".equ SPECIES_SHELLY,"):
            self.append(R, rel,
                        "\n" + f".equ SPECIES_SHELLY, {hex(SPECIES_ID)}\n",
                        ".equ SPECIES_SHELLY en asm_defines.s")

        # --- src/shelly_module.c (archivo NUEVO; se sobrescribe si difiere)
        rel = "src/shelly_module.c"
        existe = os.path.isfile(self.path(R, rel))
        if existe:
            actual = self.read(R, rel)
            if actual != ARCHIVO_C_INICIAL:
                self.backup(R, rel)
                self.write(R, rel, ARCHIVO_C_INICIAL)
                log(C.OK, f"{rel}: actualizado (v1.4)")
            else:
                log(C.INFO, f"{rel}: ya está al día (omitido)")
        else:
            self.write(R, rel, ARCHIVO_C_INICIAL)
            log(C.OK, f"{rel}: creado (disparo del evento de llegada)")

        # --- assembly/overworld_scripts/shelly_inicial.s (NUEVO)
        rel = "assembly/overworld_scripts/shelly_inicial.s"
        existe = os.path.isfile(self.path(R, rel))
        if existe:
            actual = self.read(R, rel)
            if actual != ARCHIVO_S_INICIAL:
                self.backup(R, rel)
                self.write(R, rel, ARCHIVO_S_INICIAL)
                log(C.OK, f"{rel}: actualizado (v1.4)")
            else:
                log(C.INFO, f"{rel}: ya está al día (omitido)")
        else:
            self.write(R, rel, ARCHIVO_S_INICIAL)
            log(C.OK, f"{rel}: creado (evento givepokemon nv.5 + fanfarria)")

        # --- strings/Scripts/shelly_inicial.string (NUEVO)
        rel = "strings/Scripts/shelly_inicial.string"
        existe = os.path.isfile(self.path(R, rel))
        if existe:
            actual = self.read(R, rel)
            if actual != ARCHIVO_STRING_INICIAL:
                self.backup(R, rel)
                self.write(R, rel, ARCHIVO_STRING_INICIAL)
                log(C.OK, f"{rel}: actualizado (v1.4)")
            else:
                log(C.INFO, f"{rel}: ya está al día (omitido)")
        else:
            self.write(R, rel, ARCHIVO_STRING_INICIAL)
            log(C.OK, f"{rel}: creado (mensaje de llegada en español)")

        # --- src/overworld.c: llamar a ShellyTryArrival desde el hook del
        #     motor TryRunOnFrameMapScript (que la propia CFRU ya reescribe)
        rel = "src/overworld.c"
        if self.already(R, rel, "ShellyTryArrival"):
            log(C.INFO, "overworld.c: llamada a ShellyTryArrival ya presente")
        else:
            ancla = ("bool8 TryRunOnFrameMapScript(void)\n"
                     "{\n"
                     "\tTryUpdateSwarm();\n")
            if ancla not in self.read(R, rel):
                self.errors.append(
                    "overworld.c: no se encontró TryRunOnFrameMapScript "
                    "con TryUpdateSwarm (¿versión distinta del CFRU?)")
            else:
                self.insert_after(
                    R, rel, ancla,
                    "\n"
                    "\t// SHELLY MODULE v1.4: Shelly llega a tu cuarto la "
                    "primera vez\n"
                    "\t// (flag 0x2AE + EventScript_ShellyArrival; ver "
                    "src/shelly_module.c).\n"
                    "\textern bool8 ShellyTryArrival(void);\n"
                    "\tif (ShellyTryArrival())\n"
                    "\t\treturn TRUE;\n",
                    "llamada al evento en TryRunOnFrameMapScript")

    # --------------------------------------------------------- v1.2 migración
    def migrar_v11(self):
        """v1.1 → v1.2: repara repos ya parcheados por el módulo v1.1.

        En v1.1, ShellyBurbujaFinScript() devolvía BattleScript_WrapEnds
        como fallback y lo declaraba extern en ability_battle_effects.c.
        En este CFRU ese nombre es una MACRO a una dirección fija de la
        ROM (end_turn_battle_scripts.h), no un símbolo, y el enlazador
        fallaba con «undefined reference to BattleScript_WrapEnds».
        v1.2 deja la decisión (burbuja vs wrap normal) en end_turn.c,
        donde la macro sí existe, y la función de Shelly deja de
        referenciar símbolos ajenos.
        """
        R = self.cfru
        rel1 = "src/ability_battle_effects.c"
        rel2 = "src/end_turn.c"

        # (1) retirar el extern problemático (línea completa)
        viejo_extern = "extern const u8 BattleScript_WrapEnds[];\n"
        if viejo_extern in self.read(R, rel1):
            self.sub(R, rel1, viejo_extern,
                     "// (v1.2) BattleScript_WrapEnds no va aquí: es una macro a\n"
                     "// una dirección fija de la ROM (end_turn_battle_scripts.h).\n",
                     "extern de BattleScript_WrapEnds retirado (v1.2)")

        # (2) reemplazar la función completa por la versión sin externos ajenos
        funcion_v11 = ("const u8* ShellyBurbujaFinScript(u8 bank)\n"
                       "{\n"
                       "\tif (ShellyEsBurbuja(bank))\n"
                       "\t{\n"
                       "\t\tgBattleStringLoader = gText_VientreDivinoBurbujaFin;\n"
                       "\t\treturn BattleScript_PrintCustomString;\n"
                       "\t}\n"
                       "\treturn BattleScript_WrapEnds;\n"
                       "}\n")
        funcion_v12 = ("const u8* ShellyBurbujaFinScript(u8 bank)\n"
                       "{\n"
                       "\t// v1.2: solo se invoca cuando ShellyEsBurbuja(bank) ya es\n"
                       "\t// cierto (la decisión vive en end_turn.c, donde la macro\n"
                       "\t// BattleScript_WrapEnds sí existe; aquí no es un símbolo).\n"
                       "\t(void)bank;\n"
                       "\tgBattleStringLoader = gText_VientreDivinoBurbujaFin;\n"
                       "\treturn BattleScript_PrintCustomString;\n"
                       "}\n")
        if funcion_v11 in self.read(R, rel1):
            self.sub(R, rel1, funcion_v11, funcion_v12,
                     "ShellyBurbujaFinScript reparada (v1.2, sin WrapEnds externo)")

        # (3) end_turn.c: la línea única de v1.1 pasa a if/else con la macro
        linea_v11 = ("\t\t\t\t\tgBattlescriptCurrInstr = "
                     "ShellyBurbujaFinScript(gActiveBattler);")
        if linea_v11 in self.read(R, rel2):
            self.sub(R, rel2, linea_v11, BURBUJA_FIN_V12,
                     "fin de burbuja con if/else y macro local (v1.2)")

    # --------------------------------------------------------- resumen
    def resumen(self):
        encabezado("9/9 · Resumen")
        print(f"  Archivos modificados : {len(self.modified)}")
        print(f"  Respaldos creados    : {len(self.backups)} (en .shelly_backup/)")
        if self.errors:
            print(f"  Errores              : {len(self.errors)}")
            for e in self.errors:
                print(f"    - {e}")
        print()
        if self.dry:
            print("  [MODO SIMULACIÓN] No se escribió nada en disco.")
            return len(self.errors) == 0
        if self.errors:
            print("  Hay errores. Revisa los mensajes [ERROR] de arriba.")
            print("  Puedes restaurar con: python install_shelly.py --restore ...")
            return False
        print("  ¡Shelly instalada! 🏴‍☠️")
        print("  Pasiva «Vientre Divino» integrada (esquiva 65%, refleja 45%,")
        print("  congelada 25% inmune; burbuja 3-6 turnos y aplanada 3-5).")
        print("  Inicial COMPILADA DENTRO DE LA ROM (v1.4): al entrar por")
        print("  primera vez a tu cuarto, Shelly llega con fanfarria y mensaje.")
        print("  Siguiente paso: compila con CFRU-Builder (paso DPE → CFRU).")
        print("  La ROM final ya sale completa: NO se parchea nada después.")
        return True

    def restaurar(self):
        encabezado("Restaurando respaldos")
        base = os.path.join(self.dpe, ".shelly_backup")
        base2 = os.path.join(self.cfru, ".shelly_backup")
        for raiz in {base, base2}:
            if not os.path.isdir(raiz):
                log(C.WARN, f"{raiz}: no hay respaldos")
                continue
            for ts in sorted(os.listdir(raiz)):
                carpeta = os.path.join(raiz, ts)
                for fname in os.listdir(carpeta):
                    repos = self.dpe if "species.h__" != fname else None
                    # los nombres guardan el repo por el orden: probar ambos
                    dst_candidates = []
                    for repo in (self.dpe, self.cfru):
                        rel = fname.replace("__", "/")
                        if os.path.isfile(os.path.join(repo, rel)):
                            dst_candidates.append(os.path.join(repo, rel))
                    src = os.path.join(carpeta, fname)
                    if not dst_candidates:
                        continue
                    shutil.copy2(src, dst_candidates[0])
                    print(f"  restaurado: {dst_candidates[0]}")
        # quitar sprites copiados
        for fname in (f"gFrontSprite{SPRITE_NUM}Shelly.png",
                      f"gBackShinySprite{SPRITE_NUM}Shelly.png",
                      f"gIconSprite{SPRITE_NUM}Shelly.png"):
            for carpeta in ("graphics/frontspr", "graphics/backspr",
                            "graphics/pokeicon"):
                p = self.path(self.dpe, f"{carpeta}/{fname}")
                if os.path.isfile(p):
                    os.remove(p)
                    print(f"  eliminado: {p}")
        # v1.4: quitar los archivos NUEVOS del inicial (no existen en los
        # respaldos porque no venían con el CFRU limpio)
        for rel in ("src/shelly_module.c",
                    "assembly/overworld_scripts/shelly_inicial.s",
                    "strings/Scripts/shelly_inicial.string",
                    "strings/Scripts/shelly_inicial.s"):  # .s generado del .string
            p = self.path(self.cfru, rel)
            if os.path.isfile(p):
                os.remove(p)
                print(f"  eliminado: {p}")
        print("\n  Listo. (Los respaldos originales siguen en .shelly_backup/)")


def main():
    ap = argparse.ArgumentParser(
        description="Instalador del módulo Shelly para DPE Gen-9 + CFRU")
    ap.add_argument("--dpe", required=True,
                    help="ruta del repo Dynamic-Pokemon-Expansion-Gen-9-master")
    ap.add_argument("--cfru", required=True,
                    help="ruta del repo CFRU (CFRU-expansion)")
    ap.add_argument("--assets", default=os.path.join(
                        os.path.dirname(os.path.abspath(__file__)), "assets"),
                    help="carpeta con los PNG de Shelly (default: ./assets)")
    ap.add_argument("--dry-run", action="store_true",
                    help="simula sin escribir nada")
    ap.add_argument("--restore", action="store_true",
                    help="restaura los respaldos más recientes")
    args = ap.parse_args()

    print("╔" + "═" * 60 + "╗")
    print("║  🏴‍☠️  MÓDULO SHELLY — La Administradora como Pokémon   ║")
    print("╚" + "═" * 60 + "╝")

    inst = Installer(os.path.abspath(args.dpe), os.path.abspath(args.cfru),
                      os.path.abspath(args.assets), dry=args.dry_run)

    if args.restore:
        inst.restaurar()
        return

    if not inst.verificar():
        sys.exit(1)
    inst.parchear_dpe()
    inst.parchear_dpe_dex()
    inst.parchear_dpe_tms_sprites()
    inst.parchear_cfru()
    inst.parchear_pasiva_dpe()
    inst.parchear_pasiva_cfru()
    inst.parchear_inicial_cfru()
    inst.migrar_v11()
    ok = inst.resumen()
    sys.exit(0 if ok else 2)


if __name__ == "__main__":
    main()

