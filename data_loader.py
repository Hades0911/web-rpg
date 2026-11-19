# data_loader.py - Load static game data from txt files
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"

GRADE_MULTIPLIERS = {'s': 5.0, 'a': 4.0, 'b': 3.0, 'c': 2.0, 'd': 1.0, 'e': 0.5}

ELEMENT_ADVANTAGE = {
    "fire": "nature", "nature": "earth", "earth": "thunder", "thunder": "water",
    "water": "fire", "holy": "dark", "dark": "holy"
}


def parse_bilingual_desc(raw_desc: str):
    if "|" in raw_desc:
        en_part, zh_part = raw_desc.split("|", 1)
        return en_part.strip(), zh_part.strip()
    clean = raw_desc.strip() or "No description available."
    return clean, clean


def get_monster_element(monster_name: str) -> str:
    name_lower = monster_name.lower()
    if any(k in name_lower for k in ["fire", "flame", "magma", "lava", "pyro", "burn", "dragon"]):
        return "fire"
    elif any(k in name_lower for k in ["water", "ice", "frost", "aqua", "slime", "freeze", "ocean"]):
        return "water"
    elif any(k in name_lower for k in ["thunder", "lightning", "storm", "volt", "spark"]):
        return "thunder"
    elif any(k in name_lower for k in ["dark", "shadow", "demon", "devil", "undead", "skeleton", "ghost"]):
        return "dark"
    elif any(k in name_lower for k in ["holy", "angel", "divine", "light", "saint"]):
        return "holy"
    elif any(k in name_lower for k in ["nature", "forest", "grass", "wood", "earth", "golem", "rock", "goblin"]):
        return "earth"
    return "none"


def load_powers_db():
    path = DATA_DIR / "power.txt"
    powers = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().strip().splitlines()
        for line in lines:
            if not line.strip():
                continue
            parts = line.split(maxsplit=4)
            if len(parts) >= 3:
                name, base_str, grade = parts[0], float(parts[1]), parts[2].lower()
                effect = parts[3] if len(parts) > 3 else "none"
                desc_en, desc_zh = parse_bilingual_desc(parts[4] if len(parts) > 4 else "")
                multiplier = GRADE_MULTIPLIERS.get(grade, 1.0)
                score = round(base_str * multiplier, 2)
                weight = 2 if grade == 's' else (20 if grade == 'a' else (
                    100 if grade == 'b' else (250 if grade == 'c' else (500 if grade == 'd' else 128))))
                powers.append({
                    "name": name, "base": base_str, "grade": grade, "effect": effect,
                    "score": score, "weight": weight, "desc_en": desc_en, "desc_zh": desc_zh
                })
        powers.sort(key=lambda x: x["score"], reverse=True)
        return powers
    except FileNotFoundError:
        return [{"name": "Fire", "base": 2.0, "grade": "d", "effect": "burn", "score": 2.0,
                 "weight": 500, "desc_en": "Ignites primal flames.", "desc_zh": "点燃原初烈焰。"}]


def load_monsters():
    path = DATA_DIR / "monster.txt"
    monsters = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().strip().splitlines()
        for line in lines:
            if not line.strip():
                continue
            p = line.split()
            if len(p) >= 3:
                name = p[0]
                hp = int(p[1])
                atk = int(p[2])
                pattern = p[3] if len(p) > 3 else "aggressive"
                special = p[4] if len(p) > 4 else "none"
                xp_reward = int(p[5]) if len(p) > 5 and p[5].isdigit() else 50
                element = get_monster_element(name)
                monsters.append({
                    "name": name, "hp": hp, "atk": atk, "pattern": pattern,
                    "special": special, "element": element, "xp_reward": xp_reward
                })
        return monsters
    except FileNotFoundError:
        return [{"name": "Goblin", "hp": 40, "atk": 15, "pattern": "aggressive",
                 "special": "none", "element": "earth", "xp_reward": 20}]


