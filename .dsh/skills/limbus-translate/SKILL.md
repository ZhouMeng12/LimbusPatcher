---
name: limbus-translate
description: 《边狱巴士》(Limbus Company) 零协汉化补丁仓库的翻译/润色/校对工作流：查术语、批量机翻、方括号效果 id 保护、成批文本外包给外部 AI（豆包/ChatGPT/本地小模型）、体检与回归。仓库 D:\Desktop\lbc。
whenToUse: 任务涉及 Limbus 游戏文本翻译、汉化润色、术语统一、新章节补译、补译文件(supplement)更新、译文体检，或要把大批文本交给别的 AI 处理时。
---

# 边狱巴士汉化翻译工作流

## 0. 最重要的一条：大活别在会话里读改

需要**成批**改文本（几十条以上）时，不要在会话里逐条读改——极费 token。按这个顺序选：

1. **外包给外部 AI（首选）**：`python scripts/text_tasks.py export --rel <文件> --per 60`
   → 产出 `data/text_tasks/paste/*.txt`（自带提示词、术语表、硬性规则），整篇粘给豆包/ChatGPT；
   要求它只回 JSON，存成 `data/text_tasks/ans/<同名>.json`，再 `python scripts/text_tasks.py import`
   （import 会校验方括号/韩文/占位符，坏答案直接拒绝）。`status` 看进度，`--dry-run` 先预览。
2. **本地小模型（零成本、整批粗翻）**：`data/translate/engine.json`
   ```json
   {"local": {"base_url": "http://127.0.0.1:11434/v1", "model": "qwen2.5:7b", "api_key": ""}}
   ```
   然后 `set LB_MT_ENGINE=local` 再跑 `scripts/mt_translate.py` / `mt_files.py` / `fill_missing_ch10.py`；
   Ollama / LM Studio / llama.cpp 都吃这个 OpenAI 兼容接口。小模型只适合粗翻，术语与风格仍要复核。
3. **只在会话里做**：少量（<30 条）、需要判断力、或上面两条都不合适的收尾。

## 1. 事实源

| 用途 | 路径 |
|---|---|
| 零协汉化包（风格/术语唯一基准，**只读**） | `<游戏>\LimbusCompany_Data\Lang\LLC_zh-CN` |
| 英文基线（结构基准） | `<游戏>\LimbusCompany_Data\Assets\Resources_moved\Localize\en\EN_<同名>.json`（子目录如 `RPGSystem/EN_xxx.json`） |
| 我们的译文（数据文件） | `data/translate/files/<相对路径>` |
| 我们的译文（剧情） | `data/translate/zh/<名>.json`（`{"lines": {...}}`） |
| 合并产物 → 补译文件来源 | `data/translate/out/zh/` |
| 补译文件（随补丁进游戏） | `data/supplement/`（开发）、`dist/data/supplement/`（打包版） |
| 术语表 | `data/translate/glossary.json` + `审定新词.json`（后者优先） |

游戏路径：`D:/SteamLibrary/steamapps/common/Limbus Company/LimbusCompany_Data`。
python 一律用 `D:\Desktop\lbc\.venv\Scripts\python.exe`，命令前加 `PYTHONIOENCODING=utf-8`，加 `timeout`。

## 2. 铁律（违反就会在游戏里出问题）

1. **说明类字段里的方括号是效果 id，绝不能翻**：`desc / summary / statText / effect / lowMoraleDescription / panicDescription`
   里的 `[CombatStart]`、`[Bleed]`、`[Laceration]`、`[ChargeRouge]` 必须与英文基线**一字不差**——
   翻了游戏里显示 `UNKNOWN` 或口口。名字类字段（`name/title/displayName`）里的方括号才是描述，按中文译，
   且方括号前不留空格（零协：`BongBong [Orange]` → `噗扭扭[橙子味]`）。
2. **标签与占位符原样**：`<color=#xxxxxx>`、`<i>`、`{0}`；行数/换行不能变。
3. **绝不写游戏目录**（`Lang/LLC_zh-CN`、`Localize/**`）。补译文件只放 `data/supplement`、`dist/data/supplement`。
4. **零协同名文件优先**，补译文件只补零协缺的（部署器已实现记录级合并）。
5. 译文只用简体、中文标点（`“”`、`……`、`，`）；不夹韩文；`[미사용]`（韩文"未使用"）写 `[未使用]`。
6. 空字段＝游戏里显示内部编号/空白（曾导致 RPG 任务面板出现 `0901` 这类数字）——**任何英文非空而译文为空的字段都必须补**。

