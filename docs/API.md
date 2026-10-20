# ClassEcho 后端 API 文档

适用范围：当前仓库的 FastAPI 后端，应用版本 `0.1.0`；核对日期：2026-10-20。

本文依据实际路由、Pydantic 请求模型和数据库返回字段编写，供接口调用、后端学习和答辩使用。所有正文、ID、时间及密钥示例均为说明性数据，不是课堂材料或真实调用记录。示例中的 ID 必须替换为当前实例返回的值。

## 1. 接口约定

### 1.1 地址与启动

在仓库根目录、依赖和前端构建已就绪时执行：

```bash
bash scripts/start.sh
```

开发版默认地址为 `http://127.0.0.1:8765`；业务接口统一以 `/api` 开头。`CLASSECHO_API_PORT` 可修改开发版 API 端口，桌面安装包使用运行时选择的本机端口。

启动后可访问自动文档：

- Swagger UI：`http://127.0.0.1:8765/docs`
- ReDoc：`http://127.0.0.1:8765/redoc`
- OpenAPI JSON：`http://127.0.0.1:8765/openapi.json`

Swagger 主要提供请求结构；当前多数接口直接返回数据库字段，没有声明完整的响应模型。`PUT /api/settings/notes-api` 手动解析 JSON，其请求体也未完整出现在自动生成的 OpenAPI 中，应结合本文查看。

### 1.2 请求与响应

| 项目 | 约定 |
| --- | --- |
| JSON 请求 | `Content-Type: application/json` |
| 文件上传 | `multipart/form-data`；使用 curl `-F` 时让 curl 自动设置 boundary |
| 普通成功响应 | 直接返回对象或数组，没有统一的 `code/message/data` 包装 |
| 删除成功 | `204 No Content`，没有响应体 |
| 时间 | 数据记录的 `created_at/updated_at` 为 UTC ISO 8601 字符串 |
| 单位 | 录音 `duration` 为秒；`start_ms/end_ms/position_ms/offset_ms` 为毫秒 |
| ID | 服务器生成的对象 ID 通常为 32 位小写十六进制字符串；片段 ID 如 `segment_00001` |
| 查询列表 | 当前无分页参数，按各接口规定的顺序返回完整数组 |
| 多余字段 | 本文中的 JSON 请求模型均禁止未声明字段；通常返回 `422`，AI 设置接口返回 `400` |

当前没有账号、登录令牌或用户权限隔离；接口用于本机应用。服务启动器仅监听回环地址。`TrustedHostMiddleware` 允许 `127.0.0.1`、`localhost` 和测试用 `testserver`。写请求如带 `Origin`，只接受 HTTP、本机主机名及 `5173` 或当前 API 端口；不符合返回 `403`。未带 `Origin` 的命令行调用不受这一来源检查限制。这不是用户身份认证，也不等于配置了跨域 CORS 授权。

### 1.3 错误格式与状态码

业务错误通常为：

```json
{"detail":"转录已被修改，请刷新后重试"}
```

FastAPI 参数校验错误通常为 `422`，其中 `detail` 是数组，例如：

```json
{
  "detail": [
    {"type":"missing","loc":["body","name"],"msg":"Field required","input":{}}
  ]
}
```

| 状态码 | 当前用途 |
| --- | --- |
| `200` | 查询、修改、取消任务、媒体完整读取、导出成功 |
| `201` | 创建课程、导入录音、创建标记、打开示例 |
| `202` | 已受理任务或预览；必须继续检查返回的 `state` |
| `204` | 删除成功，无响应体 |
| `206` | 媒体 Range 分段读取成功 |
| `400` | 业务规则不满足、媒体无效、任务不能重试或取消、AI 设置格式错误等 |
| `403` | 拒绝非允许来源的本机写请求 |
| `404` | 资源不存在、预览不存在或过期、未知 GET API 路径 |
| `409` | 版本冲突、AI 接口确认过期、模型未就绪、删除时仍有活动任务 |
| `413` | 文件或实时分片超过大小限制 |
| `422` | 请求字段、类型、枚举或长度等校验失败 |
| `429` | 实时预览待处理数已达上限 |
| `503` | 实时预览投递队列失败 |

不存在或不允许的 HTTP 方法也可能由框架返回 `405`；未处理的服务内部异常可能返回 `500`。异步处理中的错误通常保存为任务的 `state: failed` 和 `error`，不会使已经结束的创建任务请求变为 HTTP 错误。

## 2. 接口总览

共 26 个业务接口，不计自动文档和未知路径兜底路由。

