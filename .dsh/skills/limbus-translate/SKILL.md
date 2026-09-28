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
第十章（默尔索《局外人》篇）：西西弗百货、**赤红之神**（零协实际用词；旧术语表写的「深红之神」作废）、
凝视之下、妈妈(maman)、局外人、审判长/检察官/陪审团/辩护律师。

第十章派系（**以零协为准，不保留法文**）：`Le Rouge`=红派、`Le Noir`=黑派、`Le Kaki`=褐派。
但品牌/专名要逐条查零协术语再定，别机械替换：`Boutique du Rouge`→红派精品店、`Le Noir Footwear Hall`→黑派制鞋馆；
`Maison du Noir`、`Le Trou Rouge`、`Le Président`、`Café de Flore`、`L'Inamovible` 保留原文或按零协译名，
批量替换时务必先把它们放进保护名单（脚本 `ch10p2_unify_terms.py` 的 `PROTECT`）。
注意 `[ChargeRouge]` 这类**效果 id 里的 Rouge 不能动**。

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
分支按**楼层**挂在关卡下面（`10-4A → └ 02 1F·西西弗百货`），段内用 `label` 标小节。
第10章有两条路线：`10-4A`（路线A）/ `10-4B`（路线B），同一座百货的第二轮，任务号沿用同一套。

**分段以灰机 wiki 的「放映室」顺序为准**（用户指定，wiki 剧情页没内容也能用楼层清单）：
<https://limbuscompany.huijiwiki.com/wiki/章节X_凝视之下>
路线A 9 段：1F → 2F① → 3F① → 4F → 3F② → B1F → B2F → 3F③ → 2F②
路线B 17 段：1F① → 2F① → 3F① → 2F② → 3F② → 4F① → 5F① → B1F① → B2F① → B3F①
→ B2F② → B1F② → 1F② → 2F③ → 4F② → B3F② → 5F②
同一楼层被多次到访时，**按 wiki 的第几部分切成多个分支**（parts 用 `records:[start,end]` 切区间）。

切点怎么找（三个硬依据，缺一就标 `confidence: low` 并在 evidence 写明"待实机确认"）：
1. **过场文件的 `place` 字段**（`S1016B`=红色精品店三楼、`S1061B`=豪华大厅 2 楼…）——最可靠；
2. **任务链** `RPGSystem/rpg-loc-quest-floor-*.json`（如 3F① 后的 `Q3025 回到2F`、B3F 的
   `Q-3011~Q-3015 去取皮革 - B1F/1F/2F/3F/4F`）——注意任务编号会跨楼层归档（3F 任务文件里有 Q4xxx）；
3. **对话里的折返标记**（"又回这层？""欢迎回来""你回来了""与上次尝试不同"）。
`scripts/ch10p2_segdump.py` 把楼层文件导成 `[序号] key 说话人 首句` 摘要，交给子代理并行定位切点最省事。
重建脚本：`scripts/ch10p2_resegment.py`（带 `--apply`，会先备份 plan）。

### 4.6 新章节整批补译流水线（ch10p2 起，零协完全没跟时用）

零协没跟的新章节（如 c10p2，EN 有 94 个文件零协全缺）走这五步，比在会话里逐条翻快得多：

```bash
PY=.venv/Scripts/python.exe
$PY scripts/ch10p2_prep.py --stats     # 清点：新增文件 / 记忆复用率 / 待翻条数
$PY scripts/ch10p2_prep.py             # 切任务包 → data/translate/ch10p2/tasks/（每包约 1.6 万字符）
$PY scripts/ch10p2_terms.py            # 术语表 → ch10p2/术语表.md + 术语对照.json
#   任务包派给子代理并行翻（先读 ch10p2/翻译规则.md + 术语表.md），答案写 ch10p2/ans/<同名>.json
$PY scripts/ch10p2_apply.py            # 合回结构 → files/（RPG·数据）+ out/zh/（剧情）
$PY scripts/ch10p2_plan.py             # 分段方案写进 story_rpg_plan.json + story_stages.json 骨架
$PY scripts/build_story_rpg.py --stage <关卡> && $PY scripts/verify_story_rpg.py --stage <关卡>
$PY scripts/ch10p2_enemies.py          # 敌人写进 enemy_map.json / stage_enemies.json
$PY scripts/install_supplement.py && $PY scripts/install_supplement.py --data-dir dist/data
```

- `prep.py` 会先建**全局翻译记忆**（零协 + 我方已译，按路径对齐），ch10p2 命中率 40.6%；
  再按英文原文**去重**（6290 → 5024 条）。这两步能砍掉一半活，别省。
