# 每日论文精读 · Streamlit

Streamlit Community Cloud：仓库选择 research-daily-reading，分支 main，入口 app.py。

本程序只展示已发布的精读报告，不启动邮件发送或模型生成。
reading-content.zip 保存报告和页面样式，reading-graphics-*.zip 保存原始配图。启动时自动展开，首页展示今日精读；往期目录支持类型与方向筛选，点击进入独立单篇阅读页。
支持配图轮换与自动配色，不提供阅读页下载功能。
site-publication.json 持久记录正文更新到网站的日期，刷新或仅修改界面不会重置日期。

新报告需由独立任务生成后更新 reading-content.zip，再提交到仓库；Streamlit 随仓库更新部署。网页本身不提供准点定时生成服务。
