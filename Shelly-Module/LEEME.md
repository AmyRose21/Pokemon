# 🏴‍☠️ Módulo Shelly v1.4.0 — La Administradora como Pokémon

> *"Existía una Poké Ball especial, con cualidades distintas a las demás.
> Shelly lo sabía... así que tuvo la grandiosa idea de usársela a sí misma
> por PC, siendo recibida por la protagonista del juego."*

Shelly (Team Aqua, Hoenn) se une a tu hack de FireRed como **Pokémon inicial**:
ya la tienes en el equipo apenas arranca la partida, en tu cuarto de Pallet.

## Nuevo en v1.4.0 — ADIÓS A LOS PARCHES: el inicial se COMPILA DENTRO de la ROM

Pedido directo de la jefa de proyecto: *«modifica eso directamente de los
archivos de DPE y CFRU, ya basta de parches»*. Hecho. El evento de entrega
dejó de ser un parche binario sobre la ROM compilada y ahora **vive en los
propios archivos del CFRU**, así que `make.py` lo compila y enlaza solo:

| Archivo del CFRU | Qué es |
|---|---|
| `src/shelly_module.c` | **El disparo.** `ShellyTryArrival()` detecta "estoy en tu cuarto (grupo 4, mapa 1) y el flag 0x2AE no está fijado" y lanza el evento. Se llama desde `TryRunOnFrameMapScript` (el hook del motor que la propia CFRU ya reescribe en `src/overworld.c`): el mismo mecanismo vanilla que las escenas de Oak en Pallet, seguro para mensajes con espera. |
| `assembly/overworld_scripts/shelly_inicial.s` | **El evento** `EventScript_ShellyArrival`: `givepokemon SPECIES_SHELLY 5`, candado, fanfarria de objeto recibido (MUS_OBTAIN_ITEM), mensaje y cierre con A/B. Sus bytes ensamblados son EXACTAMENTE la secuencia v1.2.1 verificada. |
| `strings/Scripts/shelly_inicial.string` | **El mensaje** `¡Recibiste a SHELLY!\n¡Tu aventura comienza!` en español (charmap del CFRU). |
| `asm_defines.s` | `.equ SPECIES_SHELLY, 0x5D1` para que el script .s pueda nombrarla. |

Ventajas:
- **Cero parches post-compilación.** La ROM final sale del `make.py` del CFRU
  con el inicial ya integrado. `parche_inicial.py` **fue eliminado** del módulo.
- **No puede fallar por mapas/warps.** Ya no se busca ni se edita ningún mapa
  de la ROM: la detección del cuarto es una comparación en C
  (`grupo 4, mapa 1` = tu 2F según `map_groups` de pokefirered), no una
  búsqueda binaria que pueda leer el warp equivocado (los bugs de v1.1–v1.3.1).
- **Migración automática.** Sobre repos ya parcheados con módulos
  anteriores: agrega los archivos nuevos, mete la llamada en
  `overworld.c` y de paso arregla el typo «refleó» → «reflejó» de la pasiva.
- **Verificado con el compilador real** (arm-none-eabi-gcc): los 109 .c del
  CFRU, 69 ensamblados y 41 .string compilan y ENLAZAN con el módulo puesto;
  los bytes del evento coinciden con la secuencia validada de v1.2.1.

**Qué hacer si vienes de v1.3.1 o antes:**
1. Actualiza esta carpeta `Shelly-Module` (reemplaza la vieja).
2. Recompila la cadena COMPLETA con CFRU-Builder (el instalador actualiza
   tus repos solo; no hace falta restaurar nada a mano).
3. **Borra el `.sav` viejo** del emulador (o deja que el builder lo separe
   como `.bak_`), porque la nueva ROM abre partidas nuevas.

> Si a una ROM vieja le habías aplicado el `parche_inicial.py` a mano, no la
> revientes: recompílate una limpia con este módulo. Las ROMs viejas y sus
> `.sav` son de otra era — no los mezcles con la nueva compilación.

