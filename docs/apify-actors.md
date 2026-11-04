# Apify Actors 速查

## 产品搜索 / 详情 / 评价

- **Actor**: `pro100chok/tiktok-shop-scraper-usage`
- 市场：`region`（us/sg/…）、`scrapeType`（search|product|reviews|…）
- 搜索：`searchKeywords`、`sortBy=best_sellers`、`maxItems`
- 详情：`productUrls`
- 评价：`reviewProductUrls`、`maxReviews`、`reviewsSortBy`

## 关联带货视频

- **Actor**: `unseenuser/TikTok-Shop-Scraper`
- `mode=product_details`，`region=US`，`productUrls`，`getRelatedVideos=true`
- 注意免费档每 run 结果上限；十款可拆两批各 5

## 限流与费用

- 控制 `maxItems` / `maxReviews`；中途 ABORT 时记录已完成款并补跑
- Token 只放环境变量，不要写进脚本或提交
