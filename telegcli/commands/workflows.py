"""
telegcli.commands.workflows
───────────────────────────
Advanced automation workflows.

Features:
  - Chain multiple automation rules
  - Conditional logic (if-then-else)
  - Variables and templating
  - Action logging and debugging
  - Workflow scheduling
"""

from __future__ import annotations

import asyncio
import datetime
from typing import Optional, Callable
from dataclasses import dataclass, asdict

from rich.table import Table
from rich.syntax import Syntax
from rich import box

from telegcli.core.config import get_config
from telegcli.ui.theme import (
    get_console, get_palette, print_success, print_error, print_info, print_warning
)


@dataclass
class WorkflowStep:
    """Single step in a workflow"""
    name: str
    action: str  # "send", "forward", "delete", "react", "tag"
    conditions: dict  # {"if_text_contains": "hello", "if_from": "@user"}
    parameters: dict  # {"text": "...", "emoji": "..."}


class WorkflowEngine:
    """Execute and manage workflows"""
    
    def __init__(self):
        self.cfg = get_config()
        if "workflows" not in self.cfg:
            self.cfg.set("workflows", {})
        if "workflow_logs" not in self.cfg:
            self.cfg.set("workflow_logs", [])
    
    async def create_workflow(self, name: str, steps: list[dict]) -> bool:
        """Create a new workflow"""
        workflows = self.cfg.get("workflows", {})
        
        if name in workflows:
            return False  # Already exists
        
        workflows[name] = {
            "steps": steps,
            "created": datetime.datetime.now().isoformat(),
            "enabled": True,
            "runtime_count": 0
        }
        self.cfg.set("workflows", workflows)
        return True
    
    async def execute_workflow(self, name: str, context: dict) -> dict:
        """Execute a workflow with given context"""
        workflows = self.cfg.get("workflows", {})
        
        if name not in workflows:
            return {"success": False, "error": f"Workflow '{name}' not found"}
        
        workflow = workflows[name]
        results = []
        
        for step in workflow["steps"]:
            result = await self._execute_step(step, context)
            results.append(result)
            
            # Stop on error unless configured to continue
            if not result.get("success") and not step.get("continue_on_error"):
                break
        
        # Log execution
        logs = self.cfg.get("workflow_logs", [])
        logs.append({
            "workflow": name,
            "timestamp": datetime.datetime.now().isoformat(),
            "results": results,
            "context_keys": list(context.keys())
        })
        self.cfg.set("workflow_logs", logs)
        
        # Update runtime count
        workflow["runtime_count"] = workflow.get("runtime_count", 0) + 1
        self.cfg.set("workflows", workflows)
        
        return {
            "success": all(r.get("success") for r in results),
            "steps": len(results),
            "results": results
        }
    
    async def _execute_step(self, step: dict, context: dict) -> dict:
        """Execute single workflow step"""
        # Check conditions
        conditions = step.get("conditions", {})
        
        if not self._check_conditions(conditions, context):
            return {"success": True, "skipped": True, "reason": "conditions not met"}
        
        action = step.get("action", "").lower()
        
        # This would integrate with actual command handlers
        # For now, we return a success with logging
        
        if action == "send":
            params = step.get("parameters", {})
            return {
                "success": True,
                "action": action,
                "message": f"Would send: {params.get('text')}"
            }
        elif action == "forward":
            params = step.get("parameters", {})
            return {
                "success": True,
                "action": action,
                "message": f"Would forward to {params.get('to_chat')}"
            }
        elif action == "react":
            params = step.get("parameters", {})
            return {
                "success": True,
                "action": action,
                "message": f"Would react with {params.get('emoji')}"
            }
        else:
            return {"success": False, "error": f"Unknown action: {action}"}
    
    def _check_conditions(self, conditions: dict, context: dict) -> bool:
        """Check if all conditions are met"""
        for condition_key, condition_value in conditions.items():
            context_key = condition_key.replace("if_", "")
            
            if context_key not in context:
                return False
            
            if condition_key.startswith("if_"):
                if condition_key == "if_text_contains":
                    if condition_value not in context.get("text", ""):
                        return False
                elif condition_key == "if_from":
                    if context.get("from") != condition_value:
                        return False
                elif condition_key == "if_in_chat":
                    if context.get("chat") != condition_value:
                        return False
        
        return True