| 方法 | 路径 | 用途 | 正常响应 |
| --- | --- | --- | --- |
| GET | `/api/health` | API 与 Redis 健康检查 | 200 |
| GET | `/api/settings` | 读取公开设置及模型状态 | 200 |
| PUT | `/api/settings/notes-api` | 保存用户自选 AI 接口 | 200 |
| GET | `/api/usage` | 读取历史 Qwen 费用记录 | 200 |
| POST | `/api/demo` | 创建或复用内置示例 | 201 |
| GET | `/api/courses` | 课程列表 | 200 |
| POST | `/api/courses` | 创建课程 | 201 |
| GET | `/api/courses/{course_id}/lectures` | 课程内录音列表 | 200 |
| POST | `/api/courses/{course_id}/lectures` | 上传音视频 | 201 |
| GET | `/api/lectures/{lecture_id}` | 聚合查询录音详情 | 200 |
| DELETE | `/api/lectures/{lecture_id}` | 删除录音及关联资源 | 204 |
| GET | `/api/lectures/{lecture_id}/media` | 播放原始媒体 | 200 / 206 |
| POST | `/api/lectures/{lecture_id}/transcribe` | 创建完整录音转录任务 | 202 |
| GET | `/api/lectures/{lecture_id}/transcript` | 查询当前或指定转录版本 | 200 |
| PATCH | `/api/lectures/{lecture_id}/transcript` | 修订转录并生成新版本 | 200 |
| POST | `/api/lectures/{lecture_id}/notes` | 创建笔记整理任务 | 202 |
| GET | `/api/lectures/{lecture_id}/notes` | 查询全部笔记版本 | 200 |
| PUT | `/api/notes/{note_id}` | 保存笔记修订和个人补充 | 200 |
| GET | `/api/jobs/{job_id}` | 查询持久任务 | 200 |
| POST | `/api/jobs/{job_id}/cancel` | 取消排队任务 | 200 |
| POST | `/api/jobs/{job_id}/retry` | 重试失败任务 | 202 |
| POST | `/api/lectures/{lecture_id}/bookmarks` | 创建回听疑问标记 | 201 |
| DELETE | `/api/bookmarks/{bookmark_id}` | 删除标记 | 204 |
| GET | `/api/lectures/{lecture_id}/export` | 导出 Markdown、SRT、JSON | 200 |
| POST | `/api/live-transcriptions` | 提交本地实时预览分片 | 202 |
| GET | `/api/live-transcriptions/{identifier}` | 查询实时预览 | 200 |

## 3. 公共响应结构

以下名称是本文使用的结构简称；不是接口外层的字段名称。

### 3.1 Course：课程

```json
{
  "id":"11111111111111111111111111111111",
  "name":"数据库原理",
  "description":"用于学习事务与并发控制",
  "created_at":"2026-10-20T08:00:00+00:00"
}
```

### 3.2 Lecture：录音材料

一个 `Lecture` 对应一份导入的音视频，不等同于课程。上传成功时尚未转录。

```json
{
  "id":"22222222222222222222222222222222",
  "course_id":"11111111111111111111111111111111",
  "title":"事务示例",
  "filename":"事务示例.wav",
  "sha256":"0000000000000000000000000000000000000000000000000000000000000000",
  "duration":10.0,
  "media_suffix":".wav",
  "active_transcript_id":null,
  "is_demo":false,
  "created_at":"2026-10-20T08:01:00+00:00"
}
```

`sha256` 是上传内容的摘要，不代表当前存在按摘要去重的上传机制。`title` 来自文件名去扩展名后截取前 200 字符，`filename` 最多保存 255 字符。

### 3.3 Transcript：转录版本

```json
{
  "id":"33333333333333333333333333333333",
  "lecture_id":"22222222222222222222222222222222",
  "parent_id":null,
  "engine":"mlx-whisper",
  "model":"mlx-community/whisper-small-mlx",
  "revision":"45f3915923c7a79a5a5b5a7d909d39aeb0e5630e",
  "segments":[
    {
      "id":"segment_00001",
      "start_ms":0,
      "end_ms":9000,
      "raw_text":"事務具有原子性。",
      "text":"事务具有原子性。"
    }
  ],
  "metrics":{},
  "created_at":"2026-10-20T08:02:00+00:00"
}
```

- `raw_text` 保留模型原始识别文字；`text` 是繁简转换或用户修订后的文字。
- 修订产生新对象，`parent_id` 指向被修订版本；旧版本不覆盖。
- `revision` 是模型版本标识，不是转录修订次数。转录版本由 `id/parent_id` 区分。
- 真实转录的 `metrics` 可含 `elapsed_seconds`、`rtf`、`process_peak_rss_bytes`、`mlx_peak_bytes` 和 `text_normalization`。其中 `rtf` 为识别耗时除以音频时长；内存指标不是整个桌面应用总内存。

### 3.4 Note：笔记版本

```json
{
  "id":"44444444444444444444444444444444",
  "lecture_id":"22222222222222222222222222222222",
  "transcript_id":"33333333333333333333333333333333",
  "provider":"extractive",
  "model":"local-extractive-v1",
  "prompt_version":"v1",
  "content":{
    "title":"事务示例",
    "sections":[
      {
        "heading":"逐段摘录 1",
        "items":[
          {"kind":"course_content","text":"事务具有原子性。","source_segment_ids":["segment_00001"]}
        ]
      }
    ]
  },
  "text_edits":{},
  "user_markdown":null,
  "edit_version":0,
  "created_at":"2026-10-20T08:03:00+00:00"
}
```

