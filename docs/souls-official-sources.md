# V3：五款魂系游戏官方来源研究与捕获接口

## 研究范围与证据时间

实际使用 `web_search`、`web_fetch`，再通过 Python/urllib 实际 HTTP 捕获保存样板。首批样板实际捕获于 **2026-10-01 09:33 UTC**；这是运行机器当前 UTC，不是发布日期。产品介绍没有文章发布日期，因此 `published_at=null`、`patch=null`。不声称最新补丁、销量、攻略数值阈值或全平台全历史覆盖。

采集模块使用 urllib 标准库和 BeautifulSoup，保留实际来源、原文、日期与哈希。BeautifulSoup在当前环境已安装；项目依赖已显式声明，方便新环境安装。

## 游戏、edition 与 DLC 标签（每项以实际官方证据为准）

| game_id | 接口 edition | 官方 Steam 身份与适用范围 |
|---|---|---|
| elden-ring | standard | [1245620：ELDEN RING](https://store.steampowered.com/api/appdetails?appids=1245620&l=english)；基础游戏与 Shadow of the Erdtree Edition / Deluxe Edition 的产品组合同列在这一游戏下，不另造游戏 ID。 |
| nightreign | standard | [2622380：ELDEN RING NIGHTREIGN](https://store.steampowered.com/api/appdetails?appids=2622380&l=english) 明说 standalone adventure；**不是 ER 的 DLC**。Deluxe 包含 The Forsaken Hollows 与数字美术/迷你原声。 |
| dark-souls-1 | remastered / original | [570940：Remastered](https://store.steampowered.com/app/570940/?l=english) 与 [211420：Prepare To Die Edition](https://store.steampowered.com/api/appdetails?appids=211420&l=english&filters=basic) 是不同 Steam app；原版当前 appdetails 历史文本可用，不据此断言其在线功能仍活跃。模块默认公告只启用 Remastered。 |
| dark-souls-2 | scholar / standard | [335300：Scholar](https://store.steampowered.com/api/appdetails?appids=335300&l=english) 是 DX11，正文明确敌人分布改动；[236430：标准 app](https://store.steampowered.com/api/appdetails?appids=236430&l=english) 是 DX9。236430 的购买包名称也会写 Scholar，**不能仅用购买标题覆盖 app/edition 区分**。 |
| dark-souls-3 | standard | [374320：DARK SOULS III](https://store.steampowered.com/api/appdetails?appids=374320&l=english)；[美国区购买组合](https://store.steampowered.com/api/appdetails?appids=374320&l=english&cc=us&filters=packages,package_groups) 列 standard / Deluxe；默认地区接口列 Fire Fades Edition。不同购买组合不意味着不同游戏 app 或独立补丁线。 |

### 实际玩法 DLC 标识

下面的 kebab-case ID 是工作台的语义标签，不是官方自己发布的 ID；数字是已实际读取的 Steam app id。`requires_dlc` 不因为文章提及 DLC 就自动添加：补丁常同时修改基础与 DLC 内容，按整篇设为 DLC 必需会错误屏蔽基础游戏信息。模块额外给 `mentioned_dlc`；需要的具体 DLC 条件保留在原文。

- ER `shadow-of-the-erdtree` → [2778580，Shadow of the Erdtree](https://store.steampowered.com/api/appdetails?appids=2778580&l=english&filters=basic)，API fullgame=1245620。
- ER `tarnished-pack` → [3655690，Tarnished Pack](https://store.steampowered.com/api/appdetails?appids=3655690&l=english&filters=basic)，实际接口已列此包及新增初始职业/装备/坐骑外观内容，不能按旧记忆忽略。 [2778590 Premium Bundle](https://store.steampowered.com/api/appdetails?appids=2778590&l=english&filters=basic) 是 Erdtree 加美术/原声组合，不是另一片玩法区域。
- Nightreign `the-forsaken-hollows` → [3531720](https://store.steampowered.com/api/appdetails?appids=3531720&l=english&filters=basic)，API fullgame=2622380，正文明确也包含在 Deluxe。
- DS1 `artorias-of-the-abyss`：Remastered 内含，无需另买；[Steam正文](https://store.steampowered.com/app/570940/?l=english) 和 [FromSoftware 2018-01-12 原始新闻稿](https://www.fromsoftware.jp/jp/pressrelease/20180112_darksoulsremastered_releasedate.html) 均明确。新闻稿也明确这是对 2011 原版的 remaster；不要把原版与重制版联机/画面/攻略细节自动视为相同。
- DS2 `crown-of-the-sunken-king` → [271942](https://store.steampowered.com/api/appdetails?appids=271942&l=english&filters=basic)；`crown-of-the-old-iron-king` → [271943](https://store.steampowered.com/api/appdetails?appids=271943&l=english&filters=basic)；`crown-of-the-ivory-king` → [271944](https://store.steampowered.com/api/appdetails?appids=271944&l=english&filters=basic)。这三个独立 DLC app 的 fullgame 均为236430；Scholar 正文说包含已发布内容，不能据其 DLC app归属误标 Scholar 快照为 standard。[355700](https://store.steampowered.com/api/appdetails?appids=355700&l=english&filters=basic) 实际名为 `Upgrade to DX11 (no content)`，不当作新增玩法 DLC。
- DS3 `ashes-of-ariandel` → [506970](https://store.steampowered.com/api/appdetails?appids=506970&l=english&filters=basic)；`the-ringed-city` → [506971](https://store.steampowered.com/api/appdetails?appids=506971&l=english&filters=basic)。[442010 Season Pass](https://store.steampowered.com/api/appdetails?appids=442010&l=english&filters=basic) 提供两个 DLC，是购买组合，不是第三个玩法 DLC。

## 实际可用公告渠道与可信度陷阱

1. **ISteamNews 官方 JSON**：
   - [ER filtered feed](https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=1245620&count=10&maxlength=0&feeds=steam_community_announcements&format=json)
   - [Nightreign filtered feed](https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=2622380&count=2&maxlength=0&feeds=steam_community_announcements&format=json)
   - [DS1 Remastered](https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=570940&count=10&maxlength=0&feeds=steam_community_announcements&format=json)
   - [DS2 Scholar](https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=335300&count=10&maxlength=0&feeds=steam_community_announcements&format=json) / [standard](https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=236430&count=10&maxlength=0&feeds=steam_community_announcements&format=json)
   - [DS3](https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=374320&count=10&maxlength=0&feeds=steam_community_announcements&format=json)
2. [ER 未过滤 feed](https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=1245620&count=3&maxlength=0&format=json) 实测最新返回 PlayGround.ru 外部转载，`feed_type=0`。**Steam host 不等于官方作者**。模块同时检查 `appnews.appid`、每条 `appid`、`feedname=steam_community_announcements`、`feed_type=1`、公告 URL；外部 partner/社区转载排除。真正 publisher announcement 的 `is_external_url` 也可能为 true，不能据这个字段盲排。
3. 即 publisher feed 也会推广别的游戏：[DS3 feed](https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/?appid=374320&count=10&maxlength=0&feeds=steam_community_announcements&format=json) 实测最新条目包含 NIGHTREIGN 预购/公开预告，不能当作 DS3 情报。模块排除标题明确属于另外四款目标游戏的跨推广；中性公告仍保留 app来源身份，不保证已覆盖全部跨推广情形。
4. [DS1 官方商店新闻 RSS](https://store.steampowered.com/feeds/news/app/570940/?l=english) 实测可用，含2022在线恢复公告与2018发行公告，也有 ER 跨推广。RSS 的 store event view ID 与 ISteamNews 的 gid 不承诺可互换。模块当前实际实现 JSON 渠道，不隐式降级成 RSS 或社区。
5. [Bandai Nightreign patch 1.03.1](https://en.bandainamcoent.eu/elden-ring/news/elden-ring-nightreign-patch-notes-version-1031) 实测 HTTP200，article 主文与 article header time 可解析，发布日期2025-12-17；正文明确 App Ver.1.03.1 / Regulation Ver.1.03.2。Steam filtered feed 另有标题明确 **1.03.2** 的公告；这是实际抓到的条目，不是“最新补丁”承诺。两种版本号不应混为一个字段。
6. [FromSoftware产品详情](https://www.fromsoftware.jp/ww/detail.html?csm=099) 的核心产品文字依赖动态加载，web_fetch 获得框架空壳；没有把它作为抓取样板。换用了实际可读取的 FromSoftware 原始新闻稿与 Steam 第一方正文。
7. 此轮已测试渠道未遇403；DS2产品 HTML 有 agecheck，使用官方 appdetails 中的 publisher正文作为明确替代，`source_url` 指向实际 JSON 请求。将来 HTTP403 会抛包含具体 URL 的 SourceError，不偷偷换社区来源。

## 小 interface：主线程对接契约

模块只提供来源和捕获，不创建 HTTP 路由、不落 store SQL、不自动索引。

```python
sources_for(game_id)                         # source descriptors
fetch_updates(game_id, source_id=None, limit=10)  # actual captures for preview
fetch_article(game_id, url, *, edition=None)     # one selected capture
```

- 来源：`id,game_id,title,url,kind(steam_news|publisher_page),tier,app_id?,edition,notes`。`sources_for` 每次返回副本。
- 文章：`external_id,game_id,title,url,published_at,captured_at,patch,edition,content,content_sha256,source_id,source_tier,source_kind(patch_notes|reference),provenance(verified_capture|feed_capture),requires_dlc`。另含 `source_url,raw_content,mentioned_dlc,edition_notes`；hash 是 UTF-8 清理后原文content的 SHA256，raw保留被捕获的主文HTML/BBCode。
- 默认 `fetch_updates` 只选 Steam公告源；选一个 publisher_page source_id 则捕获该单页reference。limit=1..100，各feed扫描有界最多100条，返回按published倒序的最多limit条。空列表是合法结果；错误抛 `SourceError`，上层可逐source包装为 `{items,errors}`。
- 无通用域名白名单导入：Steam产品用已注册app+返回app/name校验；Bandai使用已实际验证的**具体 URL**并核验 article h1 游戏身份；未注册任意官方域名链接也拒绝。Steam单篇选取必须在该游戏近100条 genuine feed里找到对应gid与实际URL，或可匹配app/gid的news alias；旧公告或RSS eventid不能保证接受。UI应使用返回的 `item.url`。
- SteamBBCode去格式保留文字与anchor URL，HTML去script/style/nav/header/footer/aside/form/video/iframe并只提取明确正文。产品正文是reference，不以营销产品介绍冒充patch；未知patch保持null。补丁版本仅识别显式标题patch/hotfix/update或正文App Ver，不靠日期邻接推断。
- DS2标准feed出现Scholar标题或明确跨edition标题时，edition置null并附edition_notes，不能盲认一致。其余中性公告edition仅表示app渠道，不保证每行都适用该edition，导入前用户审核。
- 请求20秒超时、每响应4MiB上限；失败保留源URL。模块不进行wiki批量crawl。

## 可真实索引的样板

每款目录 `knowledge/souls/{game_id}/` 有 `official-reference.md` 和 `manifest.json`；manifest形状为 `{schema_version:1,game_id,articles:[完整payload + path]}`。五份primary正文是实际官方产品文字；DS1用remastered、DS2用scholar。产品release_date没有冒充发布日期，全部显式null。Nightreign额外保存实际Bandai历史patch主文，作为真实patch捕获示例（不要求另四款伪造patch）。CLI应使用manifest中的content/metadata或对应md正文，避免将metadata JSON当作攻略正文。

编译与捕获：完成一次内存compile（不生成额外pycache），五个产品捕获以及六条feed渠道/一个Bandai article实际请求成功；当前补丁展示与引用必须带edition、published/captured、source URL与可信等级，不能展示为最新性全覆盖。
