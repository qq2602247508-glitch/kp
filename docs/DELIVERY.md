# 设置、迁移、备份与交付

## 就绪度

设置页调用 `GET /api/v1/delivery/readiness`，分别报告：

- 独立 SQLite 数据库是否可查询；
- `data/generated-content/coc7/ingestion-report.json` 是否为 COC7 就绪语料；
- `data/vectors/coc7_rules-manifest.json` 是否匹配
  `local-coc-kp-assistant`、`coc7e`、`coc7_rules` 和 `bge-m3:latest`；
- Ollama 是否已经安装 `bge-m3:latest` 与 `qwen3:30b-instruct`。

模型检查只读取 Ollama 的 `/api/tags`，使用短超时和 `trust_env=False`。它不
执行 `pull`，不下载模型，也不会把 loopback 请求送入系统代理。

## 战役资料包

设置页按战役读取 `config/source-packs.example.json`。默认权威资料会保持启用；
时代资料只有与战役时代兼容时才可勾选。保存时服务端重新检查：

- catalog 和 pack 都属于 `coc7e`；
- pack ID 存在且使用 `coc7e.` 命名空间；
- pack 的时代与战役兼容；
- campaign version 仍与页面一致。

成功修改会递增 campaign version 并写入审计记录。

## 战役导出与导入

导出为 JSON，包头固定为：

```json
{
  "product": "local-coc-kp-assistant",
  "ruleset": "coc7e",
  "schema_version": 1,
  "namespace": "local-coc-kp-assistant/coc7e"
}
```

包内包含战役、调查员与技能/背景、案件 session/人物/地点/场景/线索/关系/
手册资料/时间线、roll、规则操作、追逐、AI 提案及提案审计、状态审计。资料原文和
向量不会进入战役导出包。

导入先完整校验 envelope、表白名单、字段白名单、UUID、ruleset、campaign
归属和外键引用，再开启写入。任何错误都会回滚整个导入。相同 campaign ID
存在时返回冲突；当前版本没有“覆盖导入”，避免误伤已有档案。

## 一致性备份

`POST /api/v1/delivery/backups` 默认写入忽略版本控制的 `data/backups/`：

1. 使用 SQLite online backup API 得到运行中一致的数据库快照；
2. 对 vector root 的每个文件先计算 SHA-256；
3. 复制向量目录和索引 manifest；
4. 再次计算源与副本的 SHA-256；期间发生变化则放弃该次备份；
5. 写入带 product、ruleset、schema 和文件 checksum 的 `manifest.json`；
6. staging 目录原子改名为最终备份目录。

可指定一个已经存在的绝对目录。符号链接和相对路径会被拒绝。
`POST /api/v1/delivery/backups/verify` 只校验 manifest 和 checksum，明确返回
`restore_performed=false`；它不会隐式覆盖运行中的数据库或向量索引。

## 自动检查与 E2E 边界

`scripts/check.sh` 运行：

- COC7 与外部规则体系的领域隔离；
- desktop launcher shell/端口/路径回归；
- 后端 Ruff、mypy、完整 pytest；
- 前端 ESLint、TypeScript、完整 Vitest 和 production build。

后端 API 集成测试覆盖 health、campaign、case、规则与 mock provider 的 AI
提案确认，以及本页的导出/导入/备份关键路径。React 组件集成测试覆盖真实设置
页和交付操作入口。

本机有 Playwright 浏览器缓存，但当前项目没有可调用的 Playwright Node
依赖；构建期间遵守“不下载浏览器/模型”约束，没有临时联网安装。因此本次交付
未把一个无法在干净环境重现的 Playwright 命令伪装成已通过的浏览器测试。若
以后在项目依赖中预置 Playwright，可直接复用
`/Users/inagi/Library/Caches/ms-playwright`，并把真实 Chromium 流程加入
`scripts/check.sh`，仍须设置禁止浏览器下载。

## 启动

桌面入口：

```text
/Users/inagi/Desktop/启动本地COC-KP助手.command
```

仓库内 launcher 会检查后端 `8010` 与前端 `5180`，按需启动服务，等待双方
就绪后打开 `http://127.0.0.1:5180/`。日志保存在 `data/logs/`。
