import os
import httpx
from typing import Dict, List, Optional
from urllib.parse import urlparse
import circuitbreaker
from dotenv import load_dotenv
from app.utils.logging import logger

# Load environment variables
load_dotenv()

class GitHubService:
    def __init__(self):
        self.base_url = "https://api.github.com"
        self.client_id = os.getenv('GITHUB_CLIENT_ID')
        self.client_secret = os.getenv('GITHUB_CLIENT_SECRET')
        self.redirect_uri = os.getenv('GITHUB_OAUTH_REDIRECT_URI')
        
        self.client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
        )
    
    async def exchange_oauth_code(self, code: str) -> Optional[str]:
        """Exchange OAuth code for access token."""
        try:
            response = await self.client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "code": code,
                },
                headers={"Accept": "application/json"}
            )
            response.raise_for_status()
            data = response.json()
            return data.get("access_token")
            
        except Exception as e:
            logger.error("OAuth token exchange failed", error=str(e))
            return None
    
    async def get_user_info(self, token: str) -> Optional[Dict]:
        """Get GitHub user information."""
        try:
            return await self._get_user_info_impl(token)
        except Exception as e:
            logger.error("Failed to get user info", error=str(e))
            return None
    
    @circuitbreaker.circuit(failure_threshold=5, recovery_timeout=30, expected_exception=Exception)
    async def _get_user_info_impl(self, token: str) -> Optional[Dict]:
        """Implementation of get user info."""
        try:
            response = await self.client.get(
                f"{self.base_url}/user",
                headers={"Authorization": f"token {token}"}
            )
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error("Failed to get user info", error=str(e))
            return None
    
    async def get_pr_details(self, repo: str, pr_number: int, token: str) -> Optional[Dict]:
        """Get PR details from GitHub."""
        try:
            return await self._get_pr_details_impl(repo, pr_number, token)
        except Exception as e:
            import traceback
            tb_str = traceback.format_exc()
            logger.error(f"get_pr_details FULL TRACEBACK: {tb_str}")
            logger.error("Failed to get PR details", repo=repo, pr=pr_number, error=str(e))
            return None
    
    @circuitbreaker.circuit(failure_threshold=5, recovery_timeout=30, expected_exception=Exception)
    async def _get_pr_details_impl(self, repo: str, pr_number: int, token: str) -> Optional[Dict]:
        """Implementation of get PR details."""
        try:
            response = await self.client.get(
                f"{self.base_url}/repos/{repo}/pulls/{pr_number}",
                headers={"Authorization": f"token {token}"}
            )
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error("Failed to get PR details", repo=repo, pr=pr_number, error=str(e))
            return None
    
    async def get_pr_files(self, repo: str, pr_number: int, token: str) -> List[Dict]:
        """Get files changed in PR."""
        try:
            return await self._get_pr_files_impl(repo, pr_number, token)
        except Exception as e:
            logger.error("Failed to get PR files", repo=repo, pr=pr_number, error=str(e))
            return []
    
    @circuitbreaker.circuit(failure_threshold=5, recovery_timeout=30, expected_exception=Exception)
    async def _get_pr_files_impl(self, repo: str, pr_number: int, token: str) -> List[Dict]:
        """Implementation of get PR files."""
        try:
            response = await self.client.get(
                f"{self.base_url}/repos/{repo}/pulls/{pr_number}/files",
                headers={"Authorization": f"token {token}"}
            )
            response.raise_for_status()
            return response.json()
            
        except Exception as e:
            logger.error("Failed to get PR files", repo=repo, pr=pr_number, error=str(e))
            return []
    
    async def get_file_content(self, repo: str, path: str, ref: str, token: str) -> Optional[str]:
        """Get file content from GitHub."""
        try:
            return await self._get_file_content_impl(repo, path, ref, token)
        except Exception as e:
            logger.error("Failed to get file content", repo=repo, path=path, error=str(e))
            return None
    
    @circuitbreaker.circuit(failure_threshold=5, recovery_timeout=30, expected_exception=Exception)
    async def _get_file_content_impl(self, repo: str, path: str, ref: str, token: str) -> Optional[str]:
        """Implementation of get file content."""
        try:
            response = await self.client.get(
                f"{self.base_url}/repos/{repo}/contents/{path}",
                params={"ref": ref},
                headers={"Authorization": f"token {token}"}
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("encoding") == "base64":
                import base64
                return base64.b64decode(data["content"]).decode("utf-8")
            
            return data.get("content", "")
            
        except Exception as e:
            logger.error("Failed to get file content", repo=repo, path=path, error=str(e))
            return None
    
    def parse_repo_url(self, repo_url: str) -> Optional[str]:
        """Parse repository URL to get owner/repo format."""
        try:
            parsed = urlparse(repo_url)
            path = parsed.path.strip("/")
            
            if path.endswith(".git"):
                path = path[:-4]
            
            parts = path.split("/")
            if len(parts) >= 2:
                return f"{parts[0]}/{parts[1]}"
            
            return None
            
        except Exception as e:
            logger.error("Failed to parse repo URL", url=repo_url, error=str(e))
            return None
    
    async def check_repo_access(self, repo: str, token: str) -> bool:
        """Check if user has access to repository."""
        try:
            response = await self.client.get(
                f"{self.base_url}/repos/{repo}",
                headers={"Authorization": f"token {token}"}
            )
            return response.status_code == 200
            
        except Exception:
            return False

github_service = GitHubService()