## 3. 术语（照零协，权威顺序：零协包实际用词 > 术语表 > 常识）

Uptie=同步 · Threadspinning=异想解析 · Identity=人格 · Clash=**拼点**（零协用 2522 次，别用"交锋"）·
SP=理智值 · HP=体力 · Sin=罪孽（暴怒/色欲/怠惰/暴食/忧郁/傲慢/嫉妒）· Stagger=混乱 ·
Max Stack=最大值 · Sinner=罪人 · E.G.O 保留 · Extraction=提取 · Egoshard=自我碎片 · Dispenser=自动贩卖机 ·
`[Season N]`→`[第N赛季]`。

人名：默尔索、克罗默、耐莉、亚细亚、仇甫、赫尔曼、埃菲、德米安、维吉里乌斯、梅菲斯托费勒斯、良秀、罗佳、
以实玛利、辛克莱、浮士德、格里高尔、堂吉诃德、李箱、鸿璐、奥提斯、林、参孙、樱桃(Aeng-du)、亚哈、阿赖耶。
罗佳叫以实玛利「以实」、默尔索「默尔」、浮士德「浮」、辛克莱「辛」、格里高尔「格雷格」。
良秀爱缩写，缩略语译成中文缩写（`C.H.`→`钟.头.`、`G.B.`→`金.皮.`）。
第十章（默尔索《局外人》篇）：西西弗百货、深红之神、凝视之下、妈妈(maman)、局外人、审判长/检察官/陪审团/辩护律师。

**动手前先在零协包里查同词**：
```bash
grep -rl "候选译名" "D:/SteamLibrary/.../Lang/LLC_zh-CN" | head
```

## 4. 标准流程（新文件/新章节）

```bash
PY=.venv/Scripts/python.exe
# 1) 结构 + 术语盘点
$PY scripts/survey_ch10.py           # 勘察：哪些文件零协没有
$PY scripts/build_glossary.py        # 术语表（id 配对 + 说话人 + 行对）
# 2) 机翻（术语/方括号/标签自动占位保护）
$PY scripts/mt_files.py --slice 0:20 # 数据文件，分批防止超时
$PY scripts/mt_translate.py --missing # 剧情
$PY scripts/fill_missing_ch10.py      # 空字段补齐（必跑）
# 3) 修方括号 id / 字体安全字符 / 韩文残留
$PY scripts/repair_ch10.py            # 全量；--files 指定
# 4) 体检
$PY scripts/verify_ch10.py --quiet    # brackets/hangul/risky/placeholders/untranslated
# 5) 合并 + 装补译文件 + 打包
$PY scripts/finalize_ch10_all.py                       # 或逐条：translate_pack.py merge <名>
$PY scripts/install_supplement.py
$PY scripts/install_supplement.py --data-dir dist/data  # 打包版（exe 同目录）
# 6) 回归测试（会拦住空字段/方括号被翻/韩文/补译文件不同步）
$PY -m pytest tests/test_ch10_quality.py -q
```

改完必须提醒用户：**重启软件 → 点「应用到游戏」**，否则游戏里旧译文不会更新。

### 4.5 RPG 关卡（10-4 这类）的剧情整理

RPG 关的剧情在 `RPGSystem/rpg-loc-dialogue-*` 里，和 `StoryData` 过场交替，且**本地文件没有触发器数据**——
顺序只能靠编排表人工定。流程：

```bash
# 1) 改编排表（唯一事实源；分支按玩家游玩顺序，含 evidence/confidence）
#    limbus_patcher/data/story_rpg_plan.json
# 2) 重建剧本数据（会连数据/wiki_story 与 dist/data/cache 两份运行时副本一起刷新）
$PY scripts/build_story_rpg.py --stage 10-04 [--dry-run]
# 3) 体检：来源必须是零协 / 覆盖 100% / 顺序单调 / 结构完整
$PY scripts/verify_story_rpg.py --stage 10-04
# 4) 中英对照（交付物）
$PY scripts/export_story_rpg.py --stage 10-04
# 5) 回归
$PY -m pytest tests/test_story_rpg.py -q
```