## Cómo funciona el evento (para los curiosos)

1. Cada frame en el mundo exterior el motor llama
   `TryRunOnFrameMapScript()` — la CFRU ya lo reescribía para sus cosas
   (swarms, DexNav, Nuzlocke).
2. Ahora, además, llama a `ShellyTryArrival()`: si estás en **tu cuarto**
   (grupo 4, mapa 1), el flag **0x2AE** no está fijado y no se está
   reproduciendo el quest-log, fija el flag y lanza
   `EventScript_ShellyArrival` en el **contexto global** de scripts.
3. El evento te da a **Shelly nivel 5** (especie 0x5D1, con su pasiva
   «Vientre Divino» incluida), suena la fanfarria de objeto recibido y
   muestra el cartel «¡Recibiste a SHELLY!» hasta que lo cierres con A/B.
4. El flag 0x2AE queda grabado en el save: solo pasa UNA vez por partida.
   El flujo de Oak (elegir Bulbasaur/Charmander/Squirtle en el laboratorio)
   sigue 100% igual que en el juego original.

## Lo que trae el módulo (desde v1.0)

- **Especie 0x5D1 (1489)** / Pokédex nacional **1026** / tipo NORMAL /
  100% hembra / grito heredado de Jigglypuff.
- Sprites frontal + trasero shiny + icono de menú (32×64), generados desde
  su arte oficial ORAS.
- Stats (70/60/65/95/80/95), learnset pirata-caótica de 17 movimientos
  (Placaje → Voz Arrasadora), TMs y tutores.
- Entrada de Pokédex en español y follower (camina detrás de ti como LASS).
- **Pasiva «VIENTRE DIVINO»** (ability 317, exclusiva de Shelly):
  - Esquiva el **65%** de TODOS los movimientos (incluso los de estado).
  - Refleja el **45%** del daño recibido de vuelta al atacante.
  - Congelada: un **25%** de los daños que recibe se anulan por completo.
  - Burbuja/Burbuja Lente/Rayo Hielo y familia: **25%** de atraparla en una
    burbuja **3-6 turnos** (no puede huir ni cambiar; la burbuja no la daña).
  - Golpe Cuerpo/Placaje/Pisotón y familia: **25%** de aplanarla **3-5
    turnos** (no puede moverse mientras siga aplanada).
- Arreglo del bug de Windows «no se encontró Python» en los `make.py`.

## Uso

```bash
python install_shelly.py --dpe <ruta DPE-Gen9> --cfru <ruta CFRU>
```

Opciones: `--dry-run` (simular), `--restore` (desinstalar y volver al
estado limpio), `--assets <ruta>` (sprites, por defecto `./assets`).

- Es **IDEMPOTENTE**: reejecutarlo sobre repos ya parcheados no duplica
  nada (los archivos del inicial se escriben solo si difieren).
- Crea respaldos en `.shelly_backup/` dentro de cada repo antes de tocar.
- Tras instalar, compila con **CFRU-Builder** (paso DPE → paso CFRU) y
  juega: al crear tu partida, Shelly llega apenas sales de la cama.

## Historial de bugs resueltos (por si te los encuentras en foros)

- **v1.1** entregaba en la casa del RIVAL y congelaba el juego
  (level script `ON_LOAD` + flag fuera de rango). v1.3 lo reescribió.
- **v1.2** tenía un off-by-one leyendo el warp: "ESTE NO ES EL CUARTO DEL
  JUGADOR: abortando" — tu cuarto siempre fue el correcto. v1.3.1 lo corrigió.
- **v1.4** tira TODO ese mecanismo a la basura: nada de parches binarios,
  nada de warps, nada de level scripts inyectados. El evento es código C +
  ensamblado del propio CFRU, compilado dentro de la ROM por `make.py`.
