# Text RPG Web Version

把原本的文字 RPG 改成网页版，支援多人透过浏览器游玩，数据会写入服务器档案并同步。

## 快速启动

```bash
cd web_rpg
pip install -r requirements.txt   # 或 pip install flask portalocker
python app.py
```

浏览器打开：http://127.0.0.1:5000

## 已完成功能（MVP）

- 注册 / 登入 / 登出
- 仪表板（等级、金币、装备、战力）
- 智能挂机战斗（可选手数，结果自动存档同步）
- 背包装备切换（武器 / 防具）
- 战力排行榜（读取所有 save 档案）
- 手动使用生命药剂

## 专案结构

```
web_rpg/
├── app.py              # Flask 主程式 + API
├── game_core.py        # 纯逻辑（无 print/input）
├── data_loader.py      # 读取 armor/wepone/power/monster.txt
├── save_manager.py     # 存档读写 + 档案锁
├── data/               # 静态游戏资料
├── saves/              # 玩家存档（自动生成）
├── templates/          # HTML 页面
├── static/             # CSS / JS
└── requirements.txt
```

## API 设计摘要

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/status` | 取得当前玩家状态 |
| POST | `/api/fight` | 智能挂机战斗 `{"max_waves": 10}` |
| POST | `/api/equip` | 装备物品 `{"type":"weapon\|armor", "name":"..."}` |
| POST | `/api/heal` | 使用微型生命药剂 |

所有会改动玩家资料的 API 都会立刻写入 `saves/save_用户名.txt`。

## 下一步可扩展

1. 铁匠铺抽卡 / 强化
2. 超能力神殿
3. 无尽深渊 Boss Rush
4. 语言切换
5. 图鉴分页浏览

## 数据同步说明

- 每个玩家一个独立档案：`saves/save_用户名.txt`
- 使用 `portalocker` 做档案锁，避免多人同时写入冲突
- 战斗结束、换装备、使用药剂后都会立刻 `save_player_data()`
- 排行榜即时读取所有 save 档案计算战力