def load_armors():
    path = DATA_DIR / "armor.txt"
    armors = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().strip().splitlines()
        for line in lines:
            if not line.strip():
                continue
            p = line.split()
            if len(p) >= 6:
                name, defense, hp_bonus = p[0], int(p[1]), int(p[2])
                crit_ch = int(p[3]) if p[3].isdigit() else 0
                crit_dmg = float(p[4]) if p[4].replace('.', '', 1).isdigit() else 1.0
                element = p[5]
                score = defense + hp_bonus
                tier = "D"
                desc_raw = ""
                if len(p) > 6:
                    if p[6].upper() in ['S', 'A', 'B', 'C', 'D', 'E', 'F']:
                        tier = p[6].upper()
                        desc_raw = " ".join(p[7:])
                    else:
                        desc_raw = " ".join(p[6:])
                        tier = "S" if score >= 250 else (
                            "A" if score >= 150 else ("B" if score >= 80 else ("C" if score >= 40 else "D")))
                else:
                    tier = "S" if score >= 250 else (
                        "A" if score >= 150 else ("B" if score >= 80 else ("C" if score >= 40 else "D")))
                desc_en, desc_zh = parse_bilingual_desc(desc_raw)
                armors[name] = {
                    "defense": defense, "hp_bonus": hp_bonus, "crit_ch": crit_ch,
                    "crit_dmg": crit_dmg, "element": element, "tier": tier,
                    "desc_en": desc_en, "desc_zh": desc_zh
                }
        return armors
    except FileNotFoundError:
        return {
            "iron_armor": {
                "defense": 70, "hp_bonus": 90, "crit_ch": 0, "crit_dmg": 1.0,
                "element": "none", "tier": "A",
                "desc_en": "Standard heavy iron plate armor.",
                "desc_zh": "制式重型铁制板甲。"
            }
        }


def load_weapons():
    path = DATA_DIR / "wepone.txt"
    default_fallback = {
        "iron_sword": {
            "atk": 30, "crit_ch": 6, "crit_dmg": 1.5, "element": "none", "tier": "C",
            "desc_en": "A dependable standard-issue knight's arming sword.",
            "desc_zh": "坚固耐用的制式骑士武装剑。"
        },
        "rusty_sword": {
            "atk": 15, "crit_ch": 5, "crit_dmg": 1.5, "element": "none", "tier": "D",
            "desc_en": "A weathered iron broadsword.",
            "desc_zh": "饱经风霜的生锈铁阔剑。"
        }
    }
    if not path.exists():
        return default_fallback

    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().strip().splitlines()
        weapons = {}
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            p = line.split()
            if len(p) < 2:
                continue
            name, atk = p[0], int(p[1])
            crit_ch, crit_dmg, element, tier, desc_start_idx = 5, 1.5, "none", "D", 2

            if len(p) > desc_start_idx and p[desc_start_idx].isdigit():
                crit_ch = int(p[desc_start_idx])
                desc_start_idx += 1
            if len(p) > desc_start_idx and p[desc_start_idx].replace('.', '', 1).isdigit():
                crit_dmg = float(p[desc_start_idx])
                desc_start_idx += 1

            valid_tiers = {'S', 'A', 'B', 'C', 'D', 'E'}
            if len(p) > desc_start_idx:
                token = p[desc_start_idx]
                if not token.replace('.', '', 1).isdigit() and token.upper() not in valid_tiers:
                    element = token.lower()
                    desc_start_idx += 1

            if len(p) > desc_start_idx:
                token = p[desc_start_idx]
                if token.upper() in valid_tiers:
                    tier = token.upper()
                    desc_start_idx += 1
                else:
                    tier = "S" if atk >= 120 else (
                        "A" if atk >= 80 else ("B" if atk >= 45 else ("C" if atk >= 25 else "D")))
            else:
                tier = "S" if atk >= 120 else (
                    "A" if atk >= 80 else ("B" if atk >= 45 else ("C" if atk >= 25 else "D")))

            desc_raw = " ".join(p[desc_start_idx:])
            desc_en, desc_zh = parse_bilingual_desc(desc_raw)
            weapons[name] = {
                "atk": atk, "crit_ch": crit_ch, "crit_dmg": crit_dmg,
                "element": element, "tier": tier, "desc_en": desc_en, "desc_zh": desc_zh
            }
        return weapons if weapons else default_fallback
    except Exception:
        return default_fallback


def load_game_catalog():
    return {
        "weapons": load_weapons(),
        "armors": load_armors(),
        "powers": {p["name"]: p for p in load_powers_db()}
    }