- 定名前先查韩文原文（`Localize/kr/`）和零协实际用词，再定；拿不准的问用户，别猜。
- 敌人名统一：`stage_enemies.json` 里 wiki 来源的旧名要按零协改正；**改完还要反向同步译文文件**
  （游戏里显示的是 `data/translate/files/Enemies-a1c10*.json`，不是 stage_enemies）：
  `scripts/ch10p2_sync_enemy_names.py --apply`——方向是「stage_enemies（零协）→ 译文」，别搞反。
- 关卡改名用 `scripts/ch10p2_rename.py`（一次改 6 个 JSON + 测试用例，别手改漏）。
- 术语事后统一：`scripts/ch10p2_unify_terms.py`（Le Rouge/Le Noir→红派/黑派，带法文专名保护）、
  `scripts/ch10p2_unify_kaki.py`（卡基→褐派）。两个都是先 dry-run 看 `_term_diff.txt` / `_kaki_diff.txt`，
  确认没误伤再 `--apply`；**改完必须跑 `install_supplement.py`**，否则
  `test_补译文件与译稿一致` 会红。

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

## 6.6 全是「旁白」/ 说话人不显示（c10p2 起的新格式）

两个**互相独立**的原因，都要查：

1. **文本本身读不到** → `TextSource` 不回退补译目录。零协没有该文件时，只会读英文基线，
   读出空文本。现在 `TextSource.detect(..., supplement_dir=...)` 会自动回退
   `data/supplement/<相对路径>`；`app_state.py` 与 `export_story_rpg.py` 都已传参。
2. **文本有了但还是旁白** → **过场文件不再填 `teller`，说话人挪到了 `model`（韩文角色键）**。
   c10p2 的 `S1017B`~`S1029B`、`S1004B`/`S1005B` 大多如此（`teller=None`，但有 `model`）。
   判定：拿同一文件比 `EN_xxx.json` 与补译文件——字段**逐文件完全一致**就说明不是补译洗掉的。
   > 别以为零协会替我们补 `teller`：全量对比 941 个零协文件，teller 有无只差 39 条，
   > 零协**严格镜像**游戏原始结构。

   权威对照表是 `ScenarioModelCodes-AutoCreated.json`：
   `dataList[i] = {"id": 韩文键, "name": 显示名}`。零协包内是**中文名**版，
   英文基线是 `EN_` 前缀的英文名版。`TextSource.resolve()` 现在在 `teller`/`speaker`
   都为空时按 `model` 反查名字，优先级：英文基线 → 本工具补充表 → 零协对照表。

   零协表查不到的键（新章节角色）登记在
   `limbus_patcher/data/scenario_model_names.json`（只放补充，别抄整张表）。
   c10p2 已登记：`과거뫼르소`→默尔索、`법정 경위`→法警、`뷔페어른`→自助餐、
   `뷔페어린이`/`뷔페어린이신발`/`뷔페어린이옷`→普伊、`카르멘`→卡门。
   注意 `뷔페어린이`(EN=Pwie→普伊) 与 `뷔페어른`(EN=Buffet→自助餐) 是同一存在的两个形态，
   译名不同。零协对「过去形态」不加前缀（과거구보→仇甫、과거동랑→东朗）。

修完自查：`旁白` 占比应落在 **25%~30%**（都是 `model` 为空的真叙述句）；
10-4A/10-4B 参考值是 24.4% / 27.7%，说话人种类 80~91。

## 6.7 改到软件本体（`limbus_patcher/`）后要重新打包 exe

**只要动了 `limbus_patcher/*.py` 或往 `limbus_patcher/data/` 加文件，就必须重打 exe**——
用户双击跑的是单文件 exe，代码与内置数据都封在里面，光改仓库源码不生效。

加**新的内置数据文件**时，除了放进 `limbus_patcher/data/`，还得写进
`limbus_patcher.spec` 的 `_DATA_FILES`，否则 exe 里根本没有（运行时静默读不到，很难查）。

```bash
PY=.venv/Scripts/python.exe
export DSH_NO_MODAL=1 LIMBUS_PATCHER_HEADLESS=1     # 否则测试里的 Qt 弹窗会挂住
$PY -m pytest tests -q                              # 先过测试

# 打包：**不要用 --clean**，也不要直接打到 dist_build —— 沙箱对「单轮删除 >50 个文件」
# 会拦（PyInstaller 清 build/ 与覆盖 onedir 都命中），改用全新临时目录，不删任何已有文件
.venv/Scripts/pyinstaller.exe --noconfirm --workpath temp/pyi_work --distpath temp/pyi_dist limbus_patcher.spec
LIMBUS_ONEDIR=1 .venv/Scripts/pyinstaller.exe --noconfirm \
    --workpath temp/pyi_work_onedir --distpath temp/pyi_dist limbus_patcher.spec
$PY scripts/make_release.py --dist temp/pyi_dist    # → dist/release/LimbusPatcher-v<版本>-*.zip
```

