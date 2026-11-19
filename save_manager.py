# save_manager.py - Handle player save files with file locking for sync
from pathlib import Path
from typing import Optional, Dict, Any, List
try:
    import portalocker
    HAS_LOCK = True
except ImportError:
    HAS_LOCK = False

BASE_DIR = Path(__file__).parent
SAVES_DIR = BASE_DIR / "saves"
SAVES_DIR.mkdir(exist_ok=True)

# New players start with the trashiest gear
DEFAULT_PLAYER = {
    "username": "",
    "password": "",
    "gold": 50000,
    "abyss_tokens": 0,
    "abyss_floor": 1,
    "level": 1,
    "xp": 0,
    "xp_to_next_level": 100,
    "hp": 120,
    "max_hp": 120,
    "powers": [],
    "equipped_power": None,
    "weapon": "wooden_stick",
    "armor": "tattered_rags",
    "unlocked_weapons": ["wooden_stick"],
    "unlocked_armors": ["tattered_rags"],
    "weapon_levels": {},
    "armor_levels": {},
    "potions": {"minor_potion": 5, "strength_potion": 2},
    "lang": "zh",
}


def get_user_save_filename(username: str) -> Path:
    safe_name = "".join(c for c in username if c.isalnum() or c in ("_", "-"))
    return SAVES_DIR / f"save_{safe_name}.txt"


def serialize_levels(lv_dict: Dict[str, int]) -> str:
    if not lv_dict:
        return "None"
    items = [f"{k}:{v}" for k, v in lv_dict.items() if v > 0]
    return ",".join(items) if items else "None"


def deserialize_levels(raw_str: str) -> Dict[str, int]:
    res = {}
    if not raw_str or raw_str == "None":
        return res
    for item in raw_str.split(","):
        if ":" in item:
            k, v = item.split(":", 1)
            if v.isdigit():
                res[k] = int(v)
    return res


def load_user_data(username: str) -> Optional[List[str]]:
    filename = get_user_save_filename(username)
    if not filename.exists():
        return None
    try:
        with open(filename, "r", encoding="utf-8") as f:
            if HAS_LOCK:
                portalocker.lock(f, portalocker.LOCK_SH)
            line = f.readline().strip()
            if HAS_LOCK:
                portalocker.unlock(f)
            if not line:
                return None
            return line.split(" ")
    except Exception:
        return None


def player_dict_from_row(parts: List[str]) -> Optional[Dict[str, Any]]:
    if not parts or len(parts) < 17:
        return None

    eq_power = parts[10] if parts[10] != "None" else None
    powers_str = parts[11]
    weapons_str = parts[12]
    armors_str = parts[13]
    minor_potion = int(parts[14]) if parts[14].isdigit() else 5
    strength_potion = int(parts[15]) if parts[15].isdigit() else 2
    lang = parts[16] if len(parts) > 16 else "zh"
    abyss_tokens = int(parts[17]) if len(parts) > 17 and parts[17].isdigit() else 0
    abyss_floor = int(parts[18]) if len(parts) > 18 and parts[18].isdigit() else 1
    w_lv_str = parts[19] if len(parts) > 19 else "None"
    a_lv_str = parts[20] if len(parts) > 20 else "None"

    powers = []
    if powers_str and powers_str != "None":
        powers = [{"name": n} for n in powers_str.split(",") if n]

    unlocked_weapons = (
        weapons_str.split(",") if weapons_str and weapons_str != "None" else ["wooden_stick"]
    )
    unlocked_armors = (
        armors_str.split(",") if armors_str and armors_str != "None" else ["tattered_rags"]
    )

    return {
        "username": parts[0],
        "password": parts[1],
        "gold": int(parts[2]),
        "level": int(parts[3]),
        "xp": int(parts[4]),
        "xp_to_next_level": int(parts[5]),
        "hp": int(parts[6]),
        "max_hp": int(parts[7]),  # will be recalculated on load
        "weapon": parts[8],
        "armor": parts[9],
        "equipped_power": eq_power,
        "powers": powers,
        "unlocked_weapons": unlocked_weapons,
        "unlocked_armors": unlocked_armors,
        "potions": {"minor_potion": minor_potion, "strength_potion": strength_potion},
        "lang": lang,
        "abyss_tokens": abyss_tokens,
        "abyss_floor": abyss_floor,
        "weapon_levels": deserialize_levels(w_lv_str),
        "armor_levels": deserialize_levels(a_lv_str),
        "armor_slots": dict(s.split(":") for s in parts[21].split(",") if ":" in s) if len(parts) > 21 and parts[21] not in ("None", "") else {},
    }