| 字段 | 含义 |
| --- | --- |
| `transcript_id` | 笔记固定引用的转录版本，不随当前转录切换 |
| `provider` | `extractive` 本地摘录、`api` 用户接口、`demo` 示例、历史兼容值 `qwen` |
| `content` | 原始生成内容；修订正文时不覆盖它 |
| `text_edits` | 条目修订映射，键为从 0 开始的 `章节索引.条目索引`，如 `0.0` |
| `user_markdown` | 单独保存的个人补充 |
| `edit_version` | 并发修改校验版本，成功保存后加 1 |

条目 `kind` 允许 `course_content`、`example`、`task`、`uncertain`。每条包含 1—100 个来源片段 ID，引用必须属于该笔记来源转录。结构校验只能检查格式和引用存在性，不能证明文字语义正确或没有幻觉。

### 3.5 Job：持久任务

```json
{
  "id":"55555555555555555555555555555555",
  "lecture_id":"22222222222222222222222222222222",
  "kind":"transcribe",
  "state":"queued",
  "stage":"queued",
  "attempt":1,
  "parameters":{"model":"small","initial_prompt":""},
  "checkpoint":{},
  "error":null,
  "result_id":null,
  "created_at":"2026-10-20T08:02:00+00:00",
  "updated_at":"2026-10-20T08:02:00+00:00"
}
```

| 字段 | 含义 |
| --- | --- |
| `kind` | `transcribe` 或 `notes` |
| `state` | `queued`、`running`、`succeeded`、`failed`、`cancelled` |
| `stage` | 处理阶段，常见为 `queued/normalize/download/transcribe/draft/validate/complete/cancelled` |
| `attempt` | 初始为 1，手动重试时加 1 |
| `parameters` | 创建任务时保存的参数，不包含 `force`，不包含 AI 密钥 |
| `checkpoint` | 已完成步骤或 AI 分块结果；API 笔记可含 `notes_progress.completed/total` |
| `result_id` | 成功时为转录 ID 或笔记 ID，否则通常为 `null` |
| `error` | 失败原因；失败后 `stage` 可能仍是出错前的阶段，判断成败应看 `state` |

正常状态路径为 `queued → running → succeeded/failed`；排队时可转为 `cancelled`，失败时可重试回到 `queued`。投递队列失败也可能直接 `queued → failed`。

### 3.6 Bookmark：回听疑问标记

```json
{
  "id":"66666666666666666666666666666666",
  "lecture_id":"22222222222222222222222222222222",
  "position_ms":5000,
  "question":"这里的回滚是什么意思？",
  "created_at":"2026-10-20T08:04:00+00:00"
}
```

## 4. 系统、设置与示例

### 4.1 GET /api/health

无请求体或查询参数。返回：

```json
{"status":"ok","redis":true}
```

配置 `CLASSECHO_INSTANCE_ID` 时额外返回 `instance_id`。Redis 不可用时通常仍返回 `200`，但 `redis: false`；不能只看 HTTP 状态判断队列可用，也不能以此证明 worker 或模型正常。

### 4.2 GET /api/settings

无参数。返回公开配置：

```json
{
  "qwen_configured":false,
  "qwen_model":"qwen-plus",
  "prices_configured":false,
  "budget":{"budget_cny":0.0,"committed_cny":0.0,"remaining_cny":0,"unknown_calls":0},
  "notes_api":{"base_url":"","model":"","key_configured":false,"configured":false,"revision":""},
  "models":[
    {"name":"small","repo":"mlx-community/whisper-small-mlx","revision":"45f3915923c7a79a5a5b5a7d909d39aeb0e5630e","ready":false},
    {"name":"turbo","repo":"mlx-community/whisper-large-v3-turbo","revision":"a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb","ready":false}
  ],
  "max_file_mb":500,
  "max_minutes":90
}
```

`ready` 表示对应固定版本的本地模型文件已标记就绪。该接口不触发下载。`qwen_*`、`prices_configured`、`budget` 为历史兼容字段，不代表用户自选 AI 接口的费用统计。

### 4.3 PUT /api/settings/notes-api

保存配置本身不调用模型。

| JSON 字段 | 必填 | 默认值与约束 |
| --- | --- | --- |
| `base_url` | 是 | 字符串，最多 2000 字符；允许空字符串以保存未配置状态 |
| `model` | 是 | 字符串，最多 200 字符；会去除首尾空白，可为空 |
| `api_key` | 否 | 默认为 `null`，最多 8192 字符；去除首尾空白后不能含其他空白字符 |

说明性请求（域名与密钥均为不可用占位值）：

```json
{"base_url":"https://provider.example.invalid/v1","model":"example-model","api_key":"EXAMPLE_ONLY_NOT_A_REAL_KEY"}
```

响应仅返回公开字段：

