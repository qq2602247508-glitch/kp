# Local AI COC KP Assistant

本地优先、纯文字的《克苏鲁的呼唤》第七版守秘人副驾驶。它服务于人类
KP：规则检索、调查员与人物管理、地点与线索编排、理智状态、战斗与追逐、
剧本准备，以及所有 AI 状态变更的人工确认。

## 产品边界

- 人类 KP 始终拥有最终裁决权。
- 规则回答必须携带本地资料出处；证据不足时明确拒答。
- 战役状态保存在独立 SQLite 数据库，规则向量使用独立 Qdrant collection。
- AI 只能创建待审核提案，不能绕过确认直接修改战役状态。
- 核心规则与时代、幻梦境、魔法等扩展资料分层启用，不能静默互相覆盖。
- 表格宏只作为文件内容读取，绝不执行。
- v1 不依赖云服务，也不会自动下载模型。

## 隔离约束

项目使用独立的：

- Python 包名 `coc_kp_assistant`
- 环境变量前缀 `COC_KP_`
- 后端端口 `8010`
- 前端端口 `5180`
- SQLite 文件 `data/coc_kp.db`
- 向量 collection `coc7_rules`
- 浏览器存储命名空间 `local-coc-kp-assistant`

任何其他规则体系的数据库、索引、迁移、测试夹具、提示词和导出文件都不得
导入。`scripts/check-domain-isolation.sh` 会对生产代码执行静态污染检查。

## 本地启动

依赖首次准备：

```bash
./scripts/setup.sh
```

同时启动前后端：

```bash
./scripts/dev.sh
```

单独启动：

```bash
./scripts/dev-backend.sh
./scripts/dev-frontend.sh
```

打开 `http://127.0.0.1:5180/`。前端 API 默认指向
`http://127.0.0.1:8010/api/v1`。

## 本地资料导入

先用只读 dry run 验证登记来源；它只向标准输出写入机器可读 JSON，不创建产物：

```bash
backend/.venv/bin/python -m coc_kp_assistant.ingestion \
  --catalog config/source-packs.example.json \
  --output-root data/generated-content/coc7 \
  --dry-run
```

移除 `--dry-run` 后才会把确定性的 JSON、Markdown 和导入报告写入
`data/generated-content/coc7`（该目录不入 Git）。PDF 必须已有文字层；DOCX、XLSX
和 XLSM 仅以 OOXML/ZIP 方式读取，绝不执行宏、公式或外部链接。

## 检查

```bash
./scripts/check.sh
```

检查脚本会运行领域隔离扫描；在后端和前端依赖已准备时，继续执行各自的
lint、类型检查、测试和构建。设置 `COC_KP_REQUIRE_ALL_CHECKS=1` 可要求缺少
任一开发环境时立即失败。

## 目录

```text
backend/       FastAPI、领域模型、SQLite、RAG 与 AI 提案
frontend/      React/Vite 守秘人控制台
scripts/       独立开发、设置与质量检查
data/          本地数据库、资料处理产物和向量索引（不入 Git）
docs/          架构、资料策略与领域说明
```
