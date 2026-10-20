#!/usr/bin/env python3
"""Generate CFRU trainer overrides from Pokemon Showdown-style party files."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PARTY_FILE = ROOT / "src" / "Tables" / "trainers.party"
PARTIES_OUT = ROOT / "src" / "Tables" / "trainer_showdown_parties.h"
TRAINERS_OUT = ROOT / "src" / "Tables" / "trainer_showdown_overrides.h"

TRAINER_FIELDS = ("Name", "Class", "Pic", "Gender", "Music", "Items", "Double Battle", "AI")
MON_FIELDS = ("Level", "Ability", "IVs", "EVs", "CFRU IV", "Ball", "Happiness", "Nature", "Shiny", "Tera Type")
STATS = ("HP", "Atk", "Def", "SpA", "SpD", "Spe")
STAT_ALIASES = {"hp": 0, "atk": 1, "attack": 1, "def": 2, "defense": 2,
                "spa": 3, "spatk": 3, "spattack": 3, "spd": 4,
                "spdef": 4, "spdefense": 4, "spe": 5, "speed": 5}


class PartyError(RuntimeError):
    pass


@dataclass
class Pokemon:
    title: str
    fields: dict[str, str] = field(default_factory=dict)
    moves: list[str] = field(default_factory=list)


@dataclass
class Trainer:
    trainer_id: str
    fields: dict[str, str] = field(default_factory=dict)
    pokemon: list[Pokemon] = field(default_factory=list)


def strip_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def parse(text: str) -> list[Trainer]:
    text = strip_comments(text)
    headers = list(re.finditer(r"(?m)^===\s+(TRAINER_[A-Z0-9_]+)\s+===\s*$", text))
    result: list[Trainer] = []
    seen: set[str] = set()
    for number, header in enumerate(headers):
        trainer_id = header.group(1)
        if trainer_id in seen:
            raise PartyError(f"Duplicate trainer block: {trainer_id}")
        seen.add(trainer_id)
        end = headers[number + 1].start() if number + 1 < len(headers) else len(text)
        chunks = re.split(r"\n\s*\n", text[header.end():end].strip())
        trainer = Trainer(trainer_id)
        if chunks and chunks[0]:
            for line in chunks[0].splitlines():
                if ":" not in line:
                    raise PartyError(f"{trainer_id}: invalid trainer field: {line}")
                key, value = line.split(":", 1)
                trainer.fields[key.strip()] = value.strip()
        for chunk in chunks[1:]:
            lines = [line.strip() for line in chunk.splitlines() if line.strip()]
            if not lines:
                continue
            mon = Pokemon(lines[0])
            for line in lines[1:]:
                if line.startswith("- "):
                    mon.moves.append(line[2:].strip())
                elif ":" in line:
                    key, value = line.split(":", 1)
                    mon.fields[key.strip()] = value.strip()
                else:
                    raise PartyError(f"{trainer_id} / {mon.title}: invalid line: {line}")
            trainer.pokemon.append(mon)
        result.append(trainer)
    return result


def normalized(value: str) -> str:
    value = re.sub(r"^(SPECIES|MOVE|ITEM|ABILITY|NATURE|TYPE|BALL|CLASS|TRAINER_PIC|TRAINER_ENCOUNTER_MUSIC|AI_SCRIPT)_", "", value.strip(), flags=re.I)
    return re.sub(r"[^A-Z0-9]", "", value.upper())


class Symbols:
    FILES = {
        "species": ("include/constants/species.h", "SPECIES_"),
        "move": ("include/constants/moves.h", "MOVE_"),
        "item": ("include/constants/items.h", "ITEM_"),
        "ability": ("include/constants/abilities.h", "ABILITY_"),
        "nature": ("include/constants/pokemon.h", "NATURE_"),
        "type": ("include/constants/pokemon.h", "TYPE_"),
        "ball": ("include/constants/items.h", "ITEM_"),
        "class": ("include/constants/trainer_classes.h", "CLASS_"),
        "pic": ("include/constants/trainers.h", "TRAINER_PIC_"),
        "music": ("include/constants/trainers.h", "TRAINER_ENCOUNTER_MUSIC_"),
        "ai": ("include/constants/battle_ai.h", "AI_SCRIPT_"),
        "trainer": ("src/Tables/trainer_defines.h", "TRAINER_"),
    }

    def __init__(self, root: Path = ROOT):
        self.root = root
        self.maps: dict[str, dict[str, str]] = {}
        for kind, (relative, prefix) in self.FILES.items():
            text = (root / relative).read_text(encoding="utf-8")
            if kind == "ai":
                text += "\n" + (root / "include/battle.h").read_text(encoding="utf-8")
            names = re.findall(rf"\b({re.escape(prefix)}[A-Z0-9_]+)\b", text)
            mapping: dict[str, str] = {}
            for name in names:
                mapping.setdefault(normalized(name), name)
                mapping[name] = name
            self.maps[kind] = mapping

    def get(self, kind: str, value: str, default: str | None = None) -> str:
        value = value.strip()
        if not value and default is not None:
            return default
        found = self.maps[kind].get(value) or self.maps[kind].get(normalized(value))
        if found:
            return found
        raise PartyError(f"Unknown {kind}: {value}")


def pokemon_title(mon: Pokemon) -> tuple[str, str]:
    title = mon.title.strip()
    item = title.split("@", 1)[1].strip() if "@" in title else ""
    species_part = title.split("@", 1)[0].strip()
    species_part = re.sub(r"\s+\([MF]\)\s*$", "", species_part)
    match = re.search(r"\((SPECIES_[A-Z0-9_]+)\)", species_part)
    if match:
        species = match.group(1)
    else:
        nickname_match = re.search(r"\(([^)]+)\)\s*$", species_part)
        species = nickname_match.group(1) if nickname_match else species_part
    return species, item


def stat_spread(value: str, default: int) -> list[int]:
    spread = [default] * 6
    if not value.strip():
        return spread
    for part in value.split("/"):
        match = re.fullmatch(r"\s*(\d+)\s+([A-Za-z]+)\s*", part)
        if not match or match.group(2).lower() not in STAT_ALIASES:
            raise PartyError(f"Invalid stat spread component: {part.strip()}")
        spread[STAT_ALIASES[match.group(2).lower()]] = int(match.group(1))
    return spread


def c_name(name: str) -> str:
    tokens = []
    aliases = {" ": "_SPACE", "-": "_HYPHEN", ".": "_PERIOD", "'": "_APOSTROPHE"}
    for char in name[:11]:
        if char.isascii() and char.isalnum():
            tokens.append("_" + char)
        elif char in aliases:
            tokens.append(aliases[char])
        else:
            raise PartyError(f"Trainer name contains an unsupported character: {char!r}")
    tokens.append("_END")
    return "{" + ", ".join(tokens) + "}"


def party_symbol(trainer_id: str) -> str:
    # str.removeprefix() was introduced in Python 3.9. Keep the build scripts
    # compatible with the Python 3.7 version traditionally used by CFRU.
    short_id = trainer_id[len("TRAINER_"):] if trainer_id.startswith("TRAINER_") else trainer_id
    return "sShowdownParty_" + "".join(word.title() for word in short_id.split("_"))


def generate_mon(mon: Pokemon, symbols: Symbols) -> tuple[str, bool, bool]:
    species_text, item_text = pokemon_title(mon)
    species = symbols.get("species", species_text)
    level = int(mon.fields.get("Level", "100"))
    if not 1 <= level <= 100:
        raise PartyError(f"{mon.title}: Level must be between 1 and 100")
    item = symbols.get("item", item_text, "ITEM_NONE")
    has_item = item != "ITEM_NONE"
    raw_iv = int(mon.fields.get("CFRU IV", "0"))
    if not 0 <= raw_iv <= 255:
        raise PartyError(f"{mon.title}: CFRU IV must be between 0 and 255")
    ivs = stat_spread(mon.fields.get("IVs", ""), 0)
    split_ivs = "IVs" in mon.fields and len(set(ivs)) > 1
    advanced = split_ivs or any(key in mon.fields for key in ("Ability", "EVs", "Nature", "Tera Type", "Ball", "Shiny", "Happiness"))
    unsupported = [key for key in ("Ball", "Shiny", "Happiness") if key in mon.fields]
    if unsupported:
        raise PartyError(f"{mon.title}: unsupported by TrainerMonItemCustomMoves: {', '.join(unsupported)}")
    custom = bool(mon.moves) or advanced
    if advanced and not mon.moves:
        raise PartyError(f"{mon.title}: custom stats require explicit moves in this CFRU")
    lines = ["    {", f"        .lvl = {level},", f"        .species = {species},"]
    if custom:
        ability_value = mon.fields.get("Ability", "Random All")
        ability_alias = {"hidden": "Ability_Hidden", "ability1": "Ability_1", "ability2": "Ability_2",
                         "random12": "Ability_Random_1_2", "randomall": "Ability_RandomAll"}
        ability = ability_alias.get(normalized(ability_value).lower())
        if ability is None:
            raise PartyError(f"{mon.title}: Ability must be Hidden, Ability 1, Ability 2, Random 1 2, or Random All")
        nature = symbols.get("nature", mon.fields.get("Nature", "Hardy"))
        ivs = stat_spread(mon.fields.get("IVs", ""), 31)
        evs = stat_spread(mon.fields.get("EVs", ""), 0)
        tera = symbols.get("type", mon.fields.get("Tera Type", "Normal"))
        moves = [symbols.get("move", move) for move in mon.moves]
        if len(moves) > 4:
            raise PartyError(f"{mon.title}: a Pokemon can have at most 4 moves")
        moves += ["MOVE_NONE"] * (4 - len(moves))
        lines += [f"        .iv = {raw_iv},", f"        .ability = {ability},", f"        .nature = {nature},",
                  "        .ivSpread = {" + ", ".join(map(str, ivs)) + "},",
                  "        .evSpread = {" + ", ".join(map(str, evs)) + "},",
                  f"        .heldItem = {item},", "        .moves = {" + ", ".join(moves) + "},",
                  f"        .teraType = {tera},"]
    elif has_item:
        lines.insert(1, f"        .iv = {raw_iv or ivs[0]},")
        lines.append(f"        .heldItem = {item},")
    else:
        lines.insert(1, f"        .iv = {raw_iv or ivs[0]},")
    lines += ["    },"]
    return "\n".join(lines), has_item, custom


def generate(trainers: list[Trainer], symbols: Symbols) -> tuple[str, str]:
    parties = ["/* Auto-generated by scripts/trainer_party.py. Do not edit. */", ""]
    overrides = ["/* Auto-generated by scripts/trainer_party.py. Do not edit. */", ""]
    for trainer in trainers:
        symbols.get("trainer", trainer.trainer_id)
        required = [field for field in ("Name", "Class", "Pic") if field not in trainer.fields]
        if required:
            raise PartyError(f"{trainer.trainer_id}: missing fields: {', '.join(required)}")
        if not trainer.pokemon:
            raise PartyError(f"{trainer.trainer_id}: party cannot be empty")
        rendered = [generate_mon(mon, symbols) for mon in trainer.pokemon]
        has_item = any(item[1] for item in rendered)
        custom = any(item[2] for item in rendered)
        if custom and not all(item[2] for item in rendered):
            raise PartyError(f"{trainer.trainer_id}: all Pokemon must use explicit moves when one uses custom data")
        if custom:
            struct_name, union_name = "TrainerMonItemCustomMoves", "ItemCustomMoves"
            flags = "PARTY_FLAG_CUSTOM_MOVES | PARTY_FLAG_HAS_ITEM"
        elif has_item:
            struct_name, union_name = "TrainerMonItemDefaultMoves", "ItemDefaultMoves"
            flags = "PARTY_FLAG_HAS_ITEM"
        else:
            struct_name, union_name, flags = "TrainerMonNoItemDefaultMoves", "NoItemDefaultMoves", "0"
        party = party_symbol(trainer.trainer_id)
        parties += [f"static const struct {struct_name} {party}[] =", "{",
                    *[item[0] for item in rendered], "};", ""]
        fields = trainer.fields
        items = [symbols.get("item", item.strip()) for item in fields.get("Items", "").split("/") if item.strip()]
        items = (items + ["ITEM_NONE"] * 4)[:4]
        ai = [symbols.get("ai", item.strip()) for item in fields.get("AI", "Check Bad Move").split("/") if item.strip()]
        overrides += [f"[{trainer.trainer_id}] = {{", f"    .partyFlags = {flags},",
            f"    .trainerClass = {symbols.get('class', fields['Class'])},",
            f"    .encounterMusic = {symbols.get('music', fields.get('Music', 'Male'))},",
            f"    .gender = {'GENDER_FEMALE' if fields.get('Gender', 'Male').lower() == 'female' else 'GENDER_MALE'},",
            f"    .trainerPic = {symbols.get('pic', fields['Pic'])},", f"    .trainerName = {c_name(fields['Name'])},",
            "    .items = {" + ", ".join(items) + "},",
            f"    .doubleBattle = {'TRUE' if fields.get('Double Battle', 'No').lower() in ('yes', 'true', 'doubles') else 'FALSE'},",
            f"    .aiFlags = {' | '.join(ai) if ai else '0'},", f"    .partySize = NELEMS({party}),",
            f"    .party = {{.{union_name} = {party}}}", "},", ""]
    return "\n".join(parties), "\n".join(overrides)


def build(root: Path = ROOT) -> None:
    party_file = root / PARTY_FILE.relative_to(ROOT)
    trainers = parse(party_file.read_text(encoding="utf-8"))
    parties, overrides = generate(trainers, Symbols(root))
    (root / PARTIES_OUT.relative_to(ROOT)).write_text(parties + "\n", encoding="utf-8")
    (root / TRAINERS_OUT.relative_to(ROOT)).write_text(overrides + "\n", encoding="utf-8")
    print(f"Generated {len(trainers)} trainer override(s).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build CFRU trainer overrides from Showdown syntax")
    parser.add_argument("command", choices=("build", "check"), nargs="?", default="build")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    try:
        build(args.root.resolve())
        return 0
    except (OSError, PartyError, ValueError) as exc:
        print(f"trainer_party: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