```json
{"base_url":"https://provider.example.invalid/v1","model":"example-model","key_configured":true,"configured":true,"revision":"77777777777777777777777777777777"}
```

规则与错误：

- URL 允许 HTTP(S)，禁止内嵌用户名密码、查询参数、fragment 和空白字符；结尾斜杠及 `/chat/completions` 后缀会被规范化。
- 每次保存产生新 `revision`。整理请求须携带当前版本及用户确认；排队或分块期间配置变化会阻止继续向旧配置发起调用。
- 未提供密钥、提供 `null` 或空密钥时：地址相同则保留旧密钥，地址不同则不沿用旧密钥。因此“空密钥”不是同地址清除密钥的操作。
- `configured` 只表示地址、模型和密钥非空，不代表真实服务已联通。
- 格式错误、非法 JSON、多余字段等返回脱敏的 `400`，不回显提交的密钥。
- 配置在本机 `data/notes-api.json` 中以明文保存，文件权限为 `0600`；`SecretStr` 和响应脱敏不等于磁盘加密。不要把配置提交到仓库。

### 4.4 GET /api/usage

无参数。返回历史 Qwen 专用路径的预算汇总与记录，记录按创建时间倒序：

```json
{
  "summary":{"budget_cny":0.0,"committed_cny":0.0,"remaining_cny":0,"unknown_calls":0},
  "records":[]
}
```

记录字段为 `id/job_id/model/input_tokens/output_tokens/reserved_cny/actual_cny/billing_state/created_at`；`actual_cny` 可为 `null`，`billing_state` 可为 `reserved/estimated/rejected/unknown`。`estimated` 表示根据响应 token 用量和本机单价计算，并非服务商账单确认。`committed_cny` 对未确定金额的调用使用预留金额。当前 `provider: api` 不生成这些费用记录，不能把此接口解释为所有模型的实时账单。

### 4.5 POST /api/demo

无请求体。返回 `201`：

```json
{"course_id":"11111111111111111111111111111111","lecture_id":"22222222222222222222222222222222"}
```

首次调用用 `samples/demo.json` 自写文本和 macOS Tingting 合成语音创建示例；转录与笔记预先生成，不执行 Whisper 或外部 AI。已有可用示例时复用 ID，仍返回 `201`。缺少系统语音能力或媒体处理失败时返回 `400`。

## 5. 课程、录音与媒体

### 5.1 GET /api/courses

无参数。返回 `Course[]`，按 `created_at` 升序；空列表为 `[]`。

### 5.2 POST /api/courses

JSON 请求：

```json
{"name":"数据库原理","description":"事务与并发控制"}
```

`name` 必填，1—120 字符，去除首尾空白后不可为空；`description` 可省略，默认为 `""`，最多 2000 字符。成功返回 `201` 和完整 `Course`；校验失败返回 `422`。当前无课程重名校验。

### 5.3 GET /api/courses/{course_id}/lectures

路径参数 `course_id` 为课程 ID。返回 `Lecture[]`，按 `created_at` 倒序；课程不存在返回 `404`。

### 5.4 POST /api/courses/{course_id}/lectures

路径参数 `course_id` 为课程 ID。请求为 multipart，必填文件字段名 `file`：

```bash
curl -X POST "$BASE_URL/api/courses/$COURSE_ID/lectures" \
  -F "file=@$AUDIO_FILE"
```

`BASE_URL/COURSE_ID/AUDIO_FILE` 需事先赋值；`AUDIO_FILE` 必须是本机实际存在的文件。

规则：

- 支持 `.mp3/.m4a/.wav/.mp4/.webm`；需有可读取的有效音轨，时长大于 0 且不超过 5400 秒。
- 文件上限为 `500 × 1024 × 1024` 字节。文件按块写入，同时计算 SHA256。
- 去掉上传文件名中的路径部分；服务器用生成的录音 ID 组织媒体目录。
- WebM 导入时先规范化，以处理浏览器录音缺少时长头的情况。
- 成功返回 `201` 和 `Lecture`，`active_transcript_id` 为 `null`；不会自动创建转录任务。

错误：课程不存在 `404`；缺少文件字段 `422`；超过大小 `413`；扩展名不支持、无有效音轨、超时、超 90 分钟等 `400`。导入失败会清理本次创建的媒体目录。

### 5.5 GET /api/lectures/{lecture_id}

路径参数为录音 ID。返回 `Lecture` 的全部字段，并增加：

| 字段 | 结构与含义 |
| --- | --- |
| `transcript` | 当前 `Transcript`，未转录时为 `null` |
| `transcript_versions` | 所有转录版本的字段，移除 `segments`，按创建时间倒序 |
| `notes` | 完整 `Note[]`，按创建时间倒序 |
| `jobs` | 完整 `Job[]`，按创建时间倒序 |
| `bookmarks` | `Bookmark[]`，按 `position_ms` 升序 |

