# Showdown-style trainer battles

Trainer overrides are stored in `src/Tables/trainers.party`. The format follows
Pokemon Showdown exports, with a short trainer header before each party.

```text
=== TRAINER_YOUNGSTER_BEN ===
Name: BEN
Class: Youngster
Pic: Youngster
Gender: Male
Music: Male
Items: Super Potion
Double Battle: No
AI: Check Bad Move / Check Good Move

Rattata (M) @ Oran Berry
Level: 12
Ability: Ability 1
Nature: Jolly
IVs: 31 HP / 31 Atk / 31 Def / 31 SpA / 31 SpD / 31 Spe
EVs: 0 HP / 252 Atk / 0 Def / 0 SpA / 4 SpD / 252 Spe
Tera Type: Normal
- Tackle
- Quick Attack
```

Only trainers present in this file are overridden. Their original definitions
remain in `trainer_data.c` and `trainer_parties.h`. Removing a block restores
the original battle after the generated headers are rebuilt.

Run the graphical editor with:

```bash
python3 useful_scripts/trainer_editor.py
```

The editor can import an existing C trainer, validate Showdown syntax, create
new trainer IDs and regenerate the C headers. The normal build also runs the
generator automatically. It can be run manually with:

```bash
python3 scripts/trainer_party.py build
```

## CFRU-specific limitations

This project's `TrainerMonItemCustomMoves` stores an ability slot rather than
an ability constant. Accepted values are `Hidden`, `Ability 1`, `Ability 2`,
`Random 1 2`, and `Random All`.

Ability, Nature, per-stat IV/EV spreads, and Tera Type require explicit moves
for every Pokemon in that trainer's party. `Ball`, `Shiny`, and `Happiness`
are rejected because they are not fields in this project's trainer structure.
