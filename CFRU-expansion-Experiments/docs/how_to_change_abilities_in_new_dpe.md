# How to Customize Species Abilities in the New DPE

The new DPE still uses `src/Base_Stats.c` as the main source for species abilities. During compilation, Python generates a separate 16-bit ability table for compatibility with the updated CFRU.

## Step 1: Open `Base_Stats.c`

Open:

```text
src/Base_Stats.c
```

Find the species you want to modify. For example:

```c
[SPECIES_EXAMPLE] =
{
    // Base stats and other data...

    .ability1 = ABILITY_DRIZZLE,
    .ability2 = ABILITY_HADRONENGINE,
    .hiddenAbility = ABILITY_ORICHALCUMPULSE,
},
```

The available slots are:

- `ability1`: the primary ability.
- `ability2`: the secondary ability.
- `hiddenAbility`: the hidden ability.

Use `ABILITY_NONE` when a slot should be empty.

## Step 2: Check the Override Table

Some species have special overrides in:

```text
scripts/build.py
```

Search for:

```python
SPECIES_ABILITY_OVERRIDES
```

If your species appears in this dictionary, its abilities from `Base_Stats.c` will be replaced during compilation.

Modify or remove its override entry. For example:

```python
'SPECIES_EXAMPLE': (
    'ABILITY_DRIZZLE',
    'ABILITY_HADRONENGINE',
    'ABILITY_ORICHALCUMPULSE',
),
```

The order is:

```text
Primary ability, secondary ability, hidden ability
```

## Step 3: Compile the DPE

Compile the project normally:

```bash
python3 scripts/make.py
```

The build script reads `src/Base_Stats.c` and automatically generates:

```text
src/generated/Base_Stats_Compat.c
src/generated/Species_Abilities.c
```

## Step 4: Do Not Edit Generated Files

Do not manually edit:

```text
src/generated/Species_Abilities.c
src/generated/Base_Stats_Compat.c
```

These files are recreated on every build, so manual changes will be overwritten.

## How the System Works

```text
src/Base_Stats.c
        |
        v
Python build generator
        |
        v
Base_Stats_Compat.c + Species_Abilities.c
```

`Base_Stats_Compat.c` preserves the original 8-bit base-stat structure.

`Species_Abilities.c` contains the complete 16-bit ability IDs required for abilities above `255`, such as Hadron Engine and Orichalcum Pulse.

## Recommended Workflow

1. Edit the abilities in `src/Base_Stats.c`.
2. Check `SPECIES_ABILITY_OVERRIDES` in `scripts/build.py`.
3. Update the override if the species is listed there.
4. Run `python3 scripts/make.py`.
5. Use the newly generated ROM for testing.
