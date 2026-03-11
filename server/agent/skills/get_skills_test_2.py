import base64
import yaml
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
import io
import zipfile

app = FastAPI(title="Agent Skills Market API")

# 你的 GitHub Token (用于提高 API 限流额度)
GITHUB_TOKEN = "your_github_token_here"
HEADERS = {
    "Accept": "application/vnd.github.v3+json",
    "Authorization": f"Bearer {GITHUB_TOKEN}"
}

class SkillMeta(BaseModel):
    name: str
    description: str
    author: Optional[str] = None
    version: Optional[str] = None
    repo_url: str
    download_url: str

@app.get("/api/skills/search", response_model=List[SkillMeta])
async def search_skills(query: str = "agent-skills"):
    """
    方案A：通过 GitHub Topic 或关键字搜索公开技能
    在实际生产中，建议你做一层 Redis 缓存或者将爬取的数据存入 PostgreSQL。
    """
    search_url = f"https://api.github.com/search/repositories?q=topic:agent-skills+{query}&per_page=10"
    
    async with httpx.AsyncClient() as client:
        response = await client.get(search_url, headers=HEADERS)
        if response.status_code != 200:
            raise HTTPException(status_code=response.status_code, detail="Failed to fetch from GitHub")
        
        repos = response.json().get("items", [])
        skills_list =[]
        
        # 遍历仓库，尝试读取 SKILL.md 来解析 YAML 元数据
        for repo in repos:
            owner = repo["owner"]["login"]
            repo_name = repo["name"]
            
            # 请求 SKILL.md 文件
            content_url = f"https://api.github.com/repos/{owner}/{repo_name}/contents/SKILL.md"
            content_res = await client.get(content_url, headers=HEADERS)
            
            if content_res.status_code == 200:
                file_data = content_res.json()
                # GitHub 返回的是 Base64 编码的文件内容
                raw_markdown = base64.b64decode(file_data["content"]).decode("utf-8")
                
                # 提取 YAML Frontmatter (--- 之间的内容)
                metadata = {}
                if raw_markdown.startswith("---"):
                    parts = raw_markdown.split("---", 2)
                    if len(parts) >= 3:
                        try:
                            metadata = yaml.safe_load(parts[1]) or {}
                        except Exception:
                            pass
                
                skills_list.append(SkillMeta(
                    name=metadata.get("name", repo_name),
                    description=metadata.get("description", repo["description"] or ""),
                    author=metadata.get("author", owner),
                    version=str(metadata.get("version", "1.0")),
                    repo_url=repo["html_url"],
                    # 提供一个统一的后端下载路由
                    download_url=f"/api/skills/download?owner={owner}&repo={repo_name}"
                ))
                
        return skills_list

@app.get("/api/skills/download")
async def download_skill(owner: str, repo: str, branch: str = "main"):
    """
    将目标技能从 GitHub 拉取并打包为 Zip 格式供用户下载。
    客户端收到后，应将其解压至 ~/.claude/skills 或对应框架的 skills 目录。
    """
    archive_url = f"https://api.github.com/repos/{owner}/{repo}/zipball/{branch}"
    
    async def iter_file():
        async with httpx.AsyncClient() as client:
            async with client.stream("GET", archive_url, headers=HEADERS, follow_redirects=True) as response:
                if response.status_code != 200:
                    raise HTTPException(status_code=404, detail="Skill archive not found")
                async for chunk in response.aiter_bytes():
                    yield chunk

    return StreamingResponse(
        iter_file(), 
        media_type="application/zip", 
        headers={"Content-Disposition": f"attachment; filename={repo}-skill.zip"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)