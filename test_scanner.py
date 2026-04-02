from aipm.scanner import ProjectScanner
import json

def test_scanner():
    scanner = ProjectScanner("./repos")
    projects = scanner.scan()
    print(f"Discovered {len(projects)} projects.")
    
    # Print the first 10
    for p in projects[:10]:
        print(f"- {p.name} ({p.language}) at {p.path}")

if __name__ == "__main__":
    test_scanner()
