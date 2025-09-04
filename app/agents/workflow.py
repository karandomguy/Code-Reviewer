from typing import Dict, List
from typing_extensions import TypedDict, Annotated
from langgraph.graph import StateGraph, END, add_messages
from app.agents.code_fetcher import fetch_pr_changes
from app.agents.analyzer import (
    security_review,
    performance_review,
    style_review,
    logic_review
)
from app.utils.logging import logger

# Custom reducer for analysis results
def merge_analysis_results(existing: Dict, new: Dict) -> Dict:
    """Merge analysis results from multiple analyzers."""
    if not existing:
        existing = {}
    existing.update(new)
    return existing

class ReviewState(TypedDict):
    # Input
    repo: str
    pr_number: int
    github_token: str
    
    # Fetched data
    pr_details: Dict
    files_changed: List[Dict]
    commit_sha: str
    pr_status: str
    review_context: Dict
    
    # Analysis results - use Annotated for concurrent updates
    analysis_results: Annotated[Dict, merge_analysis_results]
    
    # Final output
    summary: Dict
    error: str

def create_summary(state: ReviewState) -> ReviewState:
    """Create final analysis summary."""
    try:
        analysis_results = state.get("analysis_results", {})
        files_changed = state.get("files_changed", [])
        review_context = state.get("review_context", {})
        
        # Aggregate all issues
        all_issues = []
        total_critical = 0
        total_high = 0
        total_medium = 0
        total_low = 0
        
        for analysis_type, data in analysis_results.items():
            issues = data.get("issues", [])
            all_issues.extend(issues)
            
            # Count by severity
            for issue in issues:
                severity = issue.get("severity", "medium")
                if severity == "critical":
                    total_critical += 1
                elif severity == "high":
                    total_high += 1
                elif severity == "medium":
                    total_medium += 1
                elif severity == "low":
                    total_low += 1
        
        # Group issues by file
        files_with_issues = {}
        for issue in all_issues:
            filename = issue.get("filename", "unknown")
            if filename not in files_with_issues:
                files_with_issues[filename] = []
            files_with_issues[filename].append(issue)
        
        # Create file summaries
        file_summaries = []
        for file_data in files_changed:
            filename = file_data["filename"]
            file_issues = files_with_issues.get(filename, [])
            
            file_summary = {
                "name": filename,
                "language": file_data.get("language", "text"),
                "status": file_data.get("status", "modified"),
                "changes": file_data.get("changes", 0),
                "issues": file_issues,
                "issue_count": len(file_issues),
                "critical_count": len([i for i in file_issues if i["severity"] == "critical"]),
                "high_count": len([i for i in file_issues if i["severity"] == "high"])
            }
            file_summaries.append(file_summary)
        
        # Create overall summary
        summary = {
            "pr_info": {
                "repo": state.get("repo"),
                "pr_number": state.get("pr_number"), 
                "title": review_context.get("title", ""),
                "author": review_context.get("author", ""),
                "commit_sha": state.get("commit_sha", ""),
                "status": state.get("pr_status", "open")
            },
            "analysis_summary": {
                "total_files": len(files_changed),
                "files_with_issues": len([f for f in file_summaries if f["issue_count"] > 0]),
                "total_issues": len(all_issues),
                "critical_issues": total_critical,
                "high_issues": total_high,
                "medium_issues": total_medium,
                "low_issues": total_low
            },
            "files": file_summaries,
            "recommendations": _generate_recommendations(analysis_results, total_critical, total_high),
            "analysis_types": list(analysis_results.keys())
        }
        
        logger.info("Analysis summary created",
                   total_issues=len(all_issues),
                   critical_issues=total_critical,
                   files_analyzed=len(files_changed))
        
        return {"summary": summary}
        
    except Exception as e:
        logger.error("Failed to create summary", error=str(e))
        return {"error": f"Summary generation failed: {str(e)}"}

