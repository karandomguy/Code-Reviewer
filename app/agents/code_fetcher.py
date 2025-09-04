from typing import Dict, List
from typing import Generator
from app.services.github_service import github_service
from app.utils.logging import logger

async def fetch_pr_changes(state: Dict) -> Dict:
    """Fetch PR changes and prepare for analysis."""
    repo = state["repo"]
    pr_number = state["pr_number"] 
    token = state["github_token"]
    
    try:
        logger.info("Fetching PR changes", repo=repo, pr=pr_number)
        
        # Get PR details
        pr_details = await github_service.get_pr_details(repo, pr_number, token)
        if not pr_details:
            raise Exception("Failed to fetch PR details")
        
        # Get changed files
        files_changed = await github_service.get_pr_files(repo, pr_number, token)
        if not files_changed:
            raise Exception("Failed to fetch PR files")
        
        # Fetch file contents for analysis
        enhanced_files = []
        for file in files_changed:
            if file["status"] in ["added", "modified"]:
                content = await github_service.get_file_content(
                    repo, file["filename"], pr_details["head"]["sha"], token
                )
                
                enhanced_file = {
                    "filename": file["filename"],
                    "status": file["status"],
                    "additions": file.get("additions", 0),
                    "deletions": file.get("deletions", 0),
                    "changes": file.get("changes", 0),
                    "patch": file.get("patch", ""),
                    "content": content,
                    "language": _detect_language(file["filename"])
                }
                enhanced_files.append(enhanced_file)
        
        state.update({
            "pr_details": pr_details,
            "files_changed": enhanced_files,
            "commit_sha": pr_details["head"]["sha"],
            "pr_status": pr_details["state"],
            "review_context": {
                "title": pr_details["title"],
                "description": pr_details.get("body", ""),
                "author": pr_details["user"]["login"],
                "base_branch": pr_details["base"]["ref"],
                "head_branch": pr_details["head"]["ref"]
            }
        })
        
        logger.info("Successfully fetched PR changes", 
                   files_count=len(enhanced_files),
                   total_changes=sum(f["changes"] for f in enhanced_files))
        
        return state
        
    except Exception as e:
        logger.error("Failed to fetch PR changes", error=str(e))
        state["error"] = str(e)
        return state

def _detect_language(filename: str) -> str:
    """Detect programming language from filename."""
    extensions = {
        ".py": "python",
        ".js": "javascript", 
        ".ts": "typescript",
        ".jsx": "react",
        ".tsx": "react-typescript",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".cpp": "cpp",
        ".c": "c",
        ".cs": "csharp",
        ".php": "php",
        ".rb": "ruby",
        ".swift": "swift",
        ".kt": "kotlin",
        ".scala": "scala",
        ".sql": "sql",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".json": "json",
        ".xml": "xml",
        ".html": "html",
        ".css": "css",
        ".scss": "scss",
        ".md": "markdown",
        ".sh": "bash",
    }
    
    for ext, lang in extensions.items():
        if filename.lower().endswith(ext):
            return lang
    
    return "text"