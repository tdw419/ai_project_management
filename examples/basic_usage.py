"""
Basic usage example for AIPM
"""

from aipm import PromptSystem, ProjectManager, Dashboard

def main():
    # Initialize the system
    system = PromptSystem()
    pm = ProjectManager()
    
    # Create a project
    project = pm.create_project(
        name="Example Project",
        goal="Build a web application",
        path="/path/to/project",
    )
    
    print(f"Created project: {project.id}")
    
    # Add tasks
    task1 = pm.add_task(
        project_id=project.id,
        name="Design API",
        description="Design the REST API endpoints",
    )
    
    task2 = pm.add_task(
        project_id=project.id,
        name="Implement API",
        description="Create the API endpoints",
        dependencies=[task1.id],  # Depends on design task
    )
    
    print(f"Added tasks: {task1.id}, {task2.id}")
    
    # View project stats
    stats = pm.get_project_stats(project.id)
    print(f"Project stats: {stats}")
    
    # Mark a task as complete
    pm.update_task_status(task1.id, "completed")
    
    # Check ready tasks
    ready = pm.get_ready_tasks(project.id)
    print(f"Ready tasks: {[t.name for t in ready]}")
    
    # Add a prompt to the queue
    from aipm.core.engine import Prompt, PromptCategory
    
    prompt = Prompt(
        id="prompt_001",
        text="Write a REST API for user authentication",
        category=PromptCategory.CODE_GEN,
        priority=1,
        confidence=0.8,
        impact=0.9,
    )
    
    system.add_prompt(prompt)
    print(f"Added prompt: {prompt.id}")
    
    # Get next prompt to process
    next_prompt = system.get_next_prompt()
    if next_prompt:
        print(f"Next prompt: {next_prompt.text[:50]}...")
    
    # View queue stats
    queue_stats = system.queue.get_stats()
    print(f"Queue stats: {queue_stats}")


if __name__ == "__main__":
    main()