不存在返回 `404`。查询过程中会核对排队或运行任务与 RQ 状态，必要时将失联任务标为失败；不是完全不改变内部状态的静态读取。

### 5.6 DELETE /api/lectures/{lecture_id}

无请求体。成功返回 `204`。数据库内删除该录音、标记、笔记、转录及任务，然后删除媒体目录。当前代码没有删除其所属课程，也未显式清理历史 `Usage` 费用记录。

不存在返回 `404`；仍有 `queued/running` 任务返回 `409`。数据库事务与文件系统删除不是同一原子事务：数据库已提交后若目录删除失败，不能声称它们一定同时回滚。

### 5.7 GET /api/lectures/{lecture_id}/media

无查询参数。返回原始媒体文件，支持浏览器播放及 Range 请求：

```bash
curl -i "$BASE_URL/api/lectures/$LECTURE_ID/media" -H 'Range: bytes=0-15'
```

完整读取通常 `200`，有效范围读取 `206` 并带 `Content-Range`；资源或原始文件不存在 `404`，无效范围也可能由文件响应返回 `416`。该接口不返回 JSON，不自动返回规范化后的 WAV。

## 6. 完整录音转录与修订

### 6.1 POST /api/lectures/{lecture_id}/transcribe

路径参数为录音 ID。JSON 请求体必需，但可传 `{}` 使用默认值：

| 字段 | 必填 | 默认值与含义 |
| --- | --- | --- |
| `model` | 否 | `small`；仅允许 `small/turbo` |
| `initial_prompt` | 否 | `""`，最多 2000 字符，作为识别提示词 |
| `force` | 否 | `false`；是否绕过相同参数成功任务的复用 |
| `after_transcribe` | 否 | 默认省略或 `null`，不自动整理；对象结构见下 |

转录后自动接续本地摘录：

```json
{"model":"small","after_transcribe":{"provider":"extractive"}}
```

转录后自动接续用户 AI 接口：

```json
{
  "model":"small",
  "after_transcribe":{"provider":"api","consent":true,"api_revision":"77777777777777777777777777777777"}
}
```

`after_transcribe.provider` 必填，仅允许 `extractive/api`；`consent` 默认 `false`，`api_revision` 默认 `""`、最多 80 字符。API 模式必须先完成配置，并使用当前配置版本明确确认发送转录文字。

响应为 `202 + Job`，其 `kind` 为 `transcribe`。可能复用已有任务，也可能因队列投递失败立即返回 `state: failed`；不能假设所有 `202` 都是新建且排队成功。

Worker 依次规范化音频、准备模型、执行 Whisper，保存转录并切换 `active_transcript_id`。有自动整理设置时，转录与下一笔持久笔记任务在同一数据库事务中保存，再投递队列。转录任务成功不等于笔记任务也成功，应查询详情中的两种任务或笔记结果。

错误：录音不存在 `404`；AI 未配置 `400`；缺少确认或配置版本过期 `409`；同类活动任务参数不同 `400`；参数校验失败 `422`。模型下载、识别及队列故障也可能在创建之后记录为任务失败。

### 6.2 GET /api/lectures/{lecture_id}/transcript

| 参数 | 位置 | 必填 | 含义 |
| --- | --- | --- | --- |
| `lecture_id` | 路径 | 是 | 录音 ID |
| `version_id` | 查询 | 否 | 指定转录 ID；省略时读取当前活动版本 |

返回完整 `Transcript`。录音不存在、没有当前转录、指定版本不存在或属于其他录音时返回 `404`。

### 6.3 PATCH /api/lectures/{lecture_id}/transcript

JSON 请求：

```json
{
  "base_version_id":"33333333333333333333333333333333",
  "edits":{"segment_00001":"事务具有原子性，失败时需要回滚。"}
}
```

两字段均必填。`edits` 为片段 ID 到文字的映射，1—10000 项；每段最多 20000 字符，总文字最多 500000 字符。当前允许空修订文本，不应将它与笔记正文的“禁止空白”规则混淆。

成功返回 `200 + 新 Transcript`：保留 `raw_text` 和时间戳、设置 `parent_id`、切换当前版本。原版本及基于它生成的笔记继续保留。仅修改转录不会自动更新笔记。

错误：录音不存在 `404`；`base_version_id` 与当前活动版本不同 `409`；片段不存在 `400`；字段校验失败 `422`。

## 7. 笔记生成与编辑

### 7.1 POST /api/lectures/{lecture_id}/notes

| JSON 字段 | 必填 | 默认值与含义 |
| --- | --- | --- |
| `transcript_id` | 是 | 笔记来源转录 ID，可指定属于该录音的旧版本 |
| `provider` | 否 | `extractive`；支持 `extractive/api/qwen` |
| `consent` | 否 | `false` |
| `api_revision` | 否 | `""`，最多 80 字符 |
| `force` | 否 | `false`，成功任务复用规则见第 8 节 |

本地摘录请求：

```json
{"transcript_id":"33333333333333333333333333333333","provider":"extractive"}
```