要点：文本**必须**取自零协包（早期机翻稿一致率只有 ~5%，别再用）；RPG 行的叶子是
`texts[i].text`（无 KeyID），定位靠 `record + text_index`，选项/地点走 `text`；剧本模式里
分支按**楼层**挂在关卡下面（`10-04 → └ 02 1F·西西弗百货`），段内用 `label` 标小节。

## 5. 外包任务包（写给外部 AI 的需求模板）

`text_tasks.py export` 已内建这份提示词；手工写时也用同样结构：

```
任务：润色/补译《边狱巴士》第十章汉化文本（<文件> 第 N 片，共 M 条）
硬性规则：只改中文译文；不改结构/键名/条目数；
  desc/summary/statText/effect/lowMoraleDescription/panicDescription 里的 [X] 是内部效果 id，必须与英文一字不差；
  <color=…>/<i>/{0} 与换行原样；专名照术语表，表里没有的保留原文；简体+中文标点。
术语表：Uptie=同步、Threadspinning=异想解析、Identity=人格、Clash=拼点、SP=理智值…
只回 JSON：{"<文件>|<字段路径>": "新中文"}
每条格式：### 路径：dataList/3/desc  /  EN: …  /  ZH: …
```

## 6. 补译文件（supplement）机制

- 零协包里没有的文件（新章节/RPG 模式）放 `data/supplement/<零协包内相对路径>`，由部署器写进游戏副本；
- 同名文件**零协优先**，只有零协缺的 id 才用我们的记录（记录级合并）；
- 补译文件可被软件搜索/编辑（索引里 `source='supplement'`，类别「RPG 剧情」「补译文本」）。

## 6.5 零协更新（汉化包出新版本时）

```bash
PY=.venv/Scripts/python.exe
$PY scripts/llc_update.py snapshot   # 更新【前】记录基线（已做过：data/llc_baseline.json）
# —— 用户更新零协包 ——
$PY scripts/llc_update.py diff       # 新增/改动/删除，第十章相关会打 ★
$PY scripts/llc_update.py sync       # 撤销被零协覆盖的补译 + 重装两处 + 体检 + 术语对照
```
规则：**零协官方译文永远优先**。部署器对同名文件做记录级合并（只追加零协缺的 id），
但补译文件本身要按覆盖度处理：零协**完全覆盖**我们的 id → `remove` 掉；
零协仍缺记录（如 `StageChapterText.json` 第十章那几行）→ 保留，继续合并。
`sync` 会依次：撤销被覆盖的补译 → 重装两处 → 体检 → **学零协术语**（`learn_llc_terms.py --chapter 10`
→ `data/translate/零协术语-第10章.json` + `术语冲突.md`）→ 逐字段对照（`out/零协第十章-术语对照.md`）。
冲突处理：`learn_llc_terms.py --apply --files`（零协译名写进 `审定新词.json`，并把译文里旧译名替换掉）。
更新后提醒用户：**重启软件 → 点「应用到游戏」**（索引按文件的 size/mtime 自动重建，无需改代码）。

## 7. 常见坑（都踩过）

| 症状 | 原因 | 处理 |
|---|---|---|
| 游戏里技能显示 `UNKNOWN` / 口口 | 方括号效果 id 被翻译 | `repair_ch10.py`（说明字段按英文还原） |
| RPG 任务显示 `0901`、一串数字 | 标题/描述是空字符串 | `fill_missing_ch10.py`，再重装补译文件 |
| 关键字/状态面板空白 | Bufs/BattleKeywords 的 name/desc 为空或仍是英文 | 补译 + 重装 |
| `@@12@@`、`但丁@` 残留 | 占位符还原被机翻破坏 | `verify_ch10.py` 抓 placeholders；手工修 |
| 用户看到旧译文 | 没重新 `install_supplement` 或没点「应用到游戏」 | 重装 + 重应用 |
| 术语前后不一 | 多文件并行翻译 | 用零协包 grep 定标准，再全局统一 |

## 8. 汇报习惯

用户很在意 token：**先给结论和数字**（改了什么、多少处、验证结果、要他做什么），
不要贴大段原文/日志；长清单给文件名 + 计数，需要时再展开。
