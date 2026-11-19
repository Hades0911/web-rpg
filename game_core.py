import os
# game_core.py - Pure game logic (no print / input / clear_screen)
import random
from typing import Dict, Any, List, Tuple, Optional

from data_loader import (
    load_weapons, load_armors, load_powers_db, load_monsters,
    load_game_catalog, ELEMENT_ADVANTAGE, get_monster_element
)
from save_manager import save_player_data, load_user_data, load_player_json, save_player_json


def get_effective_weapon(w_name: str, player: Dict, weapons_db=None) -> Dict:
    if not w_name or w_name == "None":
        return {"atk": 5, "crit_ch": 0, "crit_dmg": 1.0, "element": "none", "tier": "D", "upgrade_lv": 0}
    if weapons_db is None:
        weapons_db = load_weapons()
    base = weapons_db.get(w_name, {
        "atk": 15, "crit_ch": 5, "crit_dmg": 1.5, "element": "none", "tier": "D"
    }).copy()
    lv = player.get("weapon_levels", {}).get(w_name, 0)
    base["upgrade_lv"] = lv
    if lv > 0:
        base["atk"] = int(base["atk"] * (1.15 ** lv))
    return base


def get_effective_armor(a_name: str, player: Dict, armors_db=None) -> Dict:
    if not a_name or a_name == "None":
        return {"defense": 0, "hp_bonus": 0, "crit_ch": 0, "crit_dmg": 1.0, "element": "none", "tier": "D"}
    if armors_db is None:
        armors_db = load_armors()
    base = armors_db.get(a_name, {
        "defense": 50, "hp_bonus": 50, "crit_ch": 0, "crit_dmg": 1.0,
        "element": "none", "tier": "D"
    }).copy()
    lv = player.get("armor_levels", {}).get(a_name, 0)
    base["upgrade_lv"] = lv
    if lv > 0:
        base["defense"] = int(base["defense"] * (1.12 ** lv))
        base["hp_bonus"] = int(base["hp_bonus"] * (1.12 ** lv))
    return base


def format_gear_name(name: str, player: Dict, category: str = "weapon") -> str:
    lv_dict = player.get("weapon_levels" if category == "weapon" else "armor_levels", {})
    lv = lv_dict.get(name, 0)
    return f"{name} +{lv}" if lv > 0 else name


def calculate_element_multiplier(attacker_elem: str, defender_elem: str) -> Tuple[float, str]:
    if not attacker_elem or not defender_elem or attacker_elem == "none" or defender_elem == "none":
        return 1.0, ""
    a_elem, d_elem = attacker_elem.lower(), defender_elem.lower()
    if ELEMENT_ADVANTAGE.get(a_elem) == d_elem:
        return 1.5, "⚡ [屬性克製！傷害 x1.5]"
    elif ELEMENT_ADVANTAGE.get(d_elem) == a_elem:
        return 0.7, "🛡️ [屬性抵抗！傷害 x0.7]"
    return 1.0, ""



def get_base_stats(level: int) -> dict:
    """Base stats from level only."""
    return {
        "atk": 10 + (level - 1) * 4,
        "hp": 120 + (level - 1) * 35,
        "def": 0,
        "crit": 5,
    }

def calculate_stats(player: Dict) -> Tuple[int, int, int, float, str, str, str]:
    """Return (total_atk, defense, crit_ch, crit_dmg, power_effect, power_desc, weapon_element)"""
    w_data = get_effective_weapon(player["weapon"], player)
    # Sum all armor slots with diminishing returns
    slots = get_equipped_armors(player)
    total_def = 0
    total_hp = 0
    slot_crit = 0
    slot_weights = {"chest": 1.0, "helmet": 0.7, "gloves": 0.5, "boots": 0.5, "cloak": 0.6}
    for slot, aname in slots.items():
        if aname:
            ad = get_effective_armor(aname, player)
            w = slot_weights.get(slot, 0.5)
            total_def += int(ad.get("defense", 0) * w)
            total_hp += int(ad.get("hp_bonus", 0) * w)
            slot_crit += int(ad.get("crit_ch", 0) * w)

    base_hp = 120 + total_hp + ((player["level"] - 1) * 35)
    player["max_hp"] = base_hp
    if player["hp"] > player["max_hp"]:
        player["hp"] = player["max_hp"]

    p_bonus, p_effect, p_desc = 10, "none", ""
    if player.get("equipped_power"):
        for p in load_powers_db():
            if p["name"] == player["equipped_power"]:
                p_bonus = int(p["score"] * 4)
                p_effect = p["effect"]
                lang = player.get("lang", "zh")
                p_desc = (p.get("desc_zh") if lang == "zh" else p.get("desc_en")) or p.get("desc_en") or p.get("desc_zh") or ""
                break

    level_base_atk = 10 + ((player["level"] - 1) * 4)
    # Reduced level scaling
    total_atk = int((level_base_atk + w_data["atk"] + p_bonus) * (1.0 + (player["level"] - 1) * 0.04))
    # Cap crit rate at 50%
    total_crit_ch = min(50, w_data.get("crit_ch", 5) + slot_crit)
    # Cap crit damage at 3.0
    total_crit_dmg = min(3.0, w_data.get("crit_dmg", 1.5))

    return total_atk, total_def, total_crit_ch, total_crit_dmg, p_effect, p_desc, w_data.get("element", "none")


def calculate_combat_power(player: Dict) -> int:
    weapons = load_weapons()
    armors = load_armors()
    powers_list = load_powers_db()
    w_name = player.get("weapon", "iron_sword")
    eq_power = player.get("equipped_power")
    w_lv = player.get("weapon_levels", {}).get(w_name, 0)

    w_data = weapons.get(w_name, {"atk": 15, "crit_ch": 5, "crit_dmg": 1.5}).copy()
    if w_lv > 0:
        w_data["atk"] = int(w_data["atk"] * (1.15 ** w_lv))

    # Sum all armor slots
    slots = get_equipped_armors(player)
    slot_weights = {"chest": 1.0, "helmet": 0.7, "gloves": 0.5, "boots": 0.5, "cloak": 0.6}
    a_score = 0
    for slot, aname in slots.items():
        if aname and aname in armors:
            a_data = armors[aname]
            a_lv = player.get("armor_levels", {}).get(aname, 0)
            def_val = int(a_data["defense"] * (1.12 ** a_lv)) if a_lv > 0 else a_data["defense"]
            hp_val = int(a_data["hp_bonus"] * (1.12 ** a_lv)) if a_lv > 0 else a_data["hp_bonus"]
            w = slot_weights.get(slot, 0.5)
            a_score += (def_val + hp_val * 0.5) * w

    ach_bonus = 0
    if player.get("equipped_achievement") == "lv50":
        ach_bonus = 15
    elif player.get("equipped_achievement") == "lv10":
        ach_bonus = 5
    w_score = w_data["atk"] + ach_bonus * (1 + (w_data["crit_ch"] / 100) * w_data["crit_dmg"])
    p_score = next((p["score"] * 25 for p in powers_list if p["name"] == eq_power), 0)
    return max(100, int(w_score * 10 + a_score * 5 + p_score + player["level"] * 50))


