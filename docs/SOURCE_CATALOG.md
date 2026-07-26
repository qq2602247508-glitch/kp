# COC 来源目录

本目录只登记用户提供资料的来源元数据，不包含、复制或转录书籍正文。真正导入 Source Pack 时，必须把文件放入独立包目录，生成 SHA-256，并以 `SourceFileManifest.relative_path` 登记。

机器可读清单位于 `config/source-packs.example.json`。

## 规则优先级

| 优先级 | 层级 | 处理方式 |
|---:|---|---|
| 10 | COC7 核心规则书 v1.2.1 | 默认启用；七版规则裁决的最高权威 |
| 20 | 七版调查员手册 1.21 | 默认启用；与核心书冲突时服从核心书 |
| 30 | 快速开始规则 | 默认关闭；教学用，避免与完整规则重复 |
| 40–50 | 守秘人卡组 | 默认关闭；仅作速查或随机候选 |
| 60 | 七版角色卡模板 | 默认关闭；只提供字段和布局参考 |
| 70 | 魔法大典 | 默认关闭；由战役显式启用 |
| 80–90 | 幻梦境、时空穿梭与时代角色卡 | 默认关闭；按战役时代显式启用 |
| 900 | 40 周年纪念版 | 旧版隔离；禁止参与默认七版检索 |

## 已登记来源

| pack_id | 版次 / 层级 | 时代 | 默认 | 格式 / 页数 |
|---|---|---|---:|---|
| `coc7e.core.zh-v1.2.1` | 7e / core | 通用 | 是 | PDF / 380 |
| `coc7e.investigator-handbook.zh-v1.21` | 7e / investigator | 通用 | 是 | PDF / 162 |
| `coc7e.quickstart.zh-db-noart` | 7e / quickstart | 通用 | 否 | DOCX |
| `coc7e.keeper-deck.weapons.zh` | 7e / card_deck | 通用 | 否 | PDF / 13 |
| `coc7e.keeper-deck.phobias.zh` | 7e / card_deck | 通用 | 否 | PDF / 13 |
| `coc7e.keeper-deck.bystanders.zh` | 7e / card_deck | 通用 | 否 | PDF / 13 |
| `coc7e.keeper-deck.misfortunes.zh` | 7e / card_deck | 通用 | 否 | PDF / 13 |
| `coc7e.character-sheet.cy21.1-lite` | 7e / investigator template | 未指定 | 否 | XLSX |
| `coc7e.character-sheet.cy22-plus-preview` | 7e / investigator template | 未指定 | 否 | XLSX |
| `coc7e.magic-compendium.zh-v1.1` | 7e supplement / magic | 通用 | 否 | PDF / 158 |
| `coc7e.time-travel.volume-6.zh` | 7e supplement / era | time-travel | 否 | PDF / 52 |
| `coc7e.dreamlands.zh` | 7e supplement / setting | dreamlands | 否 | PDF / 165 |
| `coc7e.time-travel.sheet.future-v1.5` | 7e supplement / era | future | 否 | XLSM |
| `coc7e.time-travel.sheet.apocalypse-v1.5` | 7e supplement / era | apocalypse | 否 | XLSM |
| `coc7e.time-travel.sheet.gaslight-v1.5` | 7e supplement / era | gaslight | 否 | XLSM |
| `coc7e.time-travel.sheet.roman-v1.5` | 7e supplement / era | roman | 否 | XLSM |
| `coc7e.time-travel.sheet.dreamlands-v1.5` | 7e supplement / era | dreamlands | 否 | XLSM |
| `coc7e.time-travel.sheet.dark-ages-v1.5` | 7e supplement / era | dark-ages | 否 | XLSM |
| `coc7e.time-travel.sheet.iceland-v1.5` | 7e supplement / era | iceland | 否 | XLSM |
| `coc-classic.40th-anniversary.zh-build2306` | classic-40th / legacy | 未指定 | 否 | PDF / 470 |

原始绝对路径保存在机器可读清单中，全部指向用户给出的 `/Volumes/personal_folder/...` 文件。PDF 页数来自只读 `pdfinfo` 盘点；DOCX、XLSX、XLSM 不伪造页数。

## 宏与外部内容安全

- 永不执行 XLSM 中的 VBA、公式自动计算、数据连接或外部链接。
- 只允许读取 OOXML 中的工作表、单元格和样式元数据；跳过 `vbaProject.bin`。
- 不跟随文档内的外部链接，也不调用 Office/LibreOffice 打开宏。
- 导入后的文件必须位于自己的 Source Pack 根目录，使用相对路径并记录真实 SHA-256。
- `幻梦之书.pdf` 有打印权限限制；导入流程不得尝试绕过。

## 检索隔离

默认检索仅启用 `ruleset=coc7e` 且 `default_enabled=true` 的来源。扩展包必须由战役明确启用，时代包还必须匹配当前时代。`edition=classic-40th` 的纪念版始终处于旧版隔离区；如 KP 主动查询旧版，结果也必须醒目标明版次，不得与七版片段合并为单一答案。

COC 项目使用独立数据库、向量集合和索引目录。本清单不引用 D&D 项目的规则包、技能、装备、法术或正文。
