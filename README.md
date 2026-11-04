# tiktok-shop-toolkit

公司内部 TikTok Shop 研究工具库：公开抓取产品 / 带货视频 / 评价，整理后写入「提示词表」类 Google Sheet。

## 用途

- 按市场（默认 US）与关键词或商品 URL 抓取 TikTok Shop 公开产品数据
- 抓取商品关联热门带货视频（链接、播放量、作者、封面）
- 抓取公开评价并归纳好评 / 差评主题
- 将结果写入约定表格列（不覆盖无关列）
- 备份可复用的 Apify Actor 参数与本地整理脚本

## 硬性约束

- **不下单、不改店铺、不代付**；只用公开页 / Apify 公开 Actor
- 注意 **IP / 地区 / 限流**：失败如实记；分批跑，控制 `maxItems` / `maxReviews`
- **密钥不进仓库**：只用 `.env`（见 `.env.example`）；大数据与原始 dump 放本地 `data/raw/`（已 gitignore）
- Sheets **无法表内可播嵌 TikTok 视频**时：写可点开播链接 + 封面（Drive / CDN）；单元格内嵌图需浏览器登录手动 Insert

## 目录

```
scripts/          # 可运行脚本（Apify 调用、整理、写表示例）
docs/             # Actor 说明、提示词表列约定
examples/         # 小样例 JSON（无密钥、无大批量数据）
data/             # 本地运行输出（默认忽略大文件）
```

## 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # 填入 APIFY_TOKEN
```

跑占位演示（不调网络）：

```bash
python scripts/demo_local.py
```

接 Apify（需 token）示例：

```bash
# 产品详情 + related videos（US）
python scripts/apify_product_details.py --urls-file examples/sample_product_urls.txt --out data/runs/products.json

# 评价
python scripts/apify_reviews.py --urls-file examples/sample_product_urls.txt --max-reviews 40 --out data/runs/reviews.json
```

写表请用已连接的 Google Sheets 工具或公司 Bot；本仓库脚本默认只产出 JSON，避免把表格凭据写进代码。

## 常用 Apify Actor（经验）

| 场景 | Actor | 备注 |
| --- | --- | --- |
| 关键词 / 畅销搜索 | `pro100chok/tiktok-shop-scraper-usage` | `scrapeType=search`，`sortBy=best_sellers`，`region=us` |
| 产品详情 | 同上 `scrapeType=product` | 含图；视频字段因商品而异 |
| 关联带货视频 | `unseenuser/TikTok-Shop-Scraper` | `mode=product_details`，`getRelatedVideos=true`；免费档可能每 run 限 5 条，可分批 |
| 评价 | `pro100chok/...` `scrapeType=reviews` | `recommended` 偏正面；差评少时备注「暂无」 |

## 提示词表约定（参考）

目标表示例：`提示词表`（TikTok Shop US 包包线）。列约定见 `docs/prompt-sheet-columns.md`。写表时 **不要改动无关列**。

## 备份说明

本仓库骨架对应公司 Bot 技能 `tiktok-shop-scraper-workflow`。运行产生的大批量 JSON / 图片请本地备份或 Drive，勿提交。

## License

Private company tooling. Not for public redistribution.
