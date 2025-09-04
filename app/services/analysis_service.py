from typing import Dict, Optional
# from app.agents.workflow import review_workflow
from app.services.cache_service import cache_service
from app.services.github_service import github_service
from app.utils.logging import logger
from app.utils.monitoring import track_time, ANALYSIS_DURATION

class AnalysisService:
    def __init__(self):
        self.workflow = None  # Initialize as None
    
    def _get_workflow(self):
        """Lazy load the workflow to avoid circular import."""
        if self.workflow is None:
            from app.agents.workflow import review_workflow  # Import only when needed
            self.workflow = review_workflow
        return self.workflow
    
    @track_time(ANALYSIS_DURATION)
    async def analyze_pr(self, repo_url: str, pr_number: int, github_token: str) -> Dict:
        """Analyze a GitHub pull request using LangGraph workflow."""
        try:
            # Parse repository URL
            repo = github_service.parse_repo_url(repo_url)
            if not repo:
                raise ValueError(f"Invalid repository URL: {repo_url}")
            
            # Check for cached results first
            pr_details = await github_service.get_pr_details(repo, pr_number, github_token)
            if not pr_details:
                raise ValueError(f"Cannot access PR {pr_number} in {repo}")
            
            commit_sha = pr_details["head"]["sha"]
            cached_result = await cache_service.get_pr_analysis(repo, pr_number, commit_sha)
            
            if cached_result:
                logger.info("Returning cached analysis", repo=repo, pr=pr_number)
                return cached_result
            
            # Initialize workflow state
            initial_state = {
                "repo": repo,
                "pr_number": pr_number,
                "github_token": github_token,
                "analysis_results": {},
                "error": ""
            }
            
            logger.info("Starting LangGraph PR analysis", repo=repo, pr_number=pr_number)
            
            # Run the LangGraph workflow - use lazy loaded workflow
            workflow = self._get_workflow()
            final_state = await workflow.ainvoke(initial_state)
            
            if final_state.get("error"):
                raise Exception(final_state["error"])
            
            # Extract results
            result = {
                "task_id": None,
                "status": "completed",
                "results": final_state.get("summary", {}),
                "metadata": {
                    "repo": repo,
                    "pr_number": pr_number,
                    "commit_sha": commit_sha,
                    "analysis_timestamp": None
                }
            }
            
            # Cache the results
            await cache_service.cache_pr_analysis(
                repo, pr_number, commit_sha, result, pr_details.get("state", "open")
            )
            
            logger.info("LangGraph PR analysis completed", 
                       repo=repo, 
                       pr_number=pr_number,
                       total_issues=result["results"].get("analysis_summary", {}).get("total_issues", 0))
            
            return result
            
        except Exception as e:
            logger.error("LangGraph PR analysis failed", error=str(e))
            raise

analysis_service = AnalysisService()