def apply_power_effect(effect_name: str, player: Dict) -> Tuple[int, bool, int, int, str]:
    """Return (bonus_dmg, skip_turn, dot, heal, message)"""
    msg, bonus_dmg, skip_turn, dot, heal = "", 0, False, 0, 0
    effect_lower = (effect_name or "none").lower()

    if effect_lower in ["absolute", "rewrite", "obliterate", "erase", "foresight", "execution"]:
        bonus_dmg, skip_turn = 40, True
        msg = f"⚖️ [{effect_name.upper()}] 终極宇宙律令：附加 +40 傷害並完全封鎖敵人反擊！"
    elif effect_lower in ["teleport", "blink", "gateway", "phase", "stealth"]:
        bonus_dmg, skip_turn = 22, True
        msg = f"🌌 [{effect_name.upper()}] 空間閃避：瞬間避開危险並反擊 +22 傷害！"
    elif effect_lower in ["absolute_defense", "invulnerable"]:
        bonus_dmg = 30
        msg = f"🛡️ [{effect_name.upper()}] 至高壁垒：免疫傷害並触发猛烈反擊 +30 傷害！"
    elif effect_lower in ["reflection", "reflect", "mimic"]:
        bonus_dmg = 25
        msg = f"🪞 [{effect_name.upper()}] 因果鏡像：將敵人的惡意與傷害反弹 +25 傷害！"
    elif effect_lower in ["scorch", "burn", "hellfire", "solar", "melt", "eruption", "scald"]:
        bonus_dmg, dot = 20, 10
        msg = f"🔥 [{effect_name.upper()}] 火山灼烧：造成 +20 爆发傷害並施加每回合 10 点灼烧！"
    elif effect_lower in ["poison", "toxic", "corrode", "bleed", "rot", "wither", "decay", "fallout", "drain"]:
        bonus_dmg, dot = 18, 12
        msg = f"☠️ [{effect_name.upper()}] 持續侵蝕：造成 +18 傷害並施加每回合 12 点侵蝕！"
    elif effect_lower in ["mirror_image", "dodge", "blind", "obscure", "shadow_veil"]:
        bonus_dmg, skip_turn = 20, True
        msg = f"👥 [{effect_name.upper()}] 鏡像幻影：迷惑攻擊者並反擊 +20 傷害！"
    elif effect_lower in ["sticky", "freeze", "stun", "chill", "frostbite", "root", "trap", "slumber",
                          "terror", "panic", "charm", "lock", "silence", "time_warp", "entanglement"]:
        bonus_dmg, skip_turn = 20, True
        msg = f"❄️ [{effect_name.upper()}] 控製束缚：冰封/束缚敵人，阻止其发動反擊！"
    elif effect_lower in ["shield", "harden", "armor_up", "sanctify"]:
        bonus_dmg = 25
        msg = f"🛡️ [{effect_name.upper()}] 大地壁垒：吸收傷害並以岩石之力反擊 +25 傷害！"
    elif effect_lower in ["regen", "regeneration", "bloom", "resurrect", "revive", "inspire"]:
        heal, bonus_dmg = 25, 15
        player["hp"] = min(player["max_hp"], player["hp"] + heal)
        msg = f"✨ [{effect_name.upper()}] 生命複苏：恢複 25 点生命值並造成 +15 能量傷害！"
    else:
        bonus_dmg = 12
        msg = f"⭐ [{effect_name.upper()}] 基础能量共鸣：附加 +12 点能量傷害。"

    return bonus_dmg, skip_turn, dot, heal, msg


def gain_xp(player: Dict, amount: int) -> List[str]:
    """Add XP and handle level ups. Return list of level-up messages."""
    messages = []
    player["xp"] += amount
    while player["xp"] >= player["xp_to_next_level"]:
        player["xp"] -= player["xp_to_next_level"]
        player["level"] += 1
        player["xp_to_next_level"] = int(player["xp_to_next_level"] * 1.35)
        # recalculate max_hp
        a_data = get_effective_armor(player["armor"], player)
        player["max_hp"] = 120 + a_data["hp_bonus"] + ((player["level"] - 1) * 35)
        player["hp"] = player["max_hp"]
        messages.append(f"🎉 等級提升！現在是 Lv.{player['level']}！生命值已回满。")
    return messages