AI 整理请求：

```json
{
  "transcript_id":"33333333333333333333333333333333",
  "provider":"api",
  "consent":true,
  "api_revision":"77777777777777777777777777777777"
}
```

返回 `202 + Job`，`kind: notes`。成功结果为一个新的 `Note`，`result_id` 指向它。

- `extractive`：逐段摘录，非 AI 摘要，不调用外部接口。
- `api`：使用已保存的用户接口；只发送来源转录的文字与片段 ID，不发送音频。要求配置可用、`consent: true`、当前 `api_revision`。
- `qwen`：旧版兼容路径，要求 `consent: true` 及本机原有专用配置、价格和预算；不是当前前端主要入口，不适合作为新集成默认选择。

API 模式当前限制：总转录文字不超过 60000 字符；每块最多 8000 字符，单片段超过该值会失败；边界最多保留 2 段且不超过 1000 字符重叠，最多 16 块。每块校验结构和引用并保存检查点，全部完成才发布笔记；超时、截断或引用无效不自动重试。手动重试可复用有效检查点，但不能保证外部调用严格只发生一次。

错误：录音或来源转录不存在 `404`；转录属于其他录音、AI 未配置、旧 Qwen 未确认或同类活动任务冲突 `400`；API 确认缺失或配置版本过期 `409`；字段校验失败 `422`。外部服务失败一般通过任务查询返回，而非创建请求直接报错。

### 7.2 GET /api/lectures/{lecture_id}/notes

返回 `Note[]`，按创建时间倒序；无笔记返回 `[]`，录音不存在返回 `404`。当前没有单独的 `GET /api/notes/{note_id}`，按 ID 找笔记需从该列表或录音详情获取。

### 7.3 PUT /api/notes/{note_id}

| JSON 字段 | 必填 | 默认值与约束 |
| --- | --- | --- |
| `edit_version` | 是 | 读取笔记时获得的当前整数版本，至少为 0 |
| `markdown` | 否 | 默认 `null`；个人补充，最多 300000 字符；空字符串可清空补充 |
| `text_edits` | 否 | 默认 `null`；最多 10000 项，修订文字总计最多 300000 字符 |

```json
{
  "edit_version":0,
  "markdown":"我的理解：转账中途失败时，需要回滚。",
  "text_edits":{"0.0":"事务中的一组操作要么全部成功，要么全部失败。"}
}
```

`text_edits` 为增量修改，不是整份映射替换。键是从 0 开始的 `章节索引.条目索引`，值为 1—5000 字符且不可全空白的正文；值设为 `null` 或与原文完全相同时删除该条覆盖，恢复原始正文。省略的已有覆盖保留。

成功返回更新后的完整 `Note`，`edit_version + 1`；原始 `content` 和引用不变。接口虽然用 `PUT`，实现语义是局部更新，调用方不能假设省略字段会被清除。

错误：笔记不存在 `404`；版本过期 `409`；无可保存修改或条目键不存在 `400`；正文空白、过长或其他字段问题 `422`。版本检查与修改在 `BEGIN IMMEDIATE` 事务内执行，避免两个请求静默覆盖。

## 8. 持久任务查询、取消与重试

### 8.1 创建任务的复用规则

转录、笔记接口调用共同的 `create_job()`：

1. 相同录音、相同任务种类有 `queued/running` 任务，参数相同则返回原任务 ID；参数不同则 `400`。
2. 没有活动的同类任务，`force: false` 且存在相同参数的成功任务时，复用成功任务 ID。
3. `force: true` 绕过成功任务复用，允许生成新版本，但不会绕过活动同类任务检查。
4. 任务先写 SQLite，再投递 RQ。两者不是跨系统原子事务；投递失败会尽量把持久任务标记失败，查询时也会核对队列状态。

### 8.2 GET /api/jobs/{job_id}

无请求体。返回完整 `Job`；不存在返回 `404`。查询会调用 `reconcile()`，核对 RQ 状态。短暂 Redis 故障不会直接抹除任务记录；缺失队列任务有时间宽限，异常状态或过期心跳可能转为 `failed`。

调用方可定时查询，直至 `succeeded/failed/cancelled`；当前不是 SSE、WebSocket 或逐字推送接口。

### 8.3 POST /api/jobs/{job_id}/cancel

无请求体。仅允许取消 `queued`，成功返回 `200 + Job`，`state/stage: cancelled`。即使 RQ 取消失败，持久取消状态也使后续 worker 调用跳过执行。

任务不存在或不在排队状态返回 `400`，不是统一的 `404`。运行中的任务不能通过本接口强制终止。

### 8.4 POST /api/jobs/{job_id}/retry

无请求体。仅允许重试 `failed`：保留任务 ID、参数和检查点，`attempt + 1`，清除 `error` 后重新排队。成功受理返回 `202 + Job`，仍应检查实际 `state`。