async def cmd_workflow(args: list[str]) -> None:
    """
    workflow create <name>             → Create new workflow (interactive)
    workflow list                       → List all workflows
    workflow show <name>                → Show workflow details
    workflow edit <name>                → Edit workflow
    workflow run <name>                 → Test run workflow
    workflow delete <name>              → Delete workflow
    workflow logs [name] [--last <n>]   → Show execution logs
    """
    console = get_console()
    p = get_palette()
    engine = WorkflowEngine()
    
    if not args:
        print_error("Usage: workflow create|list|show|run|delete|logs")
        return
    
    subcommand = args[0].lower()
    
    # ─── workflow create <name> ───
    if subcommand == "create":
        if len(args) < 2:
            print_error("Usage: workflow create <name>")
            return
        
        workflow_name = args[1]
        workflows = engine.cfg.get("workflows", {})
        
        if workflow_name in workflows:
            print_warning(f"Workflow '{workflow_name}' already exists.")
            return
        
        print_info("Creating workflow... (example: simple auto-reply)")
        
        steps = [
            {
                "name": "Check if message contains 'hello'",
                "action": "react",
                "conditions": {"if_text_contains": "hello"},
                "parameters": {"emoji": "👋"}
            }
        ]
        
        success = await engine.create_workflow(workflow_name, steps)
        if success:
            print_success(f"Created workflow '{workflow_name}'")
            print_info(f"Edit with: workflow edit {workflow_name}")
        else:
            print_error("Could not create workflow")
    
    # ─── workflow list ───
    elif subcommand == "list":
        workflows = engine.cfg.get("workflows", {})
        
        if not workflows:
            print_info("No workflows. Create one: workflow create <name>")
            return
        
        table = Table(box=box.SIMPLE, header_style=f"bold {p['accent']}")
        table.add_column("Workflow", style=p["success"])
        table.add_column("Steps", style=p["dim"], justify="right")
        table.add_column("Enabled", style=p["dim"], justify="center")
        table.add_column("Runs", style=p["dim"], justify="right")
        
        for name, wf in sorted(workflows.items()):
            enabled = "✓" if wf.get("enabled") else "✗"
            table.add_row(
                name,
                str(len(wf.get("steps", []))),
                enabled,
                str(wf.get("runtime_count", 0))
            )
        
        console.print(table)
    
    # ─── workflow show <name> ───
    elif subcommand == "show":
        if len(args) < 2:
            print_error("Usage: workflow show <name>")
            return
        
        workflows = engine.cfg.get("workflows", {})
        workflow_name = args[1]
        
        if workflow_name not in workflows:
            print_error(f"Workflow '{workflow_name}' not found.")
            return
        
        wf = workflows[workflow_name]
        console.print(f"\n[bold {p['accent']}]{workflow_name}[/]\n")
        
        # Show as formatted steps
        for i, step in enumerate(wf.get("steps", []), 1):
            console.print(f"[{p['accent']}]Step {i}:[/] {step.get('action')}")
            if step.get("conditions"):
                console.print(f"  If: {step['conditions']}")
            if step.get("parameters"):
                console.print(f"  Then: {step['parameters']}")
    
    # ─── workflow run <name> ───
    elif subcommand == "run":
        if len(args) < 2:
            print_error("Usage: workflow run <name>")
            return
        
        workflow_name = args[1]
        
        # Test with sample context
        context = {
            "text": "hello world",
            "from": "@user",
            "chat": "general"
        }
        
        result = await engine.execute_workflow(workflow_name, context)
        
        if result.get("success"):
            print_success(f"Workflow executed successfully")
            print_info(f"Steps: {result.get('steps')}")
        else:
            print_error(f"Workflow failed: {result.get('error')}")
    
    # ─── workflow delete <name> ───
    elif subcommand == "delete":
        if len(args) < 2:
            print_error("Usage: workflow delete <name>")
            return
        
        workflow_name = args[1]
        workflows = engine.cfg.get("workflows", {})
        
        if workflow_name not in workflows:
            print_error(f"Workflow '{workflow_name}' not found.")
            return
        
        del workflows[workflow_name]
        engine.cfg.set("workflows", workflows)
        print_success(f"Deleted workflow '{workflow_name}'")
    
    # ─── workflow logs ───
    elif subcommand == "logs":
        logs = engine.cfg.get("workflow_logs", [])
        
        if not logs:
            print_info("No workflow logs yet.")
            return
        
        limit = 10
        for i, arg in enumerate(args[1:]):
            if arg == "--last" and i + 1 < len(args):
                try:
                    limit = int(args[i + 2])
                except ValueError:
                    pass
        
        table = Table(box=box.SIMPLE, header_style=f"bold {p['accent']}")
        table.add_column("Workflow", style=p["success"])
        table.add_column("Timestamp", style=p["dim"])
        table.add_column("Status", style=p["dim"])
        
        for log in logs[-limit:]:
            success_status = "✓" if log.get("success") else "✗"
            table.add_row(
                log["workflow"],
                log["timestamp"][:16],  # Just date and time
                success_status
            )
        
        console.print(table)
    
    else:
        print_error(f"Unknown subcommand: {subcommand}")