def get_level_appropriate_monster(monsters: List[Dict], lvl: int) -> Dict:
    total = len(monsters)
    if total < 10:
        return random.choice(monsters)
    tier_size = total // 10
    tier_idx = min(9, (max(1, lvl) - 1) // 10)
    start_idx = tier_idx * tier_size
    end_idx = total if tier_idx == 9 else (start_idx + tier_size + 3)
    sub_list = monsters[start_idx:min(total, end_idx)]
    return random.choice(sub_list if sub_list else monsters)


def check_and_use_auto_potion(player: Dict) -> Optional[str]:
    hp_percent = player["hp"] / player["max_hp"] if player["max_hp"] > 0 else 0
    if hp_percent <= 0.40:
        potions = player.setdefault("potions", {"minor_potion": 5, "strength_potion": 2})
        if potions.get("minor_potion", 0) > 0:
            potions["minor_potion"] -= 1
            heal_amount = int(player["max_hp"] * 0.5)
            player["hp"] = min(player["max_hp"], player["hp"] + heal_amount)
            return f"💊 [智能应急吃藥] 生命值低于 40%！自動使用微型生命藥劑，恢複 {heal_amount} 点 HP！(剩余: {potions['minor_potion']})"
    return None


def simulate_auto_fight(player: Dict, max_waves: int = 20) -> Dict[str, Any]:
    lang = player.get("lang", "zh")
    """
    Simulate continuous auto-fight. Returns a complete result dict with log.
    This is the web-friendly version of the original auto-fight loop.
    """
    monsters = load_monsters()
    if not monsters:
        return {"ok": False, "error": "No monsters loaded"}

    start_lvl = player["level"]
    start_hp = player["hp"]
    total_kills = 0
    total_xp = 0
    total_gold = 0
    battle_log = []
    waves_fought = 0

    for wave in range(max_waves):
        if player["hp"] <= 0:
            break

        horde_size = random.choices([1, 2, 3], weights=[50, 35, 15], k=1)[0]
        active_horde = []
        for _ in range(horde_size):
            bm = get_level_appropriate_monster(monsters, player["level"])
            scaling = 1.0 + (player["level"] - 1) * 0.1
            atk_scaling = 1.0 + (player["level"] - 1) * 0.05
            active_horde.append({
                "name": bm["name"],
                "hp": int(bm["hp"] * scaling),
                "max_hp": int(bm["hp"] * scaling),
                "atk": int(bm["atk"] * atk_scaling),
                "pattern": bm["pattern"],
                "special": bm["special"],
                "element": bm.get("element", "none"),
                "xp_reward": bm["xp_reward"]
            })

        lang = player.get("lang", "zh")
        if lang == "en":
            battle_log.append(f"--- Wave {wave + 1}: {horde_size} monsters ---")
        else:
            battle_log.append(f"--- 第 {wave + 1} 波：遭遇 {horde_size} 只怪物 ---")
        floor_num = player.get('battle_floor', 1)
        level_scale = 1 + (player.get("level", 1) - 1) * 0.1 + (floor_num - 1) * 0.2
        for m in active_horde:
            m["hp"] = int(m["hp"] * level_scale)
            m["atk"] = int(m["atk"] * level_scale)
            elem_label = "Element" if player.get("lang") == "en" else "屬性"
            battle_log.append(f"  • {m['name']} (HP: {m['hp']}, ATK: {m['atk']}, {elem_label}: {m['element']})")

        # Fight this horde
        while any(m["hp"] > 0 for m in active_horde) and player["hp"] > 0:
            potion_msg = check_and_use_auto_potion(player)
            if potion_msg:
                battle_log.append(potion_msg)

            living = [m for m in active_horde if m["hp"] > 0]
            if not living:
                break
            target = living[0]

            atk, defense, crit_ch, crit_dmg, p_effect, p_desc, player_elem = calculate_stats(player)
            bonus_dmg, skip_turn, dot, heal, power_msg = apply_power_effect(p_effect, player)

            # Player attack
            is_crit = random.randint(1, 100) <= crit_ch
            raw_dmg = atk + bonus_dmg
            if is_crit:
                raw_dmg = int(raw_dmg * crit_dmg)
            elem_mult, elem_msg = calculate_element_multiplier(player_elem, target["element"])
            final_dmg = max(1, int(raw_dmg * elem_mult))

            target["hp"] -= final_dmg
            # Speed extra attack (combo)
            wtype = get_weapon_type_stats(player.get("weapon", ""))
            if wtype["speed"] >= 4 and random.randint(1, 100) <= 30:
                extra = max(1, int(final_dmg * 0.5))
                target["hp"] -= extra
                final_dmg += extra
                battle_log.append("  ⚡ 連擊！" if player.get("lang") != "en" else "  ⚡ Combo!")
            # Heavy weapon stun
            if wtype["speed"] <= 1 and is_crit and random.randint(1, 100) <= 25:
                target["stunned"] = True
                battle_log.append("  💫 眩暈！" if player.get("lang") != "en" else "  💫 Stun!")
            crit_text = ("💥 CRIT!" if player.get("lang") == "en" else "💥 暴擊！") if is_crit else ""
            if player.get("lang") == "en":
                battle_log.append(f"You hit {target['name']} for {final_dmg} dmg {crit_text}{elem_msg}")
            else:
                battle_log.append(f"你攻擊 {target['name']} 造成 {final_dmg} 傷害 {crit_text}{elem_msg}")
            if power_msg:
                battle_log.append(f"  {power_msg}")

            if target["hp"] <= 0:
                total_kills += 1
                xp_gain = target["xp_reward"]
                gold_gain = random.randint(xp_gain // 2, xp_gain)
                total_xp += xp_gain
                total_gold += gold_gain
                if player.get("lang") == "en":
                    battle_log.append(f"✅ Defeated {target['name']}! +{xp_gain} XP / {gold_gain} gold")
                else:
                    battle_log.append(f"✅ 擊敗 {target['name']}！獲得 {xp_gain} XP / {gold_gain} 金幣")
                continue

            if skip_turn:
                if player.get("lang") == "en":
                    battle_log.append("  (Enemy controlled, no counter)")
                else:
                    battle_log.append("  （敵人被控制，本回合無法反擊）")
                continue

            # Enemy attacks
            # Range reduces counter damage
            wtype = get_weapon_type_stats(player.get("weapon", ""))
            range_reduce = 0.5 if wtype["range"] >= 4 else 1.0
            total_taken = 0
            if m["hp"] > 0:
                    taken = max(2, int((m["atk"] - int(defense / 2.5)) * range_reduce))
                    if p_effect.lower() in ["shield", "harden", "armor_up", "absolute_defense", "invulnerable"]:
                        taken = max(1, taken - 15)
                    total_taken += taken
            player["hp"] -= total_taken
            if player.get("lang") == "en":
                battle_log.append(f"Enemy hits you for {total_taken} (HP: {max(0, player['hp'])})")
            else:
                battle_log.append(f"敵人反擊，你受到 {total_taken} 點傷害（剩餘 HP: {max(0, player['hp'])}）")

            if player["hp"] <= 0:
                if player.get("lang") == "en":
                    battle_log.append("❌ Defeated! HP reached 0.")
                else:
                    battle_log.append("❌ 戰敗！生命值歸零。")
                player["hp"] = max(30, int(player["max_hp"] * 0.2))  # soft revive
                break

        waves_fought += 1
        if player["hp"] <= 0:
            break

    # Apply rewards
    player["gold"] += total_gold
    level_msgs = gain_xp(player, total_xp)
    for msg in level_msgs:
        battle_log.append(msg)

    # Persist
    save_player_data(player)

    return {
        "ok": True,
        "kills": total_kills,
        "xp_gained": total_xp,
        "gold_gained": total_gold,
        "start_lvl": start_lvl,
        "end_lvl": player["level"],
        "start_hp": start_hp,
        "end_hp": player["hp"],
        "died": any("戰败" in line or "Defeated" in line for line in battle_log),
        "max_hp": player["max_hp"],
        "waves": waves_fought,
        "log": battle_log,
        "player": {
            "level": player["level"],
            "xp": player["xp"],
            "xp_to_next_level": player["xp_to_next_level"],
            "xp_percent": min(100, int(player["xp"] / max(1, player["xp_to_next_level"]) * 100)),
            "hp": player["hp"],
            "max_hp": player["max_hp"],
            "hp_percent": min(100, int(player["hp"] / max(1, player["max_hp"]) * 100)),
            "gold": player["gold"],
            "combat_power": calculate_combat_power(player)
        }
    }


def get_player_status(player: Dict) -> Dict[str, Any]:
    """Return a clean status object for the frontend."""
    cp = calculate_combat_power(player)
    atk, defense, crit_ch, crit_dmg, p_effect, p_desc, w_elem = calculate_stats(player)
    xp = player.get("xp", 0)
    xp_need = max(1, player.get("xp_to_next_level", 100))
    xp_pct = min(100, int(xp / xp_need * 100))
    weapons = load_weapons()
    armors = load_armors()
    w_name = player.get("weapon", "iron_sword")
    a_name = player.get("armor", "iron_armor")
    w_data = weapons.get(w_name, {})
    a_data = armors.get(a_name, {})
    w_tier = get_gear_tier_score(w_data.get("atk", 0), "weapon") if w_data else "D"
    a_tier = get_gear_tier_score(a_data, "armor") if a_data else "D"
    lang = player.get("lang", "zh")
    if lang == "zh":
        w_desc = w_data.get("desc_zh") or w_data.get("desc_en") or ""
        a_desc = a_data.get("desc_zh") or a_data.get("desc_en") or ""
    else:
        w_desc = w_data.get("desc_en") or w_data.get("desc_zh") or ""
        a_desc = a_data.get("desc_en") or a_data.get("desc_zh") or ""
    return {
        "username": player["username"],
        "level": player["level"],
        "xp": xp,
        "xp_to_next_level": xp_need,
        "xp_percent": xp_pct,
        "hp": player["hp"],
        "max_hp": player["max_hp"],
        "gold": player["gold"],
        "abyss_tokens": player.get("abyss_tokens", 0),
        "abyss_floor": player.get("abyss_floor", 1),
        "weapon": format_gear_name(player["weapon"], player, "weapon"),
        "weapon_raw": w_name,
        "weapon_tier": w_tier,
        "weapon_level": player.get("weapon_levels", {}).get(w_name, 0),
        "weapon_desc": w_desc,
        "armor": format_gear_name(player["armor"], player, "armor"),
        "armor_raw": a_name,
        "armor_tier": a_tier,
        "armor_level": player.get("armor_levels", {}).get(a_name, 0),
        "armor_desc": a_desc,
        "equipped_power": player.get("equipped_power") or "None",
        "power_effect": p_effect,
        "power_desc": p_desc,
        "combat_power": cp,
        "atk": atk,
        "base_atk": 10 + (player["level"] - 1) * 4,
        "bonus_atk": max(0, atk - (10 + (player["level"] - 1) * 4)),
        "defense": defense,
        "base_def": 0,
        "bonus_def": defense,
        "base_hp": 120 + (player["level"] - 1) * 35,
        "bonus_hp": max(0, player["max_hp"] - (120 + (player["level"] - 1) * 35)),
        "crit_ch": crit_ch,
        "crit_dmg": round(crit_dmg, 2),
        "weapon_element": w_elem,
        "weapon_range": get_weapon_type_stats(w_name)["range"],
        "weapon_speed": get_weapon_type_stats(w_name)["speed"],
        "weapon_style": get_weapon_type_stats(w_name)["style"],
        "armor_slot": get_armor_slot(a_name),
        "armor_slots": get_equipped_armors(player),
        "slot_tiers": {s: get_gear_tier_score(load_armors().get(n, {}), "armor", s) if n else "D" for s, n in get_equipped_armors(player).items()},
        "slot_descs": {s: (load_armors().get(n, {}).get("desc_zh") if player.get("lang") == "zh" else load_armors().get(n, {}).get("desc_en")) or "" for s, n in get_equipped_armors(player).items() if n},
        "lang": player.get("lang", "zh"),
        "potions": player.get("potions", {"minor_potion": 0, "strength_potion": 0}),
        "unlocked_weapons_count": len(player.get("unlocked_weapons", [])),
        "unlocked_armors_count": len(player.get("unlocked_armors", [])),
        "powers_count": len(player.get("powers", [])),
        "password_hint": "***",
    }


# ========== Blacksmith / Power / Abyss ==========

def get_gear_tier_score(item_dict_or_score, category="weapon", slot=None):
    catalog = load_game_catalog()
    if category == "weapon":
        all_scores = sorted([w["atk"] for w in catalog["weapons"].values()], reverse=True)
        score = item_dict_or_score.get("atk", 0) if isinstance(item_dict_or_score, dict) else item_dict_or_score
    else:
        # Per-slot ranking
        if slot:
            slot_items = [(a["defense"] + a["hp_bonus"]) for n, a in catalog["armors"].items() if slot in n]
            all_scores = sorted(slot_items, reverse=True) if slot_items else sorted([a["defense"] + a["hp_bonus"] for a in catalog["armors"].values()], reverse=True)
        else:
            all_scores = sorted([a["defense"] + a["hp_bonus"] for a in catalog["armors"].values()], reverse=True)
        score = (item_dict_or_score.get("defense", 0) + item_dict_or_score.get("hp_bonus", 0)) if isinstance(
            item_dict_or_score, dict) else item_dict_or_score
    try:
        rank = next(i for i, s in enumerate(all_scores) if score >= s) + 1
    except StopIteration:
        rank = len(all_scores)
    total = len(all_scores) or 105
    if rank <= 5:
        return "S"
    elif rank <= int(total * 0.15):
        return "A"
    elif rank <= int(total * 0.40):
        return "B"
    elif rank <= int(total * 0.75):
        return "C"
    return "D"


def forge_weapons(player: Dict, count: int = 1) -> Dict[str, Any]:
    """Gacha weapons. Cost handled by caller. Returns results list."""
    weapons_db = load_weapons()
    w_names = list(weapons_db.keys())
    weights = []
    for x in w_names:
        tier = get_gear_tier_score(weapons_db[x]["atk"], "weapon")
        base = max(1, int(1000 / (weapons_db[x]["atk"] ** 0.6)))
        if tier == "S":
            base = max(1, base // 50)  # extremely rare
        elif tier == "A":
            base = max(1, base // 8)
        weights.append(base)
    results = []
    for w in random.choices(w_names, weights=weights, k=count):
        tier = get_gear_tier_score(weapons_db[w]["atk"], "weapon")
        entry = {"name": w, "display": get_display_name(w, player.get("lang", "zh")), "atk": weapons_db[w]["atk"], "tier": tier, "new": False, "upgraded": False, "refund": 0}
        if w not in player["unlocked_weapons"]:
            player["unlocked_weapons"].append(w)
            entry["new"] = True
        else:
            w_lvs = player.setdefault("weapon_levels", {})
            w_lvs[w] = w_lvs.get(w, 0) + 1
            player["gold"] += 1000
            entry["upgraded"] = True
            entry["refund"] = 1000
            entry["new_level"] = w_lvs[w]
        results.append(entry)
    player["unlocked_weapons"].sort(
        key=lambda x: get_effective_weapon(x, player, weapons_db)["atk"], reverse=True)
    save_player_data(player)
    return {"ok": True, "results": results, "gold": player["gold"]}


def forge_armors(player: Dict, count: int = 1) -> Dict[str, Any]:
    armors_db = load_armors()
    a_names = list(armors_db.keys())
    weights = []
    for x in a_names:
        tier = get_gear_tier_score(armors_db[x], "armor")
        score = armors_db[x]["defense"] + armors_db[x]["hp_bonus"]
        base = max(1, int(2000 / (score ** 0.6)))
        if tier == "S":
            base = max(1, base // 50)
        elif tier == "A":
            base = max(1, base // 8)
        weights.append(base)
    results = []
    for a in random.choices(a_names, weights=weights, k=count):
        tier = get_gear_tier_score(armors_db[a], "armor")
        entry = {
            "name": a, "defense": armors_db[a]["defense"], "hp_bonus": armors_db[a]["hp_bonus"],
            "tier": tier, "new": False, "upgraded": False, "refund": 0
        }
        if a not in player["unlocked_armors"]:
            player["unlocked_armors"].append(a)
            entry["new"] = True
        else:
            a_lvs = player.setdefault("armor_levels", {})
            a_lvs[a] = a_lvs.get(a, 0) + 1
            player["gold"] += 1000
            entry["upgraded"] = True
            entry["refund"] = 1000
            entry["new_level"] = a_lvs[a]
        results.append(entry)
    player["unlocked_armors"].sort(
        key=lambda x: get_effective_armor(x, player, armors_db)["defense"] +
                      get_effective_armor(x, player, armors_db)["hp_bonus"], reverse=True)
    save_player_data(player)
    return {"ok": True, "results": results, "gold": player["gold"]}


def upgrade_current_weapon(player: Dict) -> Dict[str, Any]:
    weapons = load_weapons()
    curr = player["weapon"]
    if curr not in weapons:
        return {"ok": False, "error": "當前武器無效"}
    w_eff = get_effective_weapon(curr, player, weapons)
    lv = w_eff["upgrade_lv"]
    cost = int(w_eff["atk"] * 200 * (1.5 ** lv))
    if player["gold"] < cost:
        return {"ok": False, "error": f"金幣不足（需要 {cost:,}g）"}
    next_atk = int(weapons[curr]["atk"] * (1.15 ** (lv + 1)))
    player["gold"] -= cost
    w_lvs = player.setdefault("weapon_levels", {})
    w_lvs[curr] = lv + 1
    save_player_data(player)
    return {
        "ok": True, "name": curr, "old_lv": lv, "new_lv": lv + 1,
        "old_atk": w_eff["atk"], "new_atk": next_atk, "cost": cost, "gold": player["gold"]
    }


def upgrade_current_armor(player: Dict, slot: str = None) -> Dict[str, Any]:
    armors = load_armors()
    slots = get_equipped_armors(player)
    if slot and slot in slots and slots[slot]:
        curr = slots[slot]
    else:
        curr = player.get("armor")
    if not curr or curr not in armors:
        return {"ok": False, "error": "當前防具無效"}
    a_eff = get_effective_armor(curr, player, armors)
    lv = a_eff["upgrade_lv"]
    cost = int((a_eff["defense"] + a_eff["hp_bonus"]) * 150 * (1.5 ** lv))
    if player["gold"] < cost:
        return {"ok": False, "error": f"金幣不足（需要 {cost:,}g）"}
    next_def = int(armors[curr]["defense"] * (1.12 ** (lv + 1)))
    next_hp = int(armors[curr]["hp_bonus"] * (1.12 ** (lv + 1)))
    player["gold"] -= cost
    a_lvs = player.setdefault("armor_levels", {})
    a_lvs[curr] = lv + 1
    calculate_stats(player)
    player["hp"] = player["max_hp"]
    save_player_data(player)
    return {
        "ok": True, "name": curr, "old_lv": lv, "new_lv": lv + 1,
        "old_def": a_eff["defense"], "new_def": next_def,
        "old_hp": a_eff["hp_bonus"], "new_hp": next_hp,
        "cost": cost, "gold": player["gold"]
    }


def buy_potions(player: Dict, packs: int = 1) -> Dict[str, Any]:
    cost = 10000 * packs
    if player["gold"] < cost:
        return {"ok": False, "error": "金幣不足"}
    player["gold"] -= cost
    pots = player.setdefault("potions", {"minor_potion": 0, "strength_potion": 0})
    pots["minor_potion"] = pots.get("minor_potion", 0) + 5 * packs
    save_player_data(player)
    return {"ok": True, "gained": 5 * packs, "total": pots["minor_potion"], "gold": player["gold"]}


def pull_powers(player: Dict, count: int = 1) -> Dict[str, Any]:
    """Single=20000, 10x=180000 handled by caller."""
    powers = load_powers_db()
    results = []
    for p in random.choices(powers, weights=[x["weight"] for x in powers], k=count):
        entry = {
            "name": p["name"], "display": get_display_name(p["name"], player.get("lang", "zh")),
            "grade": p["grade"].upper(), "tier": p["grade"].upper(), "effect": p["effect"],
            "score": p["score"], "new": False, "refund": 0
        }
        if not any((x["name"] if isinstance(x, dict) else x) == p["name"] for x in player.get("powers", [])):
            # store full power dict
            player.setdefault("powers", []).append(p)
            entry["new"] = True
            if not player.get("equipped_power"):
                player["equipped_power"] = p["name"]
        else:
            refund = 5000 if count == 1 else 3000
            player["gold"] += refund
            entry["refund"] = refund
        results.append(entry)
    player["powers"].sort(key=lambda x: x.get("score", 0) if isinstance(x, dict) else 0, reverse=True)
    save_player_data(player)
    return {"ok": True, "results": results, "gold": player["gold"], "equipped": player.get("equipped_power")}


def equip_power(player: Dict, power_name: str) -> Dict[str, Any]:
    names = [p["name"] if isinstance(p, dict) else p for p in player.get("powers", [])]
    if power_name not in names:
        return {"ok": False, "error": "尚未擁有此超能力"}
    # Toggle: if already equipped, unequip
    if player.get("equipped_power") == power_name:
        player["equipped_power"] = None
    else:
        player["equipped_power"] = power_name
    save_player_data(player)
    return {"ok": True, "equipped": power_name, "status": get_player_status(player)}


def simulate_boss_rush(player: Dict, max_floors: int = 5) -> Dict[str, Any]:
    """Auto climb abyss for up to max_floors. Returns log + rewards."""
    monsters = load_monsters()
    if not monsters:
        return {"ok": False, "error": "No monsters"}
    start_floor = player.get("abyss_floor", 1)
    start_hp = player["hp"]
    total_gold = 0
    total_tokens = 0
    total_xp = 0
    log = []
    floors_cleared = 0

    for i in range(max_floors):
        if player["hp"] <= 0:
            break
        floor = player.get("abyss_floor", 1)
        # Random events (20% chance)
        if random.randint(1, 100) <= 20:
            evt = random.choice(["treasure", "shrine", "merchant"])
            if evt == "treasure":
                bonus = floor * 200
                player["gold"] += bonus
                log.append(f"🎁 發現寶箱！+{bonus}g")
            elif evt == "shrine":
                heal = int(player["max_hp"] * 0.3)
                player["hp"] = min(player["max_hp"], player["hp"] + heal)
                log.append(f"✨ 發現神殿！回復 {heal} HP")
            else:
                player["potions"] = player.get("potions", 0) + 1
                log.append("🛒 遇到商人！獲得藥劑")
        base_boss = random.choice(monsters)
        scaling = 1.0 + (floor - 1) * 0.2
        boss_hp = int((base_boss["hp"] * 2.2) * scaling)
        boss_max = boss_hp
        boss_atk = int((base_boss["atk"] * 1.5) * scaling)
        boss_elem = base_boss.get("element", "none")
        log.append(f"--- 第 {floor} 層首领: {base_boss['name']} (HP:{boss_hp}, ATK:{boss_atk}) ---")

        while boss_hp > 0 and player["hp"] > 0:
            potion_msg = check_and_use_auto_potion(player)
            if potion_msg:
                log.append(potion_msg)
            atk, defense, crit_ch, crit_dmg, p_effect, p_desc, player_elem = calculate_stats(player)
            bonus_dmg, skip_turn, dot, heal, power_msg = apply_power_effect(p_effect, player)
            if dot > 0:
                boss_hp -= dot
            is_crit = random.randint(1, 100) <= crit_ch
            base_dmg = random.randint(15, 25) + atk + bonus_dmg
            elem_mult, elem_txt = calculate_element_multiplier(player_elem, boss_elem)
            final_dmg = int((base_dmg * crit_dmg if is_crit else base_dmg) * elem_mult)
            boss_hp -= final_dmg
            crit_label = " 💥暴擊" if is_crit else ""
            log.append(f"你造成 {final_dmg} 傷害{crit_label} {elem_txt} | Boss HP: {max(0, boss_hp)}")
            if power_msg:
                log.append(f"  {power_msg}")

            if boss_hp <= 0:
                reward_gold = floor * 800
                reward_tokens = max(1, floor)
                player["gold"] += reward_gold
                player["abyss_tokens"] = player.get("abyss_tokens", 0) + reward_tokens
                player["abyss_floor"] = floor + 1
                xp_gain = floor * 40
                level_msgs = gain_xp(player, xp_gain)
                total_gold += reward_gold
                total_tokens += reward_tokens
                total_xp += xp_gain
                floors_cleared += 1
                log.append(f"✅ 擊杀第 {floor} 層！+{reward_gold:,}g +{reward_tokens}🔮 +{xp_gain}XP")
                # Chance for S tier drop on high floors
                if floor >= 5 and random.randint(1, 100) <= min(30, floor * 3):
                    weapons = load_weapons()
                    sorted_w = sorted(weapons.items(), key=lambda x: x[1]["atk"], reverse=True)
                    pool = [w[0] for w in sorted_w[:max(1, len(sorted_w)//10)]]
                    drop = random.choice(pool)
                    if drop not in player.get("unlocked_weapons", []):
                        player.setdefault("unlocked_weapons", []).append(drop)
                        log.append(f"🎁 獲得 S 級武器: {drop}")
                    else:
                        w_lvs = player.setdefault("weapon_levels", {})
                        w_lvs[drop] = w_lvs.get(drop, 0) + 1
                        log.append(f"🎁 S 級武器 {drop} 強化 +1")
                for m in level_msgs:
                    log.append(m)
                break

            if skip_turn:
                log.append("  （首领被控製，本回合無法反擊）")
                continue

            taken = max(5, boss_atk - int(defense / 3))
            if p_effect.lower() in ["shield", "harden", "armor_up", "absolute_defense", "invulnerable"]:
                taken = max(2, taken - 25)
            player["hp"] -= taken
            log.append(f"首领反擊，你受到 {taken} 傷害（HP: {max(0, player['hp'])}）")
            if player["hp"] <= 0:
                log.append(f"❌ 在第 {floor} 層倒下，撤回地面。")
                player["hp"] = max(30, int(player["max_hp"] * 0.2))
                break

        if player["hp"] <= 0:
            break

    save_player_data(player)
    return {
        "ok": True,
        "floors_cleared": floors_cleared,
        "start_floor": start_floor,
        "end_floor": player.get("abyss_floor", 1),
        "gold_gained": total_gold,
        "tokens_gained": total_tokens,
        "xp_gained": total_xp,
        "end_hp": player["hp"],
        "died": any("戰败" in line or "Defeated" in line for line in log),
        "max_hp": player["max_hp"],
        "log": log,
        "player": get_player_status(player)
    }


def abyss_shop_exchange(player: Dict, item: str) -> Dict[str, Any]:
    """
    item: 'potion' | 'gold' | 's_weapon' | 'a_weapon' | 's_armor' | 'a_armor'
    Expanded to support A-S weapons and armors as requested.
    """
    tokens = player.get("abyss_tokens", 0)
    prices = {
        "potion": 5,
        "gold": 20,
        "a_weapon": 30,
        "a_armor": 30,
    }
    if item not in prices:
        return {"ok": False, "error": "無效选项"}
    cost = prices[item]
    if tokens < cost:
        return {"ok": False, "error": f"深淵代幣不足（需要 {cost}）"}

    player["abyss_tokens"] = tokens - cost
    msg = ""

    if item == "potion":
        pots = player.setdefault("potions", {"minor_potion": 0, "strength_potion": 0})
        pots["minor_potion"] = pots.get("minor_potion", 0) + 10
        msg = "獲得微型生命藥劑 x10"
    elif item == "gold":
        player["gold"] += 100000
        msg = "獲得 100,000 金幣"
    elif item == "a_weapon":
        weapons = load_weapons()
        sorted_w = sorted(weapons.items(), key=lambda x: x[1]["atk"], reverse=True)
        total = len(sorted_w)
        pool = [w[0] for w in sorted_w if get_gear_tier_score(w[1]["atk"], "weapon") == "A"] or [w[0] for w in sorted_w[:5]]
        reward = random.choice(pool)
        is_new = reward not in player.get("unlocked_weapons", [])
        if is_new:
            player.setdefault("unlocked_weapons", []).append(reward)
            player["unlocked_weapons"].sort(
                key=lambda x: get_effective_weapon(x, player, weapons)["atk"], reverse=True)
        else:
            w_lvs = player.setdefault("weapon_levels", {})
            w_lvs[reward] = w_lvs.get(reward, 0) + 1
        tier = "A"
        msg = f"獲得 {tier} 級武器: {reward} (ATK:{weapons[reward]['atk']})" + (" [新]" if is_new else " [強化+1]")
    elif item == "a_armor":
        armors = load_armors()
        sorted_a = sorted(armors.items(), key=lambda x: x[1]["defense"] + x[1]["hp_bonus"], reverse=True)
        total = len(sorted_a)
        pool = [a[0] for a in sorted_a if get_gear_tier_score(a[1], "armor") == "A"] or [a[0] for a in sorted_a[:5]]
        reward = random.choice(pool)
        is_new = reward not in player.get("unlocked_armors", [])
        if is_new:
            player.setdefault("unlocked_armors", []).append(reward)
            player["unlocked_armors"].sort(
                key=lambda x: get_effective_armor(x, player, armors)["defense"] +
                              get_effective_armor(x, player, armors)["hp_bonus"], reverse=True)
        else:
            a_lvs = player.setdefault("armor_levels", {})
            a_lvs[reward] = a_lvs.get(reward, 0) + 1
        tier = "A"
        a = armors[reward]
        msg = f"獲得 {tier} 級防具: {reward} (DEF:{a['defense']} HP+:{a['hp_bonus']})" + (" [新]" if is_new else " [強化+1]")

    save_player_data(player)
    return {"ok": True, "message": msg, "tokens": player["abyss_tokens"], "status": get_player_status(player)}



def get_weapon_type_stats(name: str) -> dict:
    """Return range (1-5), speed (1-5), style based on weapon name."""
    if not name:
        return {"range": 2, "speed": 3, "style": "melee", "range_name": "short", "speed_name": "medium"}
    n = name.lower()
    if any(x in n for x in ["bow", "crossbow", "rifle", "staff"]):
        return {"range": 5, "speed": 3, "style": "ranged", "range_name": "long", "speed_name": "medium"}
    if any(x in n for x in ["dagger", "rapier", "sabre", "scimitar", "cutlass"]):
        return {"range": 1, "speed": 5, "style": "melee", "range_name": "short", "speed_name": "fast"}
    if any(x in n for x in ["spear", "lance", "halberd", "glaive", "naginata", "trident"]):
        return {"range": 3, "speed": 3, "style": "reach", "range_name": "medium", "speed_name": "medium"}
    if any(x in n for x in ["hammer", "mace", "axe", "club", "flail"]):
        return {"range": 1, "speed": 1, "style": "heavy", "range_name": "short", "speed_name": "slow"}
    if any(x in n for x in ["greatsword", "claymore", "zweihander", "scythe"]):
        return {"range": 3, "speed": 1, "style": "heavy", "range_name": "medium", "speed_name": "slow"}
    return {"range": 2, "speed": 3, "style": "melee", "range_name": "short", "speed_name": "medium"}

def get_armor_slot(name: str) -> str:
    """Return armor slot type."""
    if not name:
        return "chest"
    n = name.lower()
    if any(x in n for x in ["helmet", "helm", "crown", "hood"]):
        return "helmet"
    if any(x in n for x in ["boot", "greave", "shoe"]):
        return "boots"
    if any(x in n for x in ["glove", "gauntlet", "bracer"]):
        return "gloves"
    if any(x in n for x in ["robe", "cloak", "cape", "shroud", "vestment"]):
        return "cloak"
    if any(x in n for x in ["shield"]):
        return "shield"
    return "chest"


ARMOR_SLOTS = ["helmet", "chest", "gloves", "boots", "cloak"]

def get_equipped_armors(player: dict) -> dict:
    """Return dict of slot -> armor name. Migrates old single armor to chest."""
    slots = player.get("armor_slots")
    if not isinstance(slots, dict):
        slots = {}
    # migrate old single armor
    if not slots and player.get("armor"):
        old = player["armor"]
        slot = get_armor_slot(old)
        if slot not in ARMOR_SLOTS:
            slot = "chest"
        slots[slot] = old
        player["armor_slots"] = slots
    # ensure all slots exist
    for s in ARMOR_SLOTS:
        slots.setdefault(s, None)
    return slots

def set_armor_slot(player: dict, slot: str, name: str):
    slots = get_equipped_armors(player)
    slots[slot] = name
    player["armor_slots"] = slots
    # keep legacy armor field as chest for compatibility
    if slot == "chest":
        player["armor"] = name


def auto_chinese_name(item_id: str) -> str:
    """Convert English ID to Traditional Chinese name."""
    parts = item_id.replace("_", " ").split()
    pre_map = {
        "rusty": "生鏽", "worn": "破舊", "sturdy": "堅固", "fine": "精良",
        "masterwork": "大師", "legendary": "傳說", "ancient": "遠古",
        "blessed": "祝福", "cursed": "詛咒", "enchanted": "附魔",
        "royal": "皇家", "elite": "精英", "divine": "神聖",
    }
    mat_map = {
        "iron": "鐵", "steel": "鋼", "bronze": "青銅", "silver": "銀", "gold": "金",
        "mithril": "秘銀", "crystal": "水晶", "dragon": "龍", "demon": "惡魔",
        "angel": "天使", "void": "虛空", "cosmic": "宇宙", "obsidian": "黑曜",
        "ruby": "紅寶石", "sapphire": "藍寶石", "leather": "皮革", "shadow": "暗影",
        "wind": "風", "fire": "火焰", "ice": "寒冰", "swift": "迅捷", "heavy": "沉重",
        "light": "輕盈", "assassin": "刺客", "mage": "法師", "warrior": "戰士",
        "archer": "射手", "cloth": "布", "mystic": "神秘", "star": "星辰",
        "quantum": "量子", "death": "死亡", "earth": "大地", "celestial": "天界",
        "abyssal": "深淵", "phoenix": "鳳凰", "titan": "泰坦", "eternal": "永恆",
        "godslayer": "弒神", "windwalker": "風行",
    }
    slot_map = {
        "helmet": "頭盔", "helm": "頭盔", "boots": "靴子", "boot": "靴",
        "gloves": "手套", "glove": "手套", "cloak": "披風", "cape": "披風",
        "plate": "板甲", "mail": "甲", "armor": "甲", "robe": "袍",
        "sword": "劍", "dagger": "匕首", "axe": "斧", "bow": "弓",
        "spear": "矛", "mace": "錘", "rifle": "步槍", "scythe": "鐮",
    }
    result = []
    for p in parts:
        if p in pre_map:
            result.append(pre_map[p])
        elif p in mat_map:
            result.append(mat_map[p])
        elif p in slot_map:
            result.append(slot_map[p])
        elif p.isdigit() or p.startswith("+"):
            result.append(p)
        else:
            result.append(p)
    return "".join(result) if result else item_id

def get_display_name(item_id: str, lang: str = "zh") -> str:
    """Return Chinese display name if lang is zh, else original id."""
    if not item_id:
        return "—"
    if lang != "zh":
        return item_id
    names = {'wooden_stick': '木棒', 'rusty_dagger': '生鏽匕首', 'broken_sword': '斷劍', 'wooden_club': '木棍', 'rusty_sword': '生鏽劍', 'stone_axe': '石斧', 'bronze_dagger': '青銅匕首', 'copper_sword': '銅劍', 'hunting_bow': '獵弓', 'iron_dagger': '鐵匕首', 'iron_spear': '鐵矛', 'iron_sword': '鐵劍', 'iron_axe': '鐵斧', 'iron_mace': '鐵錘', 'steel_dagger': '鋼匕首', 'steel_sword': '鋼劍', 'steel_rapier': '鋼細劍', 'steel_halberd': '鋼戟', 'steel_warhammer': '鋼戰錘', 'silver_sword': '銀劍', 'longbow': '長弓', 'crossbow': '弩', 'heavy_crossbow': '重弩', 'diamond_blade': '鑽石刃', 'katana': '武士刀', 'nodachi': '野太刀', 'claymore': '大劍', 'zweihander': '雙手劍', 'flamberge': '火焰劍', 'scimitar': '彎刀', 'cutlass': '短彎刀', 'sabre': '軍刀', 'trident': '三叉戟', 'glaive': '長刀', 'naginata': '薙刀', 'morningstar': '晨星錘', 'flail': '鏈錘', 'battleaxe': '戰斧', 'greataxe': '巨斧', 'war_scythe': '戰鐮', 'mithril_sword': '祕銀劍', 'mithril_bow': '祕銀弓', 'mithril_spear': '祕銀矛', 'adamantite_blade': '精金刃', 'adamantite_axe': '精金斧', 'orichalcum_sword': '奧利哈剛劍', 'godly_katana': '神刀', 'obsidian_dagger': '黑曜匕首', 'crystal_sword': '水晶劍', 'emerald_blade': '翡翠刃', 'ruby_greatsword': '紅寶石巨劍', 'sapphire_spear': '藍寶石矛', 'flame_sword': '火焰劍', 'inferno_blade': '煉獄刃', 'magma_hammer': '岩漿錘', 'frost_blade': '冰霜刃', 'glacial_lance': '冰川槍', 'thunder_axe': '雷斧', 'storm_bow': '風暴弓', 'lightning_spear': '閃電矛', 'wind_fan': '風扇', 'tornado_blade': '龍卷刃', 'earth_hammer': '大地錘', 'quake_mace': '地震錘', 'shadow_dagger': '暗影匕首', 'nightmare_scythe': '夢魘鐮', 'void_blade': '虛空刃', 'abyssal_greatsword': '深淵巨劍', 'light_saber': '光劍', 'solar_blade': '太陽刃', 'lunar_bow': '月弓', 'starlight_staff': '星光杖', 'eclipse_scythe': '日蝕鐮', 'dragon_slayer': '屠龍劍', 'wyvern_fang': '雙足飛龍牙', 'hydra_whip': '九頭蛇鞭', 'phoenix_bow': '鳳凰弓', 'demon_blade': '惡魔刃', 'archdemon_scythe': '大惡魔鐮', 'angelic_sword': '天使劍', 'seraphim_lance': '熾天使槍', 'valkyrie_spear': '女武神矛', 'paladin_hammer': '聖騎士錘', 'excalibur': '王者之劍', 'durandal': '杜蘭達爾', 'joyeuse': '歡悅劍', 'kusanagi': '草薙劍', 'gungnir': '岡格尼爾', 'mjolnir': '雷神之錘', 'gram': '格拉姆', 'tyrfing': '提爾鋒', 'gae_bolg': '蓋伯爾加', 'ame_no_habakiri': '天之羽羽斬', 'masamune': '正宗', 'muramasa': '村正', 'soul_reaver': '噬魂者', 'death_scythe': '死亡鐮', 'chaos_blade': '混沌刃', 'order_sword': '秩序劍', 'chrono_dagger': '時空匕首', 'quantum_rifle': '量子步槍', 'cosmic_spear': '宇宙矛', 'divine_judgement': '神罰', 'world_ender': '滅世者', 'genesis_blade': '創世刃', 'cloth_tunic': '布衣', 'tattered_rags': '破布衣', 'leather_vest': '皮背心', 'padded_armor': '軟甲', 'hide_armor': '獸皮甲', 'studded_leather': '釘皮甲', 'ring_mail': '環甲', 'chain_shirt': '鎖子甲', 'scale_mail': '鱗甲', 'brigandine': '布里根甲', 'chainmail_hauberk': '鎖子甲衫', 'breastplate': '胸甲', 'splint_armor': '板條甲', 'iron_armor': '鐵甲', 'banded_mail': '帶甲', 'half_plate': '半板甲', 'steel_plate': '鋼板甲', 'knight_armor': '騎士甲', 'gothic_plate': '哥特板甲', 'diamond_armor': '鑽石甲', 'bronze_cuirass': '青銅胸甲', 'copper_plate': '銅板甲', 'silver_mail': '銀鎖甲', 'gold_armor': '金甲', 'platinum_plate': '鉑金甲', 'mithril_shirt': '祕銀衫', 'mithril_plate': '祕銀板甲', 'adamantite_armor': '精金甲', 'orichalcum_plate': '奧利哈剛甲', 'titanium_suit': '鈦金戰甲', 'obsidian_armor': '黑曜甲', 'crystal_plate': '水晶甲', 'emerald_mail': '翡翠鎖甲', 'ruby_plate': '紅寶石甲', 'sapphire_armor': '藍寶石甲', 'amethyst_robes': '紫水晶袍', 'quartz_armor': '石英甲', 'granite_plate': '花崗岩甲', 'marble_cuirass': '大理石胸甲', 'bone_armor': '骨甲', 'chitin_plate': '甲殼板甲', 'dragon_scale': '龍鱗甲', 'wyvern_hide': '飛龍皮', 'drake_mail': '幼龍甲', 'basilisk_armor': '蛇蜥甲', 'hydra_scale': '九頭蛇鱗', 'phoenix_feather_robe': '鳳凰羽袍', 'griffin_hide': '獅鷲皮', 'manticore_plate': '蠍獅甲', 'chimera_mail': '奇美拉甲', 'kraken_shell': '海妖殼', 'leviathan_plate': '利維坦甲', 'behemoth_hide': '貝希摩斯皮', 'tarrasque_carapace': '泰拉斯奎甲', 'demon_plate': '惡魔甲', 'archdemon_armor': '大惡魔甲', 'angelic_vestments': '天使法衣', 'seraphim_plate': '熾天使甲', 'valkyrie_armor': '女武神甲', 'paladin_plate': '聖騎士甲', 'crusader_mail': '十字軍甲', 'templar_armor': '聖殿甲', 'samurai_yoroi': '武士鎧', 'shogun_armor': '將軍甲', 'ninja_garb': '忍者裝', 'shinobi_shroud': '忍者之衣', 'assassin_cloak': '刺客鬥篷', 'shadow_cloak': '暗影鬥篷', 'void_armor': '虛空甲', 'abyssal_plate': '深淵甲', 'celestial_robes': '天界袍', 'astral_armor': '星界甲', 'ethereal_mail': '以太甲', 'spectral_shroud': '幽魂衣', 'ghostly_robes': '幽靈袍', 'necromancer_robes': '死靈法师袍', 'lich_vestments': '巫妖法衣', 'vampire_cape': '吸血鬼鬥篷', 'werewolf_pelt': '狼人皮', 'berserker_hide': '狂戰士皮', 'barbarian_armor': '野蠻人甲', 'gladiator_gear': '角鬥士裝', 'spartan_cuirass': '斯巴達胸甲', 'roman_lorica': '羅馬鎧', 'viking_mail': '維京甲', 'celtic_tunic': '凱爾特衣', 'druid_vestments': '德魯伊法衣', 'bark_armor': '樹皮甲', 'ironwood_plate': '鐵木甲', 'elderwood_mail': '古木甲', 'magma_plate': '岩漿甲', 'volcanic_armor': '火山甲', 'frost_armor': '冰霜甲', 'glacial_plate': '冰川甲', 'storm_mail': '風暴甲', 'thunder_plate': '雷霆甲', 'solar_armor': '太陽甲', 'lunar_vestments': '月之法衣', 'eclipse_plate': '日蝕甲', 'starlight_mail': '星光甲', 'cosmic_armor': '宇宙甲', 'quantum_suit': '量子戰甲', 'chrono_plate': '時空甲', 'divine_aegis': '神聖庇護', 'godslayer_armor': '弒神甲', 'Fire': '火焰', 'Water': '水流', 'Ground': '大地', 'Wind': '疾風', 'Strength': '力量', 'Explosion': '爆炸', 'Heal': '治癒', 'Gravitation': '重力', 'Rule': '律令', 'Time': '時間', 'Ruin': '毀滅', 'Sun': '太陽', 'Ice': '寒冰', 'Powerless': '無力', 'Speed': '極速', 'Mind': '精神', 'Ores': '礦石', 'Lightning': '閃電', 'Shadow': '暗影', 'Light': '光明', 'Space': '空間', 'Void': '虛空', 'Chaos': '混沌', 'Order': '秩序', 'Reality': '現實', 'Soul': '靈魂', 'Blood': '鮮血', 'Bone': '骸骨', 'Poison': '毒素', 'Acid': '酸蝕', 'Lava': '熔岩', 'Magma': '岩漿', 'Crystal': '水晶', 'Metal': '金屬', 'Wood': '木頭', 'Nature': '自然', 'Beast': '野獸', 'Dragon': '龍', 'Phoenix': '鳳凰', 'Demon': '惡魔', 'Angel': '天使', 'Ghost': '幽靈', 'Illusion': '幻象', 'Dream': '夢境', 'Nightmare': '夢魘', 'Fear': '恐懼', 'Rage': '狂怒', 'Love': '愛', 'Hope': '希望', 'Despair': '絕望', 'Fate': '命運', 'Destiny': '天命', 'Karma': '業力', 'Luck': '幸運', 'Fortune': '好運', 'Misfortune': '厄運', 'Sound': '聲波', 'Vibration': '震動', 'Plasma': '等離子', 'Nuclear': '核能', 'Atomic': '原子', 'Quantum': '量子', 'Gravity_Well': '重力井', 'Black_Hole': '黑洞', 'Star': '星辰', 'Moon': '月亮', 'Eclipse': '日蝕', 'Meteor': '流星', 'Comet': '彗星', 'Storm': '風暴', 'Hurricane': '颶風', 'Tornado': '龍卷', 'Tsunami': '海嘯', 'Earthquake': '地震', 'Volcano': '火山', 'Blizzard': '暴風雪', 'Frost': '霜凍', 'Mist': '迷霧', 'Smoke': '煙霧', 'Steam': '蒸汽', 'Sand': '沙', 'Dust': '塵', 'Mud': '泥', 'Slime': '史萊姆', 'Web': '蛛網', 'Venom': '毒液', 'Toxin': '毒素', 'Decay': '腐朽', 'Rot': '腐爛', 'Curse': '詛咒', 'Blessing': '祝福', 'Teleport': '傳送', 'Portal': '傳送門', 'Mirror': '鏡像', 'Copy': '複製', 'Steal': '竊取', 'Nullify': '無效化', 'Erase': '抹除', 'Create': '創造', 'Life': '生命', 'Death': '死亡', 'Rebirth': '重生', 'Immortality': '不朽', 'Invincibility': '無敵', 'Omniscience': '全知', 'trap': '陷阱'}
    return names.get(item_id, auto_chinese_name(item_id))


def get_effect_name(effect: str, lang: str = "zh") -> str:
    if lang != "zh":
        return effect
    names = {
        "absolute": "絕對", "trap": "陷阱", "burn": "灼燒", "slow": "緩速",
        "shield": "護盾", "dodge": "閃避", "rage": "狂怒", "burst": "爆發",
        "regen": "回復", "crush": "碾壓", "time_warp": "時間扭曲",
        "none": "無", "stun": "暈眩", "bleed": "流血", "pierce": "穿刺",
    }
    return names.get(effect.lower(), effect)


def check_daily_reward(player: dict) -> dict:
    """Check and give daily login reward."""
    from datetime import date
    today = str(date.today())
    last = player.get("last_login", "")
    if last != today:
        player["last_login"] = today
        player["login_streak"] = player.get("login_streak", 0) + 1
        if player.get("last_login_yesterday") != today:
            # Check if streak continues
            pass
        reward_gold = 1000 * min(player["login_streak"], 7)
        reward_tokens = min(player["login_streak"], 3)
        player["gold"] += reward_gold
        player["abyss_tokens"] = player.get("abyss_tokens", 0) + reward_tokens
        return {"ok": True, "gold": reward_gold, "tokens": reward_tokens, "streak": player["login_streak"]}
    return {"ok": False, "message": "今日已領取"}

def get_achievements(player: dict) -> list:
    """Get player achievements."""
    achievements = []
    if player.get("level", 0) >= 10:
        achievements.append({"id": "lv10", "name": "初出茅廬", "desc": "達到等級 10"})
    if player.get("level", 0) >= 50:
        achievements.append({"id": "lv50", "name": "高手", "desc": "達到等級 50"})
    if len(player.get("unlocked_weapons", [])) >= 10:
        achievements.append({"id": "w10", "name": "收藏家", "desc": "擁有 10 把武器"})
    if len(player.get("powers", [])) >= 5:
        achievements.append({"id": "p5", "name": "超能力者", "desc": "擁有 5 個超能力"})
    if player.get("abyss_floor", 0) >= 10:
        achievements.append({"id": "a10", "name": "深淵探索者", "desc": "到達深淵第 10 層"})
    if player.get("gold", 0) >= 100000:
        achievements.append({"id": "g100k", "name": "富豪", "desc": "擁有 100,000 金幣"})
    return achievements


# ========== Social Features ==========
CHAT_FILE = "saves/chat.json"
FRIENDS_FILE = "saves/friends.json"

def get_chat_messages(limit=50):
    """Get recent chat messages."""
    import json
    if not os.path.exists(CHAT_FILE):
        return []
    try:
        with open(CHAT_FILE, "r", encoding="utf-8") as f:
            msgs = json.load(f)
        return msgs[-limit:]
    except:
        return []

def send_chat_message(username: str, message: str):
    """Send a chat message."""
    import json
    from datetime import datetime
    msgs = get_chat_messages(100)
    msgs.append({
        "user": username,
        "msg": message[:200],
        "time": datetime.now().strftime("%H:%M")
    })
    os.makedirs("saves", exist_ok=True)
    with open(CHAT_FILE, "w", encoding="utf-8") as f:
        json.dump(msgs[-100:], f, ensure_ascii=False)

def get_friends(username: str) -> list:
    """Get friend list."""
    import json
    if not os.path.exists(FRIENDS_FILE):
        return []
    try:
        with open(FRIENDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get(username, [])
    except:
        return []

def add_friend(username: str, friend: str) -> dict:
    """Add a friend."""
    import json
    os.makedirs("saves", exist_ok=True)
    data = {}
    if os.path.exists(FRIENDS_FILE):
        with open(FRIENDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    if username not in data:
        data[username] = []
    if friend not in data[username] and friend != username:
        data[username].append(friend)
        with open(FRIENDS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        return {"ok": True}
    return {"ok": False, "error": "已是好友或無法添加"}

def send_gift(sender: str, receiver: str, gold: int) -> dict:
    """Send gold to another player."""
    sender_data = load_player_json(sender) or load_user_data(sender)
    receiver_data = load_player_json(receiver) or load_user_data(receiver)
    if not sender_data or not receiver_data:
        return {"ok": False, "error": "玩家不存在"}
    if sender_data.get("gold", 0) < gold:
        return {"ok": False, "error": "金幣不足"}
    if gold < 100:
        return {"ok": False, "error": "最少送 100 金幣"}
    sender_data["gold"] -= gold
    receiver_data["gold"] = receiver_data.get("gold", 0) + gold
    save_player_json(sender_data)
    save_player_json(receiver_data)
    return {"ok": True, "sent": gold}


def get_player_profile(username: str) -> dict:
    """Get public player profile."""
    data = load_player_json(username) or load_user_data(username)
    if not data:
        return None
    return {
        "username": data["username"],
        "level": data.get("level", 1),
        "combat_power": calculate_combat_power(data),
        "weapon": data.get("weapon", "None"),
        "armor": data.get("armor", "None"),
        "abyss_floor": data.get("abyss_floor", 1),
        "gold": data.get("gold", 0)
    }

def pvp_challenge(challenger: str, target: str) -> dict:
    """PVP with simulated battle rounds."""
    import random
    c_data = load_player_json(challenger) or load_user_data(challenger)
    t_data = load_player_json(target) or load_user_data(target)
    if not c_data or not t_data:
        return {"ok": False, "error": "玩家不存在"}
    c_power = calculate_combat_power(c_data)
    t_power = calculate_combat_power(t_data)
    # Simulate battle rounds
    c_hp = c_data.get("max_hp", 100)
    t_hp = t_data.get("max_hp", 100)
    log = []
    rounds = 0
    while c_hp > 0 and t_hp > 0 and rounds < 20:
        rounds += 1
        # Challenger attacks
        c_dmg = int(c_power * 0.1 * random.uniform(0.8, 1.2))
        t_hp -= c_dmg
        log.append(f"R{rounds}: {challenger} hits for {c_dmg}")
        if t_hp <= 0:
            break
        # Target attacks
        t_dmg = int(t_power * 0.1 * random.uniform(0.8, 1.2))
        c_hp -= t_dmg
        log.append(f"R{rounds}: {target} hits for {t_dmg}")
    winner = challenger if t_hp <= 0 else target
    # Reward
    reward = 1000
    if winner == challenger:
        c_data["gold"] = c_data.get("gold", 0) + reward
        save_player_json(c_data)
    return {
        "ok": True,
        "winner": winner,
        "challenger_power": c_power,
        "target_power": t_power,
        "reward": reward if winner == challenger else 0,
        "log": log[-6:],
        "rounds": rounds
    }


def get_daily_quests(player: dict) -> list:
    """Get daily quests with progress."""
    from datetime import date
    today = str(date.today())
    if player.get("quest_date") != today:
        player["quest_date"] = today
        player["quest_progress"] = {"fights": 0, "forges": 0, "abyss": 0}
    progress = player.get("quest_progress", {"fights": 0, "forges": 0, "abyss": 0})
    quests = [
        {"id": "fight5", "name": "戰鬥 5 次" if player.get("lang") != "en" else "Fight 5 times", "progress": progress.get("fights", 0), "goal": 5, "reward": 500},
        {"id": "forge3", "name": "抽卡 3 次" if player.get("lang") != "en" else "Forge 3 times", "progress": progress.get("forges", 0), "goal": 3, "reward": 1000},
        {"id": "abyss1", "name": "深淵 1 次" if player.get("lang") != "en" else "Abyss 1 time", "progress": progress.get("abyss", 0), "goal": 1, "reward": 2},
    ]
    return quests

def update_quest_progress(player: dict, quest_type: str, amount: int = 1):
    """Update quest progress."""
    from datetime import date
    today = str(date.today())
    if player.get("quest_date") != today:
        player["quest_date"] = today
        player["quest_progress"] = {"fights": 0, "forges": 0, "abyss": 0}
    player.setdefault("quest_progress", {"fights": 0, "forges": 0, "abyss": 0})
    player["quest_progress"][quest_type] = player["quest_progress"].get(quest_type, 0) + amount

def claim_quest_reward(player: dict, quest_id: str) -> dict:
    """Claim quest reward if completed."""
    quests = get_daily_quests(player)
    for q in quests:
        if q["id"] == quest_id and q["progress"] >= q["goal"]:
            claimed = player.setdefault("claimed_quests", [])
            if quest_id not in claimed:
                claimed.append(quest_id)
                if quest_id == "abyss1":
                    player["abyss_tokens"] = player.get("abyss_tokens", 0) + q["reward"]
                else:
                    player["gold"] += q["reward"]
                return {"ok": True, "reward": q["reward"]}
            return {"ok": False, "error": "已領取"}
    return {"ok": False, "error": "未完成"}


def get_equipped_achievement(player: dict) -> dict:
    """Get equipped achievement bonus."""
    ach_id = player.get("equipped_achievement")
    bonuses = {
        "lv10": {"atk": 5, "name": "初出茅廬"},
        "lv50": {"atk": 15, "name": "高手"},
        "w10": {"crit": 5, "name": "收藏家"},
        "p5": {"def": 10, "name": "超能力者"},
        "a10": {"hp": 50, "name": "深淵探索者"},
        "g100k": {"gold_bonus": 10, "name": "富豪"},
    }
    return bonuses.get(ach_id, {})

def equip_achievement(player: dict, ach_id: str) -> dict:
    """Equip an achievement."""
    from game_core import get_achievements
    unlocked = [a["id"] for a in get_achievements(player)]
    if ach_id in unlocked:
        player["equipped_achievement"] = ach_id
        return {"ok": True}
    return {"ok": False, "error": "未解鎖"}