以下情况返回 `400`：任务不存在或非失败状态；该录音已有任何排队或运行任务；存在历史 Qwen 路径的 `reserved/unknown` 费用记录尚待核对。配置变化导致 API 任务失败时，直接重试不会更新旧参数，应重新确认当前接口并创建整理任务。

## 9. 回听标记与导出

### 9.1 POST /api/lectures/{lecture_id}/bookmarks

```json
{"position_ms":5000,"question":"这里的回滚是什么意思？"}
```

两字段必填；`position_ms` 为非负整数，不能超过录音总毫秒数；`question` 长度为 1—2000 字符。成功返回 `201 + Bookmark`。

错误：录音不存在 `404`；超出录音范围 `400`；字段校验失败 `422`。

### 9.2 DELETE /api/bookmarks/{bookmark_id}

无请求体。成功 `204`；标记不存在 `404`。

### 9.3 GET /api/lectures/{lecture_id}/export

| 查询字段 | 默认值 | 用途 |
| --- | --- | --- |
| `format` | `markdown` | 支持 `markdown/srt/json` |
| `note_id` | 省略 | Markdown 指定笔记；省略时使用创建时间最新的笔记 |
| `version_id` | 省略 | SRT 指定转录；省略时使用当前活动转录 |

| 格式 | Content-Type（可附 charset） | 内容 |
| --- | --- | --- |
| `markdown` | `text/markdown` | 笔记正文、来源时间戳、个人补充；标注用户修订和本地摘录来源 |
| `srt` | `text/plain` | 指定转录版本的字幕与时间戳 |
| `json` | `application/json` | `format/lecture/transcripts/notes/bookmarks`，其中 `format` 为 `classecho-backup-v1` |

成功带 `Content-Disposition: attachment; filename="classecho-<录音ID前8位>.<扩展名>"`，扩展名为 `md/srt/json`。`note_id` 只影响 Markdown，`version_id` 只影响 SRT；JSON 导出全部版本，录音字段中移除 `sha256`，不包含音频文件、模型、密钥或任务列表。

Markdown 按所选笔记自己的 `transcript_id` 获取引用，并不盲目使用当前转录。JSON 保留原始内容和修订记录；当前没有对应的 JSON 备份恢复导入接口。

错误：录音不存在、没有可用笔记或转录、指定版本不属于当前录音时 `404`；不支持的格式 `400`。

## 10. 本地实时转录预览

预览与第 6 节的完整录音转录是两套接口。预览状态保存在临时文件中，不生成数据库 `Transcript/Job/Note`，不能直接当作最终笔记来源。完整录音保存后仍需走上传与正式转录流程。

### 10.1 POST /api/live-transcriptions

multipart 请求：

| 字段 | 必填 | 默认值与约束 |
| --- | --- | --- |
| `file` | 是 | 完整 WAV，16kHz、单声道、PCM16，1—192000 帧，即大于 0 且不超过 12 秒 |
| `model` | 否 | `small`；后端接受 `small/turbo`，对应模型必须提前就绪 |
| `offset_ms` | 否 | `0`；整数 0—5400000，表示本片段在完整录音中的起点 |

文件最多 `384044` 字节；额外 WAV 元数据也计入这个大小上限。分片起点加时长不能超过 90 分钟。

```bash
curl -X POST "$BASE_URL/api/live-transcriptions" \
  -F "file=@$PREVIEW_WAV" -F 'model=small' -F 'offset_ms=10000'
```

`PREVIEW_WAV` 为满足上述格式的真实文件路径。成功返回 `202`：

```json
{
  "id":"88888888888888888888888888888888",
  "state":"queued",
  "created":1792483200.0,
  "model":"small",
  "offset_ms":10000,
  "duration":2.0,
  "segments":[],
  "error":null
}
```

`created` 是 Unix 秒级时间戳，不是普通数据库记录的 ISO 时间。

错误：WAV 格式或时长范围错误 `400`；模型未就绪 `409`；文件过大 `413`；参数错误 `422`；全局已有 2 个排队或运行预览 `429`；投递失败 `503`。这里的限额按当前数据目录计算，不是每个课程各两个。

### 10.2 GET /api/live-transcriptions/{identifier}

返回与创建相同的预览结构，`state` 可为 `queued/running/succeeded/failed`；成功后 `segments` 为片段数组：

- ID 为 `<预览ID>-segment_00001` 等，区别于正式转录片段。
- 起止时间已加上 `offset_ms`，调用方不要再次偏移。
- 未识别出有效语音可成功返回空数组；其他识别故障为 `failed` 和脱敏 `error`。

格式非法、目录不存在或记录无法读取返回 `404`。查询到排队或运行超过 300 秒的预览时将其标为失败。执行结束删除临时音频；超过约一小时的状态目录在后续提交预览时惰性清理，因此不保证恰好一小时立刻删除，也不保证过了一小时查询必定返回 `404`。

## 11. 最小完整调用流程

以下用内置预生成示例验证接口调用关系，不是 Whisper 或真实 AI 质量测试。需要实际运行的 API、FFmpeg/macOS 合成语音；整理任务还需要 Redis 和 worker。

