# 本 fork 的定制说明

上游：[kiddin9/Kwrt](https://github.com/kiddin9/Kwrt)，分支 `25.12`。目标设备：N4100-4L（x86_64）。

## 与上游的差异
- `devices/x86_64/.config`：追加现网路由器用到的插件（见文件末尾注释）。
- `devices/x86_64/settings.ini`：关闭 WeTransfer 上传。
- `.github/workflows/Openwrt-AutoBuild.yml`
  - `secrets.TOKEN_KIDDIN9` 全部改为内置 `secrets.GITHUB_TOKEN`，**不需要自建 PAT**；已声明 `permissions`。
  - 删除「向上游 op-packages 发 dispatch」和「部署到作者服务器」两个步骤。
  - 第三方 action 固定到具体提交；`actions/*` 固定到 v4。
- `.github/workflows/repo-dispatcher.yml`：重写，只编译指定的一个 target（原版一次触发 25 个）。

## 触发编译
```
gh workflow run "Repo Dispatcher" -f target=x86_64
# 或绕过：
gh api repos/<owner>/Kwrt/dispatches -f event_type=x86_64 -f 'client_payload[target]=x86_64'
```
产物在 Actions 运行页的 Artifacts 里。

## 注意
- 包源仍是上游作者的 `kiddin9/op-packages`（`devices/common/diy.sh`），构建内容部分取决于它。
- 与上游合并时，上面两个工作流文件会冲突，保留本 fork 的版本即可。
- 现网的自装脚本、`/work`、`/etc/config` 含密钥，**不放进本仓库**（本仓库公开），刷机后从私有备份还原。