def save_player_data(player: Dict[str, Any]) -> bool:
    if not player.get("username"):
        return False
    filename = get_user_save_filename(player["username"])

    powers = player.get("powers") or []
    if powers and isinstance(powers[0], dict):
        powers_str = ",".join(p["name"] for p in powers) if powers else "None"
    else:
        powers_str = ",".join(powers) if powers else "None"

    eq_power = player.get("equipped_power") or "None"
    weapons_str = ",".join(player.get("unlocked_weapons") or ["iron_sword"])
    armors_str = ",".join(player.get("unlocked_armors") or ["iron_armor"])
    potions = player.get("potions") or {"minor_potion": 5, "strength_potion": 2}
    w_lv_str = serialize_levels(player.get("weapon_levels") or {})
    a_lv_str = serialize_levels(player.get("armor_levels") or {})
    slots = player.get("armor_slots") or {}
    slots_str = ",".join(f"{k}:{v}" for k, v in slots.items() if v) or "None"

    row_data = [
        player["username"],
        player["password"],
        str(player.get("gold", 0)),
        str(player.get("level", 1)),
        str(player.get("xp", 0)),
        str(player.get("xp_to_next_level", 100)),
        str(player.get("hp", 120)),
        str(player.get("max_hp", 120)),
        player.get("weapon", "iron_sword"),
        player.get("armor", "iron_armor"),
        eq_power,
        powers_str,
        weapons_str,
        armors_str,
        str(potions.get("minor_potion", 5)),
        str(potions.get("strength_potion", 2)),
        player.get("lang", "zh"),
        str(player.get("abyss_tokens", 0)),
        str(player.get("abyss_floor", 1)),
        w_lv_str,
        a_lv_str,
        slots_str,
    ]

    try:
        with open(filename, "w", encoding="utf-8") as f:
            if HAS_LOCK:
                portalocker.lock(f, portalocker.LOCK_EX)
            f.write(" ".join(str(x) for x in row_data))
            if HAS_LOCK:
                portalocker.unlock(f)
        return True
    except Exception as e:
        print(f"[save error] {e}")
        return False


def create_new_account(username: str, password: str) -> Dict[str, Any]:
    """Create a fresh player with trash-tier starter gear."""
    player = {k: (v.copy() if isinstance(v, (dict, list)) else v) for k, v in DEFAULT_PLAYER.items()}
    player["username"] = username
    player["password"] = password
    player["weapon"] = "wooden_stick"
    player["armor"] = "tattered_rags"
    player["unlocked_weapons"] = ["wooden_stick"]
    player["unlocked_armors"] = ["tattered_rags"]
    player["gold"] = 50000
    player["weapon_levels"] = {}
    player["armor_levels"] = {}
    player["powers"] = []
    player["equipped_power"] = None
    player["potions"] = {"minor_potion": 5, "strength_potion": 2}
    # max_hp will be set properly when calculate_stats runs (includes armor hp_bonus)
    from game_core import calculate_stats
    calculate_stats(player)
    player["hp"] = player["max_hp"]
    save_player_data(player)
    return player


def user_exists(username: str) -> bool:
    return get_user_save_filename(username).exists()


def list_all_saves() -> List[str]:
    names = []
    for f in SAVES_DIR.glob("save_*.txt"):
        name = f.stem[5:]
        if name:
            names.append(name)
    return names


def save_player_json(player: dict):
    """Save player data as JSON (more stable)."""
    path = get_save_path(player["username"])
    path = path.replace(".txt", ".json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(player, f, ensure_ascii=False, indent=2)

def load_player_json(username: str) -> dict:
    """Load player data from JSON."""
    path = get_save_path(username).replace(".txt", ".json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None


def backup_save(username: str):
    """Create backup of save file."""
    import shutil
    from datetime import datetime
    src = get_save_path(username).replace(".txt", ".json")
    if os.path.exists(src):
        backup_dir = os.path.join(os.path.dirname(src), "backups")
        os.makedirs(backup_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        dst = os.path.join(backup_dir, f"{username}_{ts}.json")
        shutil.copy2(src, dst)
        # Keep only last 5 backups
        backups = sorted([f for f in os.listdir(backup_dir) if f.startswith(username)])
        for old in backups[:-5]:
            os.remove(os.path.join(backup_dir, old))

def load_player_with_backup(username: str) -> dict:
    """Load player, try JSON first, then txt, with backup recovery."""
    # Try JSON first
    data = load_player_json(username)
    if data:
        return data
    # Try txt fallback
    data = load_user_data(username)
    if data:
        # Migrate to JSON
        save_player_json(data)
        return data
    # Try backup recovery
    backup_dir = os.path.join(os.path.dirname(get_save_path(username)), "backups")
    if os.path.exists(backup_dir):
        backups = sorted([f for f in os.listdir(backup_dir) if f.startswith(username)], reverse=True)
        if backups:
            with open(os.path.join(backup_dir, backups[0]), "r", encoding="utf-8") as f:
                return json.load(f)
    return None
