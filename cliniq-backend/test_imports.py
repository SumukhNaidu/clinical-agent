
import importlib.util
import sys

def find_module(module_name):
    try:
        spec = importlib.util.find_spec(module_name)
        if spec:
            print(f"Found module: {module_name} at {spec.origin}")
            return True
    except Exception as e:
        print(f"Error finding {module_name}: {e}")
    return False

# Try possible locations
possible_imports = [
    "langchain.chains.retrieval",
    "langchain_core.chains",
    "langchain_community.chains",
    "langchain.chains",
    "langchain.chains.combine_documents",
]

for imp in possible_imports:
    print(f"\nChecking: {imp}")
    find_module(imp)
