# app.py - Flask web application for the Text RPG
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from functools import wraps
import os
from pathlib import Path

from data_loader import load_game_catalog, load_powers_db
from save_manager import (
    load_user_data, player_dict_from_row, save_player_data,
    create_new_account, user_exists, list_all_saves,
    load_player_json, save_player_json
)
from game_core import (
    get_display_name, get_effect_name, get_player_status, simulate_auto_fight, calculate_combat_power,
    calculate_stats, get_effective_weapon, get_effective_armor, format_gear_name,
    forge_weapons, forge_armors, upgrade_current_weapon, upgrade_current_armor,
    buy_potions, pull_powers, equip_power, simulate_boss_rush, abyss_shop_exchange
)

app = Flask(__name__)

@app.context_processor
def inject_lang():
    player = get_current_player()
    lang = player.get("lang", "zh") if player else "zh"
    return {"ui_lang": lang, "get_display_name": get_display_name, "get_effect_name": get_effect_name}


app.secret_key = os.environ.get("SECRET_KEY", "rpg-dev-secret-change-me-in-production")

# In-memory session cache of full player objects (reloaded from disk when needed)
_player_cache = {}


def get_current_player():
    """Load player from session username, preferring cache then disk.
    Always recalculate max_hp from armor + level so bars stay correct.
    """
    username = session.get("username")
    if not username:
        return None
    if username in _player_cache:
        player = _player_cache[username]
        # Keep max_hp in sync with equipped armor / level
        old_max = player.get("max_hp", 0)
        calculate_stats(player)
        if player["max_hp"] != old_max:
            if player["hp"] > player["max_hp"]:
                player["hp"] = player["max_hp"]
            elif player["hp"] == old_max:
                player["hp"] = player["max_hp"]
        return player
    row = load_user_data(username)
    if not row:
        return None
    player = player_dict_from_row(row)
    if player:
        # Enrich powers with full data if only names were stored
        if player.get("powers") and isinstance(player["powers"][0], dict) and "score" not in player["powers"][0]:
            all_powers = {p["name"]: p for p in load_powers_db()}
            enriched = []
            for p in player["powers"]:
                name = p["name"] if isinstance(p, dict) else p
                if name in all_powers:
                    enriched.append(all_powers[name])
                else:
                    enriched.append({"name": name, "score": 1, "grade": "e", "effect": "none"})
            player["powers"] = enriched
        # Recalculate max_hp including armor bonus (saved max_hp may be stale)
        saved_hp = player.get("hp", 0)
        calculate_stats(player)
        # Preserve current HP ratio-ish: clamp to new max
        if saved_hp > player["max_hp"]:
            player["hp"] = player["max_hp"]
        else:
            player["hp"] = saved_hp
        _player_cache[username] = player
    return player


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ========== Pages ==========

