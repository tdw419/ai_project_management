"""
Run the API server example
"""

import asyncio
from aipm import PromptSystem, ProjectManager
from aipm.api import APIServer


async def main():
    # Initialize components
    system = PromptSystem()
    pm = ProjectManager()
    
    # Create a sample project
    project = pm.create_project(
        name="Sample Project",
        goal="Demonstrate AIPM capabilities",
    )
    
    # Add some sample tasks
    pm.add_task(project_id=project.id, name="Design system architecture")
    pm.add_task(project_id=project.id, name="Implement core features")
    pm.add_task(project_id=project.id, name="Write tests")
    
    # Add some sample prompts
    from aipm.core.engine import Prompt, PromptCategory
    
    prompts = [
        Prompt(
            id="prompt_001",
            text="Analyze the system architecture requirements",
            category=PromptCategory.ANALYSIS,
            priority=1,
        ),
        Prompt(
            id="prompt_002",
            text="Generate database schema for user management",
            category=PromptCategory.CODE_GEN,
            priority=2,
        ),
        Prompt(
            id="prompt_003",
            text="Write unit tests for authentication module",
            category=PromptCategory.TEST,
            priority=3,
        ),
    ]
    
    for p in prompts:
        system.add_prompt(p)
    
    # Start the API server
    server = APIServer(system=system, pm=pm, port=8080)
    await server.run()


if __name__ == "__main__":
    asyncio.run(main())
