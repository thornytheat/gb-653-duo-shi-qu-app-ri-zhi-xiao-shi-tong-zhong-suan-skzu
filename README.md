# 多时区应用日志小时桶重算

        面向一线复核人员的单服务数据工作台。样例数据随仓库提供，结论保留行号、原因码和原值。

        ## 业务模块

        - M1 日志采信：`/api/logs/import`
- M2 时间解析：`/api/time/normalize`
- M3 事件去重：`/api/events/dedupe`
- M4 小时分桶：`/api/buckets/rebuild`
- M5 迟到修订：`/api/watermark/advance`
- M6 批次对账：`/api/export/buckets.csv`

        ## 核心规则

        事件先归一到 UTC，DST 重叠时保留 fold；小时桶右端开，水位只能前进且迟到事件仍进入修订。

        同一 `request_id` 出现一成一败两条日志时，该请求记为**待核对**（`OUTCOME_CONFLICT`），
        不计入已确认错误数；小时分桶与导出都分别给出“已确认错误”和“待核对”两列。
        待核对请求的两条原行随批次留档，可凭 `run_id` + `request_id` 查回，不丢记录。
        同一批次摘要重跑复用原 `run_id`，结果、原始行与待核对证据都只在首次入账。

        ## 启动

        ```bash
        docker compose up --build
        ```

        浏览器访问 `http://localhost:18212`。运行测试：

        ```bash
        docker compose exec -T app pytest -q
        ```

        ## 样例流程

        依次运行六个模块；最后在批次页复核输入、有效、隔离与输出合计。同一输入摘要重复执行时复用原 `run_id`。

        ## 待核对请求

        - `POST /api/buckets/rebuild` 返回 `errors`（已确认错误）与 `pending_count`（待核对请求数），
          每行小时桶带 `confirmed` / `pending` 两列。
        - `GET /api/buckets/pending/{run_id}/{request_id}` 查回分桶批次里的两条原行。
        - `GET /api/logs/pending/{run_id}/{request_id}` 查回导入批次里的两条原行。
        - `GET /api/runs/pending/{run_id}` 列出某批次的全部待核对请求。
        - 导出 CSV 增加 `confirmed`、`pending` 列，交班时可直接区分两者。

        ## 已知不覆盖

        不处理加密文件与需要外部密钥的对象；不连接真实生产存储。
