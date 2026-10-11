# 你手动把 Production Scheduling Optimization System 上传到 GitHub

项目全名：**Production Scheduling Optimization System**。
它提供交互式 Web 排程界面、Power BI 数据导出，并支持默认关闭的可选 AI Copilot 扩展。
创建仓库时，Description 可以填写：

> Verified production scheduling with a Web dashboard, Power BI data exports and an optional AI copilot extension.

源码已从 `Independent Projects` 迁移到独立的本地项目目录，运行数据库和已有排程也已保留。
当前项目目录是 `C:\Users\12418\Documents\ChatGPT\Project scheduling Optimization System`。
本次迁移没有执行 Git 提交、推送或发布；现有 `.git` 保持不变。

## 1. 确认目录

在 PowerShell 中输入：

```powershell
Set-Location 'C:\Users\12418\Documents\ChatGPT\Project scheduling Optimization System'
Get-Location
git --version
git status
```

此目录已经有 `.git`，因此不需要再次初始化。下面第二节中的 `git init` 仅适用于尚未初始化的目录。
README.md、backend、frontend、docs 应直接位于此目录。数据库、运行环境和本地备份被 `.gitignore` 排除。

## 2. 建立本地版本记录

以下命令在上面的独立项目目录执行。

```powershell
git init -b main
git status
git add .
git diff --cached --stat
git status
```

`init` 建立版本库，`status` 查看状态，`add` 放进待提交区，`diff --cached --stat` 查看将记录哪些文件。
包内的 `.gitignore` 会排除 .env、运行数据库、.venv 和 node_modules。待提交列表应该是源码与文档。
确认列表后，你自己运行：

```powershell
git commit -m "Build production scheduling optimization system"
git log -1 --oneline
```

`commit` 把这批文件保存为一个本地版本；此时还没有上传。
如果显示 `Author identity unknown`，在这个目录设置你自己的名字和 GitHub 邮箱，再重试 commit：

```powershell
git config --local user.name '你的名字'
git config --local user.email '你的 GitHub 邮箱或 GitHub 提供的 noreply 邮箱'
```

## 3. 在 GitHub 网站建空仓库

登录 GitHub，点 **New repository**，填写 `production-scheduling-optimization-system`。
第一次练习建议选 **Private**。保持空仓库：不勾选添加 README、.gitignore、license，
因为源码包已经有这些文件。点 Create repository，然后复制它显示的 HTTPS 地址。

## 4. 连接并上传

把下方示例里的 `YOUR_USERNAME` 换成你复制的真实仓库地址：

```powershell
git remote add origin https://github.com/YOUR_USERNAME/production-scheduling-optimization-system.git
git remote -v
git push -u origin main
```

`remote` 指定远程仓库，`push` 上传你已提交的版本。如果出现登录窗口，按 Git Credential Manager
的浏览器流程登录。不要把密码或 token 发给聊天；只需要分享去除凭据后的错误信息即可诊断。

## 5. 确认上传成功

刷新 GitHub 仓库页，应看到 README、backend、frontend、docs、.github/workflows/opspilot.yml。
提交列表应与 `git log -1` 的提交一致。打开 **Actions** 看 Windows、Linux、浏览器和 Docker
检查；这些检查首次在 GitHub 上运行，不能把已配置当作已经通过。

## 6. 以后更新

在你选择继续维护的这个目录中修改文件，然后：

```powershell
git status
git add 你改过的文件路径
git diff --cached
git commit -m "Explain the specific change"
git push
```

此独立目录现在是排程系统的主要工程目录，后续修改和 Git 操作均在这里完成。

上述步骤依据 [GitHub 官方 Windows 导入指南](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github?platform=windows)。
本项目的打包脚本只准备文件，没有执行这些 Git 或 GitHub 操作。