def _generate_recommendations(analysis_results: Dict, critical_count: int, high_count: int) -> List[str]:
    """Generate actionable recommendations based on analysis."""
    recommendations = []
    
    if critical_count > 0:
        recommendations.append("🚨 CRITICAL: Address critical security vulnerabilities immediately before merging.")
    
    if high_count > 5:
        recommendations.append("⚠️ HIGH: Consider breaking this PR into smaller chunks for easier review.")
    
    # Security recommendations
    security_issues = analysis_results.get("security", {}).get("issues", [])
    if len(security_issues) > 0:
        recommendations.append("🔐 Security: Run additional security scans and consider security review.")
    
    # Performance recommendations
    perf_issues = analysis_results.get("performance", {}).get("issues", [])
    if len([i for i in perf_issues if i["severity"] in ["critical", "high"]]) > 0:
        recommendations.append("⚡ Performance: Profile the application to validate performance improvements.")
    
    # Style recommendations
    style_issues = analysis_results.get("style", {}).get("issues", [])
    if len(style_issues) > 10:
        recommendations.append("✨ Style: Consider using automated code formatting tools.")
    
    if not recommendations:
        recommendations.append("✅ Good job! No major issues found. Code looks ready for merge.")
    
    return recommendations

def route_analyzers(state: ReviewState) -> List[str]:
    """Intelligently route to relevant analyzers based on file content."""
    files_changed = state.get("files_changed", [])
    languages = {f.get("language", "text") for f in files_changed}
    
    # Start with always-run analyzers
    routes = []
    
    # Always run style and logic for any code files
    code_languages = languages - {"text", "markdown", "json", "yaml", "xml"}
    if code_languages:
        routes.extend(["style_analysis", "logic_analysis"])
    
    # Run security for security-relevant languages
    security_languages = {
        "python", "javascript", "typescript", "java", "php", "go", 
        "rust", "csharp", "cpp", "c", "ruby", "kotlin", "scala", "swift"
    }
    if languages & security_languages:
        routes.append("security_analysis")
    
    # Run performance for performance-critical languages
    perf_languages = {
        "python", "javascript", "typescript", "java", "go", "rust", 
        "cpp", "c", "csharp", "kotlin", "scala", "swift"
    }
    if languages & perf_languages:
        routes.append("performance_analysis")
    
    # Always include summary
    routes.append("create_summary")
    
    logger.info("Smart analyzer routing", 
               languages=list(languages), 
               routes=[r for r in routes if r != "create_summary"])
    
    return routes

def create_review_workflow():
    """Create optimized workflow with proper parallel execution handling."""
    workflow = StateGraph(ReviewState)
    
    # Add all nodes
    workflow.add_node("fetch_code", fetch_pr_changes)
    workflow.add_node("security_analysis", security_review)
    workflow.add_node("performance_analysis", performance_review)
    workflow.add_node("style_analysis", style_review)
    workflow.add_node("logic_analysis", logic_review)
    workflow.add_node("create_summary", create_summary)
    
    # Set entry point
    workflow.set_entry_point("fetch_code")
    
    # Smart routing after fetch - runs relevant analyzers in parallel
    workflow.add_conditional_edges(
        "fetch_code",
        route_analyzers,
        {
            "security_analysis": "security_analysis",
            "performance_analysis": "performance_analysis", 
            "style_analysis": "style_analysis",
            "logic_analysis": "logic_analysis",
            "create_summary": "create_summary"
        }
    )
    
    # All analyzers flow to summary (fan-in pattern)
    workflow.add_edge("security_analysis", "create_summary")
    workflow.add_edge("performance_analysis", "create_summary")
    workflow.add_edge("style_analysis", "create_summary")
    workflow.add_edge("logic_analysis", "create_summary")
    
    # End workflow
    workflow.add_edge("create_summary", END)
    
    return workflow.compile()

# Create the compiled workflow
review_workflow = create_review_workflow()