### 11.1 创建示例并读取录音

```bash
BASE_URL='http://127.0.0.1:8765'
curl -sS -X POST "$BASE_URL/api/demo"
```

复制响应的 `lecture_id`，替换下方占位值：

```bash
LECTURE_ID='替换为上一步返回的lecture_id'
curl -sS "$BASE_URL/api/lectures/$LECTURE_ID"
curl -sS "$BASE_URL/api/lectures/$LECTURE_ID/transcript"
```

### 11.2 根据转录创建本地笔记任务

复制转录响应的 `id`，使用 `force: true` 明确生成新笔记版本：

```bash
TRANSCRIPT_ID='替换为转录响应的id'
curl -sS -X POST "$BASE_URL/api/lectures/$LECTURE_ID/notes" \
  -H 'Content-Type: application/json' \
  -d "{\"transcript_id\":\"$TRANSCRIPT_ID\",\"provider\":\"extractive\",\"force\":true}"
```

### 11.3 查询任务与读取结果

复制任务响应的 `id`，间隔查询直到终态：

```bash
JOB_ID='替换为任务响应的id'
curl -sS "$BASE_URL/api/jobs/$JOB_ID"
```

确认 `state: succeeded` 后再获取笔记：

```bash
curl -sS "$BASE_URL/api/lectures/$LECTURE_ID/notes"
```

### 11.4 导出

以下命令在当前目录创建或覆盖同名导出文件：

```bash
curl -fS "$BASE_URL/api/lectures/$LECTURE_ID/export?format=markdown" -o classecho-demo.md
curl -fS "$BASE_URL/api/lectures/$LECTURE_ID/export?format=srt" -o classecho-demo.srt
curl -fS "$BASE_URL/api/lectures/$LECTURE_ID/export?format=json" -o classecho-demo.json
```

真实转录的调用顺序为：创建课程 → 上传文件 → 创建转录任务 → 查询任务 → 读取转录 → 创建笔记任务 → 查询任务 → 读取笔记。不要把 `/api/demo` 的预生成结果说成模型现场识别。

## 12. 答辩时如何解释这些接口

| 常见追问 | 对应实现与回答依据 |
| --- | --- |
| 为什么返回 202 而不是直接返回笔记？ | 识别和整理耗时，接口返回任务，RQ worker 独立执行；轮询获取最终状态 |
| HTTP 200 是否表示模型运行成功？ | 查询任务成功只是查询成功，业务结果必须看 `state/error` |
| 为什么同时用 SQLite 和 Redis？ | SQLite 保存业务与持久任务，Redis/RQ 承担队列调度；不是两套相同的业务存储 |
| 重复点击会重复调用模型吗？ | 同类任务按参数复用，成功任务可用 `force` 重做；外部调用与检查点落盘之间仍有中断窗口 |
| 为什么修订需要版本字段？ | 转录用 `base_version_id`，笔记用 `edit_version`；事务内比较，过期写入返回 409 |
| 为什么旧笔记还能回听正确原文？ | 笔记固定引用来源转录版本，条目保存来源片段 ID，片段携带时间戳 |
| AI 编造引用如何处理？ | Pydantic 检查结构，再检查引用是否存在；无法仅凭此证明语义正确 |
| API Key 会返回给浏览器吗？ | 公开配置只返回是否已配置；磁盘文件仍是 0600 权限的明文，需要保护 |
| 项目是不是完整的公网多用户服务？ | 当前是本机应用，没有账号和用户权限隔离，不能宣称已具备公网多用户能力 |
| 实时预览是不是流式最终识别？ | 不是；短音频分片排队后轮询结果，完整录音另行正式转录 |

## 13. 代码与验证索引

- [主路由与本机来源检查](../backend/app/main.py)
- [请求模型、结构及引用校验](../backend/app/schemas.py)
- [数据库字段与会话](../backend/app/db.py)
- [持久任务、复用、重试与队列核对](../backend/app/jobs.py)
- [Worker 入口](../backend/app/worker.py)
- [媒体格式与规范化](../backend/app/media.py)
- [本地识别与模型版本](../backend/app/asr.py)
- [笔记分块、接口调用及结果合并](../backend/app/notes.py)
- [AI 配置规范化与密钥保存](../backend/app/notes_api.py)
- [临时实时预览](../backend/app/live_asr.py)
- [导出实现](../backend/app/exports.py)
- [API 工作流测试](../backend/tests/test_workflow.py)、[任务测试](../backend/tests/test_jobs.py)、[笔记修订测试](../backend/tests/test_note_edits.py)、[模拟 AI 接口测试](../backend/tests/test_api_notes.py)、[实时预览测试](../backend/tests/test_live_asr.py)

自动测试中的模型和外部 AI 响应使用替身验证业务逻辑，不代表真实课堂准确率或真实外部服务兼容性。运行验证命令：

```bash
uv run --locked python -m pytest backend/tests -q
```