@app.route("/")
def index():
    if "username" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        # Validation
        if not username or len(username) < 2 or len(username) > 20:
            return render_template("register.html", error="用戶名需 2-20 字元")
        if not password or len(password) < 4:
            return render_template("register.html", error="密碼至少 4 字元")
        if " " in username or " " in password:
            return render_template("register.html", error="用戶名和密碼不能有空格")
        if not username or not password:
            flash("请输入用户名和密码", "error")
            return render_template("login.html")

        row = load_user_data(username)
        if row and len(row) >= 2 and row[1] == password:
            session["username"] = username
            # clear any stale cache
            _player_cache.pop(username, None)
            flash(f"欢迎回来，{username}！", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("用户名不存在或密码错误", "error")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register with input validation."""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        # Validation
        if not username or len(username) < 2 or len(username) > 20:
            return render_template("register.html", error="用戶名需 2-20 字元")
        if not password or len(password) < 4:
            return render_template("register.html", error="密碼至少 4 字元")
        if " " in username or " " in password:
            return render_template("register.html", error="用戶名和密碼不能有空格")
        confirm = request.form.get("confirm", "").strip()

        if not username or not password:
            flash("请填写完整资料", "error")
            return render_template("register.html")
        if " " in username or " " in password:
            flash("用户名和密码不能包含空格", "error")
            return render_template("register.html")
        if password != confirm:
            flash("两次密码不一致", "error")
            return render_template("register.html")
        if user_exists(username):
            flash("用户名已被占用", "error")
            return render_template("register.html")
        if len(username) < 2 or len(username) > 20:
            flash("用户名长度需在 2~20 之间", "error")
            return render_template("register.html")

        player = create_new_account(username, password)
        _player_cache[username] = player
        session["username"] = username
        flash("账号创建成功！", "success")
        return redirect(url_for("dashboard"))
    return render_template("register.html")


@app.route("/logout")
def logout():
    username = session.pop("username", None)
    if username:
        _player_cache.pop(username, None)
    flash("已安全登出", "info")
    return redirect(url_for("login"))


@app.route("/dashboard")
@login_required
def dashboard():
    player = get_current_player()
    if not player:
        session.clear()
        return redirect(url_for("login"))
    status = get_player_status(player)
    return render_template("dashboard.html", status=status)



@app.route("/status")
@login_required
def status_page():
    player = get_current_player()
    if not player:
        return redirect(url_for("login"))
    status = get_player_status(player)
    return render_template("status.html", status=status)

@app.route("/battle")
@login_required
def battle_page():
    player = get_current_player()
    if not player:
        return redirect(url_for("login"))
    status = get_player_status(player)
    return render_template("battle.html", status=status)


@app.route("/inventory")
@login_required
def inventory_page():
    player = get_current_player()
    if not player:
        return redirect(url_for("login"))
    status = get_player_status(player)
    catalog = load_game_catalog()
    weapons = catalog["weapons"]
    armors = catalog["armors"]

    owned_w = []
    for w in player.get("unlocked_weapons", []):
        if w in weapons:
            eff = get_effective_weapon(w, player, weapons)
            from game_core import get_gear_tier_score, get_weapon_type_stats, get_armor_slot
            tier = get_gear_tier_score(weapons[w]["atk"], "weapon")
            lang = player.get("lang", "zh")
            desc = weapons[w].get("desc_zh") if lang == "zh" else weapons[w].get("desc_en")
            desc = desc or weapons[w].get("desc_en") or weapons[w].get("desc_zh") or ""
            owned_w.append({"name": w, "display": format_gear_name(w, player, "weapon"), "level": player.get("weapon_levels", {}).get(w, 0), "atk": eff["atk"], "crit_ch": eff.get("crit_ch",5), "crit_dmg": eff.get("crit_dmg",1.5), "range": get_weapon_type_stats(w)["range"], "speed": get_weapon_type_stats(w)["speed"], "tier": tier, "desc": desc, "element": weapons[w].get("element","none"), "equipped": w == player["weapon"]})
    owned_w.sort(key=lambda x: x["atk"], reverse=True)

    owned_a = []
    for a in player.get("unlocked_armors", []):
        if a in armors:
            eff = get_effective_armor(a, player, armors)
            tier = get_gear_tier_score(armors[a], "armor")
            lang = player.get("lang", "zh")
            desc = armors[a].get("desc_zh") if lang == "zh" else armors[a].get("desc_en")
            desc = desc or armors[a].get("desc_en") or armors[a].get("desc_zh") or ""
            owned_a.append({
                "name": a, "display": format_gear_name(a, player, "armor"), "level": player.get("armor_levels", {}).get(a, 0),
                "defense": eff["defense"], "hp_bonus": eff["hp_bonus"], "tier": tier,
                "desc": desc, "element": armors[a].get("element","none"), "slot": get_armor_slot(a),
                "equipped": a == (player.get("armor_slots") or {}).get(get_armor_slot(a))
            })
    owned_a.sort(key=lambda x: x["defense"] + x["hp_bonus"], reverse=True)

    return render_template("inventory.html", status=status, weapons=owned_w, armors=owned_a)


@app.route("/leaderboard")
@login_required
def leaderboard_page():
    category = request.args.get("cat", "power")
    entries = []
    for uname in list_all_saves():
        row = load_user_data(uname)
        if not row:
            continue
        p = player_dict_from_row(row)
        if not p:
            continue
        cp = calculate_combat_power(p)
        entries.append({
            "username": uname,
            "level": p["level"],
            "combat_power": cp,
            "gold": p.get("gold", 0),
            "abyss_floor": p.get("abyss_floor", 1),
            "abyss_tokens": p.get("abyss_tokens", 0),
        })
    key_map = {
        "power": "combat_power",
        "gold": "gold",
        "floor": "abyss_floor",
        "level": "level",
        "tokens": "abyss_tokens",
    }
    sort_key = key_map.get(category, "combat_power")
    entries.sort(key=lambda x: x.get(sort_key, 0), reverse=True)
    return render_template("leaderboard.html", entries=entries[:50], category=category)


# ========== API Endpoints ==========

@app.route("/api/status")
@login_required
def api_status():
    player = get_current_player()
    if not player:
        return jsonify({"ok": False, "error": "not logged in"}), 401
    return jsonify({"ok": True, "status": get_player_status(player)})


@app.route("/api/fight", methods=["POST"])
@login_required
def api_fight():
    player = get_current_player()
    if not player:
        return jsonify({"ok": False, "error": "not logged in"}), 401
    # reload lang from save to ensure latest
    row = load_user_data(player["username"])
    if row and len(row) > 16:
        player["lang"] = row[16]

    data = request.get_json(silent=True) or {}
    max_waves = int(data.get("max_waves", 10))
    max_waves = max(1, min(max_waves, 30))  # safety limit

    from game_core import update_quest_progress
    update_quest_progress(player, "fights", 1)
    result = simulate_auto_fight(player, max_waves=max_waves)
    # update cache
    _player_cache[player["username"]] = player
    return jsonify(result)


@app.route("/api/equip", methods=["POST"])
@login_required
def api_equip():
    player = get_current_player()
    if not player:
        return jsonify({"ok": False, "error": "not logged in"}), 401

    data = request.get_json(silent=True) or {}
    item_type = data.get("type")  # "weapon" or "armor"
    name = data.get("name")

    if item_type == "weapon" and name in player.get("unlocked_weapons", []):
        # Toggle: if already equipped, unequip
        if player.get("weapon") == name:
            player["weapon"] = None
        else:
            player["weapon"] = name
        from game_core import calculate_stats
        calculate_stats(player)
        save_player_data(player)
        _player_cache[player["username"]] = player
        return jsonify({"ok": True, "status": get_player_status(player)})
    elif item_type == "armor" and name in player.get("unlocked_armors", []):
        from game_core import get_armor_slot, set_armor_slot, get_equipped_armors
        slot = get_armor_slot(name)
        slots = get_equipped_armors(player)
        # Toggle: if already equipped, unequip
        if slots.get(slot) == name:
            slots[slot] = None
            player["armor_slots"] = slots
            if slot == "chest":
                player["armor"] = None
        else:
            set_armor_slot(player, slot, name)
            if slot == "chest":
                player["armor"] = name
        # recalculate max_hp and heal a bit
        from game_core import calculate_stats
        calculate_stats(player)
        player["hp"] = min(player["hp"], player["max_hp"])
        save_player_data(player)
        _player_cache[player["username"]] = player
        return jsonify({"ok": True, "status": get_player_status(player)})
    return jsonify({"ok": False, "error": "invalid item"}), 400


@app.route("/api/heal", methods=["POST"])
@login_required
def api_heal():
    """Use a minor potion manually."""
    player = get_current_player()
    if not player:
        return jsonify({"ok": False, "error": "not logged in"}), 401
    potions = player.setdefault("potions", {"minor_potion": 0, "strength_potion": 0})
    if potions.get("minor_potion", 0) <= 0:
        return jsonify({"ok": False, "error": "没有微型生命药剂"}), 400
    potions["minor_potion"] -= 1
    heal = int(player["max_hp"] * 0.5)
    player["hp"] = min(player["max_hp"], player["hp"] + heal)
    save_player_data(player)
    _player_cache[player["username"]] = player
    return jsonify({"ok": True, "healed": heal, "status": get_player_status(player)})


# ========== Blacksmith / Power / Abyss Pages ==========

@app.route("/blacksmith")
@login_required
def blacksmith_page():
    player = get_current_player()
    if not player:
        return redirect(url_for("login"))
    status = get_player_status(player)
    weapons = load_game_catalog()["weapons"]
    armors = load_game_catalog()["armors"]
    w_eff = get_effective_weapon(player["weapon"], player, weapons)
    a_eff = get_effective_armor(player["armor"], player, armors)
    return render_template("blacksmith.html", status=status, w_eff=w_eff, a_eff=a_eff)


@app.route("/power-shrine")
@login_required
def power_shrine_page():
    player = get_current_player()
    if not player:
        return redirect(url_for("login"))
    status = get_player_status(player)
    powers = player.get("powers", [])
    # enrich if needed
    all_p = {p["name"]: p for p in load_powers_db()}
    enriched = []
    for p in powers:
        name = p["name"] if isinstance(p, dict) else p
        if name in all_p:
            enriched.append(all_p[name])
        elif isinstance(p, dict):
            enriched.append(p)
    enriched.sort(key=lambda x: x.get("score", 0), reverse=True)
    return render_template("power_shrine.html", status=status, powers=enriched)


@app.route("/abyss")
@login_required
def abyss_page():
    player = get_current_player()
    if not player:
        return redirect(url_for("login"))
    status = get_player_status(player)
    return render_template("abyss.html", status=status)


# ========== Blacksmith / Power / Abyss APIs ==========

@app.route("/api/forge", methods=["POST"])
@login_required
def api_forge():
    player = get_current_player()
    if not player:
        return jsonify({"ok": False, "error": "not logged in"}), 401
    data = request.get_json(silent=True) or {}
    kind = data.get("kind") or data.get("type")  # weapon | armor
    count = int(data.get("count", 1))
    count = 1 if count not in (1, 10) else count
    costs = {"weapon": {1: 5000, 10: 45000}, "armor": {1: 5000, 10: 45000}}
    if kind not in costs:
        return jsonify({"ok": False, "error": "invalid kind"}), 400
    cost = costs[kind][count]
    if player["gold"] < cost:
        return jsonify({"ok": False, "error": f"金币不足（需要 {cost:,}g）"}), 400
    player["gold"] -= cost
    from game_core import update_quest_progress
    update_quest_progress(player, "forges", 1)
    if kind == "weapon":
        result = forge_weapons(player, count)
    else:
        result = forge_armors(player, count)
    _player_cache[player["username"]] = player
    result["status"] = get_player_status(player)
    return jsonify(result)


@app.route("/api/upgrade", methods=["POST"])
@login_required
def api_upgrade():
    player = get_current_player()
    if not player:
        return jsonify({"ok": False, "error": "not logged in"}), 401
    data = request.get_json(silent=True) or {}
    kind = data.get("kind") or data.get("type")
    if kind == "weapon":
        result = upgrade_current_weapon(player)
    elif kind == "armor":
        result = upgrade_current_armor(player, data.get("slot"))
    else:
        return jsonify({"ok": False, "error": "invalid kind"}), 400
    if result.get("ok"):
        _player_cache[player["username"]] = player
        result["status"] = get_player_status(player)
    return jsonify(result)


@app.route("/api/buy-potions", methods=["POST"])
@login_required
def api_buy_potions():
    player = get_current_player()
    if not player:
        return jsonify({"ok": False, "error": "not logged in"}), 401
    result = buy_potions(player, 1)
    if result.get("ok"):
        _player_cache[player["username"]] = player
        result["status"] = get_player_status(player)
    return jsonify(result)


@app.route("/api/pull-power", methods=["POST"])
@login_required
def api_pull_power():
    player = get_current_player()
    if not player:
        return jsonify({"ok": False, "error": "not logged in"}), 401
    data = request.get_json(silent=True) or {}
    count = int(data.get("count", 1))
    count = 10 if count == 10 else 1
    cost = 180000 if count == 10 else 20000
    if player["gold"] < cost:
        return jsonify({"ok": False, "error": f"金币不足（需要 {cost:,}g）"}), 400
    player["gold"] -= cost
    result = pull_powers(player, count)
    _player_cache[player["username"]] = player
    result["status"] = get_player_status(player)
    return jsonify(result)


@app.route("/api/equip-power", methods=["POST"])
@login_required
def api_equip_power():
    player = get_current_player()
    if not player:
        return jsonify({"ok": False, "error": "not logged in"}), 401
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    result = equip_power(player, name)
    if result.get("ok"):
        _player_cache[player["username"]] = player
    return jsonify(result)


@app.route("/api/abyss-rush", methods=["POST"])
@login_required
def api_abyss_rush():
    player = get_current_player()
    if not player:
        return jsonify({"ok": False, "error": "not logged in"}), 401
    data = request.get_json(silent=True) or {}
    max_floors = int(data.get("floors") or data.get("max_floors") or 5)
    max_floors = max(1, min(max_floors, 20))
    from game_core import update_quest_progress
    update_quest_progress(player, "abyss", 1)
    result = simulate_boss_rush(player, max_floors)
    _player_cache[player["username"]] = player
    return jsonify(result)


@app.route("/api/abyss-shop", methods=["POST"])
@login_required
def api_abyss_shop():
    player = get_current_player()
    if not player:
        return jsonify({"ok": False, "error": "not logged in"}), 401
    data = request.get_json(silent=True) or {}
    item = data.get("item")
    result = abyss_shop_exchange(player, item)
    if result.get("ok"):
        _player_cache[player["username"]] = player
    return jsonify(result)




# ========== Run ==========


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings_page():
    player = get_current_player()
    if not player:
        return redirect(url_for("login"))
    if request.method == "POST":
        action = request.form.get("action")
        if action == "lang":
            new_lang = request.form.get("lang", "zh")
            if new_lang in ("zh", "en"):
                player["lang"] = new_lang
                save_player_data(player)
                _player_cache[player["username"]] = player
                flash("语言已切换 / Language updated", "success")
        elif action == "password":
            old_p = request.form.get("old_password", "")
            new_p = request.form.get("new_password", "")
            conf = request.form.get("confirm_password", "")
            if old_p != player.get("password"):
                flash("原密码错误 / Wrong current password", "error")
            elif not new_p or len(new_p) < 3:
                flash("新密码至少 3 位", "error")
            elif new_p != conf:
                flash("两次新密码不一致 / Passwords do not match", "error")
            else:
                player["password"] = new_p
                save_player_data(player)
                _player_cache[player["username"]] = player
                flash("密码修改成功 / Password changed", "success")
        return redirect(url_for("settings_page"))
    status = get_player_status(player)
    return render_template("settings.html", status=status, lang=player.get("lang", "zh"))


@app.route("/api/equip-best", methods=["POST"])
@login_required
def api_equip_best():
    player = get_current_player()
    if not player:
        return jsonify({"ok": False, "error": "未登录"})
    catalog = load_game_catalog()
    weapons, armors = catalog["weapons"], catalog["armors"]
    owned_w = [w for w in player.get("unlocked_weapons", []) if w in weapons]
    if owned_w:
        player["weapon"] = max(owned_w, key=lambda x: get_effective_weapon(x, player, weapons)["atk"])
    owned_a = [a for a in player.get("unlocked_armors", []) if a in armors]
    if owned_a:
        from game_core import get_armor_slot, set_armor_slot
        for slot in ["helmet", "chest", "gloves", "boots", "cloak"]:
            slot_items = [a for a in owned_a if get_armor_slot(a) == slot]
            if slot_items:
                best = max(slot_items, key=lambda x: get_effective_armor(x, player, armors)["defense"] + get_effective_armor(x, player, armors)["hp_bonus"])
                set_armor_slot(player, slot, best)
                if slot == "chest":
                    player["armor"] = best
    if player.get("powers"):
        best = max(player["powers"], key=lambda x: x.get("score", 0) if isinstance(x, dict) else 0)
        if isinstance(best, dict):
            player["equipped_power"] = best["name"]
    calculate_stats(player)
    player["hp"] = player["max_hp"]
    save_player_data(player)
    _player_cache[player["username"]] = player
    return jsonify({"ok": True, "status": get_player_status(player)})



@app.route("/achievements")
@login_required
def achievements_page():
    player = get_current_player()
    if not player:
        return redirect(url_for("login"))
    from game_core import get_achievements
    unlocked = get_achievements(player)
    all_ach = [
        {"id": "lv10", "name": "初出茅廬" if player.get("lang") != "en" else "Beginner", "desc": "達到等級 10" if player.get("lang") != "en" else "Reach level 10"},
        {"id": "lv50", "name": "高手" if player.get("lang") != "en" else "Expert", "desc": "達到等級 50" if player.get("lang") != "en" else "Reach level 50"},
        {"id": "w10", "name": "收藏家" if player.get("lang") != "en" else "Collector", "desc": "擁有 10 把武器" if player.get("lang") != "en" else "Own 10 weapons"},
        {"id": "p5", "name": "超能力者" if player.get("lang") != "en" else "Power User", "desc": "擁有 5 個超能力" if player.get("lang") != "en" else "Own 5 powers"},
        {"id": "a10", "name": "深淵探索者" if player.get("lang") != "en" else "Abyss Explorer", "desc": "到達深淵第 10 層" if player.get("lang") != "en" else "Reach abyss floor 10"},
        {"id": "g100k", "name": "富豪" if player.get("lang") != "en" else "Rich", "desc": "擁有 100,000 金幣" if player.get("lang") != "en" else "Own 100,000 gold"},
    ]
    return render_template("achievements.html", 
        unlocked=unlocked, 
        all_achievements=all_ach,
        unlocked_ids=[a["id"] for a in unlocked],
        streak=player.get("login_streak", 0),
        ui_lang=player.get("lang", "zh"),
        status=get_player_status(player))


@app.route("/social")
@login_required
def social_page():
    player = get_current_player()
    if not player:
        return redirect(url_for("login"))
    from game_core import get_chat_messages, get_friends
    return render_template("social.html",
        messages=get_chat_messages(30),
        friends=get_friends(player["username"]),
        ui_lang=player.get("lang", "zh"),
        status=get_player_status(player))

@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    player = get_current_player()
    data = request.get_json() or {}
    from game_core import send_chat_message
    send_chat_message(player["username"], data.get("msg", ""))
    return jsonify({"ok": True})

@app.route("/api/friend", methods=["POST"])
@login_required
def api_friend():
    player = get_current_player()
    data = request.get_json() or {}
    from game_core import add_friend
    result = add_friend(player["username"], data.get("friend", ""))
    return jsonify(result)

@app.route("/api/gift", methods=["POST"])
@login_required
def api_gift():
    player = get_current_player()
    data = request.get_json() or {}
    from game_core import send_gift
    result = send_gift(player["username"], data.get("to", ""), int(data.get("gold", 0)))
    if result.get("ok"):
        _player_cache[player["username"]] = load_player_json(player["username"]) or load_user_data(player["username"])
    return jsonify(result)


@app.route("/player/<username>")
@login_required
def view_player(username):
    player = get_current_player()
    from game_core import get_player_profile
    profile = get_player_profile(username)
    if not profile:
        return "玩家不存在", 404
    return render_template("player_profile.html", profile=profile, ui_lang=player.get("lang", "zh"), status=get_player_status(player))

@app.route("/api/pvp", methods=["POST"])
@login_required
def api_pvp():
    player = get_current_player()
    data = request.get_json() or {}
    from game_core import pvp_challenge
    result = pvp_challenge(player["username"], data.get("target", ""))
    if result.get("ok") and result.get("winner") == player["username"]:
        _player_cache[player["username"]] = load_player_json(player["username"]) or load_user_data(player["username"])
    return jsonify(result)


@app.route("/quests")
@login_required
def quests_page():
    player = get_current_player()
    if not player:
        return redirect(url_for("login"))
    from game_core import get_daily_quests
    return render_template("quests.html",
        quests=get_daily_quests(player),
        claimed=player.get("claimed_quests", []),
        ui_lang=player.get("lang", "zh"),
        status=get_player_status(player))

@app.route("/api/claim-quest", methods=["POST"])
@login_required
def api_claim_quest():
    player = get_current_player()
    data = request.get_json() or {}
    from game_core import claim_quest_reward
    result = claim_quest_reward(player, data.get("quest_id", ""))
    if result.get("ok"):
        save_player_data(player)
        _player_cache[player["username"]] = player
    return jsonify(result)


@app.route("/api/equip-achievement", methods=["POST"])
@login_required
def api_equip_achievement():
    player = get_current_player()
    data = request.get_json() or {}
    from game_core import equip_achievement
    result = equip_achievement(player, data.get("ach_id", ""))
    if result.get("ok"):
        save_player_data(player)
        _player_cache[player["username"]] = player
    return jsonify(result)

@app.route("/encyclopedia")
@login_required
def encyclopedia_page():
    player = get_current_player()
    if not player:
        return redirect(url_for("login"))
    catalog = load_game_catalog()
    lang = player.get("lang", "zh")
    owned_w = set(player.get("unlocked_weapons") or [])
    owned_a = set(player.get("unlocked_armors") or [])
    owned_p = set()
    for pp in player.get("powers") or []:
        owned_p.add(pp["name"] if isinstance(pp, dict) else pp)
    weapons = []
    for name, w in sorted(catalog["weapons"].items(), key=lambda x: x[1]["atk"], reverse=True):
        desc = w.get("desc_zh") if lang == "zh" else w.get("desc_en")
        desc = desc or w.get("desc_en") or w.get("desc_zh") or ""
        from game_core import get_gear_tier_score, get_weapon_type_stats, get_armor_slot
        weapons.append({
            "name": name, "atk": w["atk"], "element": w.get("element","none"),
            "crit_ch": w.get("crit_ch", 5), "crit_dmg": w.get("crit_dmg", 1.5), "range": get_weapon_type_stats(name)["range"], "speed": get_weapon_type_stats(name)["speed"],
            "tier": get_gear_tier_score(w["atk"], "weapon"), "desc": desc,
            "owned": name in owned_w
        })
    armors = []
    for name, a in sorted(catalog["armors"].items(), key=lambda x: x[1]["defense"]+x[1]["hp_bonus"], reverse=True):
        desc = a.get("desc_zh") if lang == "zh" else a.get("desc_en")
        desc = desc or a.get("desc_en") or a.get("desc_zh") or ""
        from game_core import get_gear_tier_score, get_weapon_type_stats, get_armor_slot
        armors.append({
            "name": name, "defense": a["defense"], "hp_bonus": a["hp_bonus"],
            "element": a.get("element","none"), "crit_ch": a.get("crit_ch", 0), "slot": get_armor_slot(name),
            "tier": get_gear_tier_score(a, "armor", get_armor_slot(name)), "desc": desc,
            "owned": name in owned_a
        })
    powers = []
    for p in sorted(catalog["powers"].values(), key=lambda x: x["score"], reverse=True):
        desc = p.get("desc_zh") if lang == "zh" else p.get("desc_en")
        desc = desc or p.get("desc_en") or p.get("desc_zh") or ""
        powers.append({
            "name": p["name"], "grade": p["grade"].upper(), "score": p["score"],
            "effect": p["effect"], "desc": desc, "owned": p["name"] in owned_p
        })
    status = get_player_status(player)
    return render_template("encyclopedia.html", status=status, weapons=weapons, armors=armors, powers=powers)


if __name__ == "__main__":
    # Ensure folders exist
    Path("saves").mkdir(exist_ok=True)
    print("=" * 50)
    print("  Text RPG Web Server")
    print("  Open http://127.0.0.1:5000 in your browser")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=True)


@app.errorhandler(500)
def internal_error(e):
    return jsonify({"ok": False, "error": "伺服器錯誤，請稍後再試"}), 500

@app.errorhandler(404)
def not_found(e):
    return jsonify({"ok": False, "error": "頁面不存在"}), 404
