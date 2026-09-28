# 第三方许可与来源声明

本程序（边狱巴士汉化文本修改器）自身代码以 **MIT** 许可发布，见 `LICENSE`。
发布包中还包含/依赖以下第三方组件与内容，各自的许可与来源如下。

## 1. Qt for Python（PySide6）— LGPL v3

- 用途：整个图形界面（Qt 6 / PySide6 6.11，含 QtCore / QtGui / QtWidgets / QtSvg 等模块）。
- 许可：**GNU Lesser General Public License v3**（LGPL-3.0）。
- 许可全文：https://www.gnu.org/licenses/lgpl-3.0.txt
- 源码：https://code.qt.io/ （Qt）、https://code.qt.io/cgit/pyside/pyside-setup.git/ （PySide6）
- 说明：程序以动态链接方式使用 PySide6/Qt。若你需要在替换 Qt 库后继续使用本程序，
  可自行安装 PySide6 并直接从源码运行（`pip install PySide6 && python main.py`），
  或使用「目录版（onedir）」发布包——其中的 Qt 动态库是独立文件，可按 LGPL 要求替换。

## 2. 游戏文本（**不随本发布包分发**）

- 程序**不包含**任何游戏原文、零协汉化译文或 wiki 剧情文本。
- 程序读取的是**你本机已安装**的：零协汉化包（`Lang/LLC_zh-CN`，版权归零协会汉化组）
  与游戏自带英文基线（`Assets/Resources_moved/Localize/en`，版权归 Project Moon）。
- 剧本数据文件（`data/cache/story_stages.json`）只保存**位置信息**
  （相对路径 + 记录下标 + 字段路径），文本在运行时从上述本机文件读取。

## 3. 卡面头像（**随发布包分发**，仅非商业用途）

- 发布包内含 **310 张**人格 / E.G.O 卡面缩略图（`limbus_patcher/data/portraits/`，约 18 MB，
  webp，最长边 640px），用于「人格图鉴 / 敌方图鉴」的卡片显示。
- 来源：一部分从**你本机**游戏资源中离线只读抽取（`scripts/extract_portraits.py`），
  一部分由灰机 wiki / Fandom 的卡图直链下载（`scripts/import_portrait_urls.py`、
  `scripts/fetch_portraits_fandom.py`），再统一压缩（`scripts/shrink_portraits.py`）。
- 授权：原始美术资源版权归 **Project Moon**；来自 wiki 的页面与卡图依
  **CC BY-NC-SA 4.0** 授权 —— 灰机 wiki「边狱公司」中文维基
  （<https://limbuscompany.huijiwiki.com>）与 Limbus Company Wiki (Fandom)。
- 这些图片**不属于**本仓库 MIT 许可的覆盖范围，仅供在已购买正版游戏的前提下做
  非商业的汉化对照使用。若你是权利人并希望移除，请提 issue，会立即从发布包与仓库中删除。

## 4. 其他运行期依赖

| 组件 | 许可 | 用途 |
| --- | --- | --- |
| Python 标准库（sqlite3 等） | PSF License | 索引、文件处理 |
| shiboken6 | LGPL-3.0 | PySide6 绑定层 |

## 6. 测试样本

`tests/fixtures/` 中的少量零协译文样本，版权归 **LocalizeLimbusCompany（零协会汉化组）** 所有，
依 **CC BY-NC-SA 4.0** 授权，**不属于**本仓库 MIT 许可的覆盖范围；仅用于自动化测试，未作修改再分发。

## 5. 免责声明

本程序为爱好者工具，与 **Project Moon**、**零协会汉化组** 均无隶属或合作关系。
仅供个人在已购买正版游戏的前提下做汉化对照与文本整理使用，请勿用于商业用途；
使用前请自行备份游戏目录。游戏与汉化包的一切权利归其各自权利人所有。
