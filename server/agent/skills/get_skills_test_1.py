import requests
import base64
from typing import List, Dict
import yaml

class AgentSkillsMarketplace:
    def __init__(self, github_token: str = None):
        self.token = github_token
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            **({"Authorization": f"token {github_token}"} if github_token else {})
        }
    
    def fetch_repo_skills(self, owner: str, repo: str, path: str = "skills") -> List[Dict]:
        """
        从 GitHub 仓库获取技能列表
        例如：anthropics/skills 或 其他社区仓库
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/main?recursive=1"
        response = requests.get(url, headers=self.headers)
        data = response.json()
        
        skills = []
        for item in data.get("tree", []):
            # 找到所有 SKILL.md 文件
            if item["path"].endswith("SKILL.md") and path in item["path"]:
                skill_folder = item["path"].split("/")[-2]
                skills.append({
                    "name": skill_folder,
                    "path": item["path"],
                    "url": f"https://raw.githubusercontent.com/{owner}/{repo}/main/{item['path']}",
                    "sha": item["sha"]
                })
        return skills
    
    def get_skill_detail(self, raw_url: str) -> Dict:
        """获取单个技能的详细内容（SKILL.md）"""
        response = requests.get(raw_url)
        content = response.text
        
        # 解析 YAML frontmatter
        if content.startswith("---"):
            _, frontmatter, body = content.split("---", 2)
            metadata = yaml.safe_load(frontmatter)
        else:
            metadata = {}
            body = content
        
        return {
            "metadata": metadata,
            "content": body,
            "raw_url": raw_url
        }
    
    def download_skill_files(self, owner: str, repo: str, skill_path: str) -> Dict:
        """
        下载技能文件夹下所有文件
        返回文件结构，可用于前端打包下载
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{skill_path}"
        response = requests.get(url, headers=self.headers)
        files = response.json()
        
        skill_package = {
            "name": skill_path.split("/")[-1],
            "files": []
        }
        
        for file in files:
            if file["type"] == "file":
                file_content = requests.get(file["download_url"]).text
                skill_package["files"].append({
                    "filename": file["name"],
                    "content": file_content,
                    "path": file["path"]
                })
        
        return skill_package

# 使用示例
market = AgentSkillsMarketplace(github_token="your_token")

# 1. 获取 Anthropic 官方技能列表
skills = market.fetch_repo_skills("anthropics", "skills", "skills")
print(f"找到 {len(skills)} 个技能")

# 2. 获取技能详情
if skills:
    detail = market.get_skill_detail(skills[0]["url"])
    print(f"技能名称: {detail['metadata'].get('name')}")
    print(f"描述: {detail['metadata'].get('description')}")

# 3. 下载完整技能包（用于前端提供给用户下载）
skill_package = market.download_skill_files("anthropics", "skills", "skills/development")