**部署到用户实际运行的那份**（`dist/`，不是 `dist_build/`）：先备份旧 exe 再覆盖，
并把 `limbus_patcher/data/story_stages.json` 刷到 `dist/data/cache/story_stages.json`
（程序优先读后者）。这两个脚本就是干这个的，可直接用：
`temp/_deploy.py`（备份 + 覆盖 exe + 刷剧本数据；**默认取 `temp/pyi_dist*` 里最新的 exe**，
发布时请用 `--from <发布包解出的 exe>` 显式指定——它以前默认读 `dist_build/`，
那里可能是旧构建，曾误部署过一次）、
`temp/_finish_release.py`（不建暂存目录直接生成两个 zip + SHA256SUMS，绕开批量删除保护）。
改版本号就动 `limbus_patcher/__init__.py::__version__` + README 两处 + CHANGELOG；
exe 没有内嵌版本资源，版本号只在界面里看得到。

**验证**（别只看文件时间）：
```bash
.venv/Scripts/pyi-archive_viewer.exe -l temp/pyi_dist/边狱巴士汉化文本修改器.exe   # 确认新数据文件在包里
.venv/Scripts/python.exe scripts/verify_exe_code.py   # 解出 PYZ，确认修复代码真在包里（不只是数据）
$PY scripts/verify_packaged.py     # 真启动 dist/ 的 exe：建索引、无 crash.log
```

**「代码到底进没进包」怎么查**：单文件 exe 的模块在 PYZ 归档里，磁盘上看不到。
用 `scripts/verify_exe_code.py`——它用 `PyInstaller.archive.readers.CArchiveReader`
读 exe、`extract()` 出 PYZ（条目名是 `PYZ.pyz`），再用 `ZlibArchiveReader` 对
`limbus_patcher.textsource` 做符号检查。判定依据是模块顶层 `co_names` **和** `co_consts`
里的字符串常量（模块级导入的符号在 co_names，`CODES_FILE` 这类常量在 co_consts）。
注意：函数内的局部 `import`（如 `app_state.refresh_env` 里的 `from .textsource import
set_game_dirs`）不会出现在模块顶层，需看嵌套 code 对象，别据此误判为「没进包」。
交叉核对最省事：把发布包 zip 里的 exe 流式算 SHA256，和 `dist/` 部署的那份比，
一致即可确认「我验证的就是用户跑的那份」。

## 7. 常见坑（都踩过）

| 症状 | 原因 | 处理 |
|---|---|---|
| 游戏里技能显示 `UNKNOWN` / 口口 | 方括号效果 id 被翻译 | `repair_ch10.py`（说明字段按英文还原） |
| RPG 任务显示 `0901`、一串数字 | 标题/描述是空字符串 | `fill_missing_ch10.py`，再重装补译文件 |
| 关键字/状态面板空白 | Bufs/BattleKeywords 的 name/desc 为空或仍是英文 | 补译 + 重装 |
| `@@12@@`、`但丁@` 残留 | 占位符还原被机翻破坏 | `verify_ch10.py` 抓 placeholders；手工修 |
| 用户看到旧译文 | 没重新 `install_supplement` 或没点「应用到游戏」 | 重装 + 重应用 |
| 术语前后不一 | 多文件并行翻译 | 用零协包 grep 定标准，再全局统一 |
| 对话「全是旁白」 | ①`TextSource` 没回退补译目录（零协没这文件）；②过场文件 `teller` 为空，说话人在 `model` 韩文键 | 见 6.6；`scenario_model_names.json` 补零协表里没有的键 |
| 导出 md 里出现空的 `**` 行 | `*{text}*` 遇到空文本场景（`source=quest` 的任务结点） | 导出器已跳过空文本场景 |
| pytest 卡住不动 | `test_replace.py` / `test_headless_guard.py` 的 Qt 弹窗在无头环境阻塞 | `DSH_NO_MODAL=1 LIMBUS_PATCHER_HEADLESS=1 .venv/Scripts/python.exe -m pytest tests -q` |
| 部署完软件行为没变 | 部署脚本取错了来源（曾默认读 `dist_build/` 的旧构建） | `temp/_deploy.py --from <发布包解出的 exe>`；用 `scripts/verify_exe_code.py` 查 PYZ 符号 |
| 验证脚本打印的 crash.log 尾部有 Traceback，但判定「无新崩溃」 | `crash.log` 是**追加**的，尾巴可能是几天前的旧记录 | 比对 mtime（`crash_new` 字段），别看尾巴；确认旧可直接忽略 |
| `crash_native.log` 里有 `Windows fatal exception: code 0x8001010d` | taskkill /F 强杀 Qt 进程时在途的 COM 调用被打断，属验证副产品 | 看 mtime 是否在本次验证窗口内；旧的忽略即可 |

## 8. 汇报习惯

用户很在意 token：**先给结论和数字**（改了什么、多少处、验证结果、要他做什么），
不要贴大段原文/日志；长清单给文件名 + 计数，需要时再展开。
