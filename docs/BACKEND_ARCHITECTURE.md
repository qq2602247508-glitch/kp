# COC7 后端隔离与领域边界

本后端是独立的 COC7 守秘人助手，不是其他规则系统的兼容模式。

## 隔离约束

- Python 包名、SQLite、Alembic 历史、资料包清单与向量目录均独立。
- 生产包不得导入旧项目的领域模块。
- 战役和资料包的 `ruleset` 固定为 `coc7e`。
- 只有事务、审计、并发版本、本地模型与向量适配器一类中性机制可以在未来抽象复用。
- `tests/test_domain_isolation.py` 是最低污染门禁；后续新增 API、提示词和种子数据时需要扩展扫描范围。

## 当前领域核心

- Campaign：年代、启用资料包、房规和 KP 私密笔记。
- Investigator：八项属性、HP/MP/SAN/Luck、Move、DB/Build、信用评级、技能和背景故事。
- Skill：基础值、当前值、成长标记，并确定性派生一半与五分之一值。
- Roll：百分骰、奖励/惩罚骰、难度和成功等级，保留每颗十位骰以便审计。
- Source pack：版次、时代、优先级、文件哈希和索引状态。

## 规则引擎原则

模型不得自行计算检定结果。所有规则计算都应进入版本化纯函数，输出输入、阈值、结果和规则来源。当前只实现百分骰成功等级与调查员最基础派生值；年龄调整、战斗、理智、追逐、成长等在核对本地规则资料后分阶段加入。

## 数据库原则

初始迁移只包含 COC7 原生表。调查员技能和背景故事是独立子表；删除战役通过外键级联清理调查员数据。所有后续可变聚合都必须增加乐观并发版本和审计记录。

## M2 API

- `GET/POST /api/v1/campaigns`
- `GET/PUT/DELETE /api/v1/campaigns/{campaign_id}`
- `GET/POST /api/v1/campaigns/{campaign_id}/investigators`
- `GET/PUT/DELETE /api/v1/campaigns/{campaign_id}/investigators/{investigator_id}`
- `PUT .../{investigator_id}/skills`
- `PUT .../{investigator_id}/backstory`
- `POST /api/v1/rolls`
- `GET /api/v1/campaigns/{campaign_id}/audits`

PUT 请求携带 `expected_version`；DELETE 使用同名查询参数。版本过期返回 409，跨战役或不存在的 ID 返回 404。调查员创建时从 COC7 属性确定性初始化 HP、MP、SAN；完整替换时由后端重新验证资源上限。

检定请求包含战役、可选调查员与技能、目标值、难度、`bonus_penalty`（-2 到 2）以及可选的可复现骰面。省略骰面时由服务端生成。响应返回每颗十位骰、个位骰、最终点数、三档阈值、成功等级与是否满足要求，并把完整输入和结果写入不可变检定记录及战役审计。
