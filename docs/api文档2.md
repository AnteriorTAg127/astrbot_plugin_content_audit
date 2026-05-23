# 审核 API — 端口 8000

内容审核系统的核心审核接口，提供文本违规检测能力。

## 基础地址

```
http://<host>:8000
```

## 认证方式

所有审核接口（除 `/health` 外）必须携带 API Key，否则返回 `404`。

| 方式 | 说明 |
|------|------|
| `Authorization: Bearer <key>` | 推荐方式 |
| `X-Api-Key: <key>` | 备选方式 |
| `X-Admin-Token: <token>` | 管理后台 session（仅限管理端模拟请求，绕过 Key 检查） |

### API Key 分组与响应分级

| 分组 | 响应级别 |
|------|---------|
| `standard` | 仅返回基本判定结果，**不暴露具体违规词和详细日志** |
| `full` | 返回完整审核详情（关键词命中、语义相似度、LLM 理由） |

### 认证状态码

| 状态 | 含义 |
|------|------|
| **404** | 无 Key / 无效 Key / 禁用 Key |
| **200** | 审核完成（standard 分组仅含基础字段） |
| **403** | 仅 full 分组可查看完整细节（`/audit/full`） |

---

## 端点列表

### POST /audit

核心审核接口。检测单条文本是否违规。

**请求头：** 需 API Key 认证

**请求体（JSON）：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `sentence` | string | 是 | 待检测文本（最长 50000 字符） |
| `skip_llm` | boolean | 否 | 是否跳过 LLM 复核（默认 `false`） |
| `context` | string | 否 | 审核上下文，注入到 LLM 提示中辅助判断。例如对话场景、用户关系、历史背景等。仅在 L3（LLM 审核）阶段生效 |

**standard 分组响应示例：**

```json
{
  "sentence": "待检测文本",
  "has_violation": true,
  "source": "comprehensive",
  "request_id": "a1b2c3d4",
  "timestamp": "2026-05-22T12:00:00.000Z",
  "api_tier": "standard"
}
```

**full 分组响应示例：**

```json
{
  "sentence": "待检测文本",
  "has_violation": true,
  "keyword_result": {
    "hits": [{ "keyword": "违规词", "library": "色情词库", "matched_text": "weigui", "position": { "start": 0, "end": 4 } }],
    "is_violation": true,
    "match_count": 3,
    "libraries": ["色情词库", "补充词库"]
  },
  "semantic_result": {
    "hits": [{ "category": "色情", "similarity": 0.92, "sample_text": "..." }],
    "max_similarity": 0.92,
    "black_avg_similarity": 0.88,
    "white_avg_similarity": 0.42,
    "whitelist_hits": [{ "category": "白名单", "similarity": 0.45, "sample_text": "..." }],
    "is_violation": true,
    "effective_threshold": 0.67
  },
  "llm_result": {
    "is_violation": true,
    "category": "色情",
    "reason": "文本包含明显色情暗示..."
  },
  "source": "comprehensive",
  "request_id": "a1b2c3d4",
  "timestamp": "2026-05-22T12:00:00.000Z",
  "api_tier": "full"
}
```

---

### POST /audit/full

强制返回完整审核细节。**仅限 `full` 分组 API Key 调用。**

**请求头：** 需 full 分组 API Key 认证

**请求体：** 同 `/audit`

**响应：** 同 `/audit` 的 full 分组响应

---

### POST /audit/batch

批量审核，共享 Embedding 批次以提升效率。

**请求头：** 需 API Key 认证

**请求体（JSON）：**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `sentences` | string[] | 是 | 待检测文本数组 |
| `skip_llm` | boolean | 否 | 是否跳过 LLM（默认 `false`） |
| `context` | string | 否 | 审核上下文，统一应用到所有句子的 LLM 审核阶段 |

**响应：**

```json
{
  "total": 10,
  "violations": 3,
  "results": [ /* 每条结果同 /audit 响应 */ ],
  "request_id": "...",
  "timestamp": "...",
  "api_tier": "standard"
}
```

---

### GET /health

健康检查。**无需认证。**

**响应：**

```json
{
  "status": "ok",
  "uptime_sec": 3600,
  "services": {
    "keyword_matcher": "ready",
    "semantic_checker": "ready",
    "llm_checker": "enabled",
    "database": true
  },
  "cache": { "size": 128, "max_size": 1000 },
  "memory": {
    "rss_mb": 256,
    "heap_used_mb": 128
  }
}
```

---

## 处理流程

1. **高频缓存检查** — 命中直接返回，不走后续流程
2. **永久黑白名单** — 最高优先级，硬裁定
3. **L1 关键词匹配** — Aho-Corasick 多模式匹配，支持拼音模糊
4. **L2 语义检测** — 文本向量化后同时检索黑/白名单，计算 top-K 平均相似度
5. **L3 LLM 复核** — 大模型终判，短文本走专用 prompt 和缓存
6. **判定** — 根据判定模式输出最终结果

## 上下文注入（context）

可选字段 `context` 允许调用方传入额外的上下文信息，辅助 LLM 做出更准确的判断。常见场景：

- 对话场景描述（"群聊"、"私聊"、"客服对话"）
- 用户关系说明（"对方是陌生人"、"好友之间的调侃"）
- 历史背景（"该用户此前已三次触发违规判定"）

**实现细节：**

- context 仅注入到 L3（LLM 审核）阶段的 Prompt 中，L1 关键词和 L2 语义检测不感知该字段
- 短文本路径（text_too_short）不使用上下文，因为短文本审核结果会被持久缓存，注入上下文会导致缓存污染
- 如果 Prompt 模板中包含 `{context}` 占位符，上下文会替换到模板指定位置；否则自动追加到 Prompt 末尾
- 上下文文本经过与 `sentence` 同级别的安全处理（截断 2000 字符 + 转义特殊字符）
- 上下文不会出现在 API 响应中

## 判定模式

| 模式 | 逻辑 |
|------|------|
| `all` | L1 ∧ L2 ∧ L3 全部命中才判定违规 |
| `any` | 关键词命中即判违规（跳过 L2/L3） |

## 错误处理

所有错误信息均经过脱敏处理：API Key 被隐藏、文件路径被隐藏、过长消息被截断（200 字符限制）。
