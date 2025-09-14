#!/usr/bin/env python3
"""
Export OpenAPI specification for the Evently Booking Platform API.

This script generates the OpenAPI JSON specification that can be used
for API documentation, client generation, and testing tools.
"""

import json
import sys
import os

# Add the project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from evently_booking_platform.main import app

def export_openapi_spec():
    """Export the OpenAPI specification to a JSON file."""
    try:
        # Get the OpenAPI schema
        openapi_schema = app.openapi()
        
        # Write to file
        output_file = "openapi.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(openapi_schema, f, indent=2, ensure_ascii=False)
        
        print(f"✅ OpenAPI specification exported to: {output_file}")
        print(f"📄 Schema version: {openapi_schema.get('openapi', 'unknown')}")
        print(f"🏷️  API title: {openapi_schema.get('info', {}).get('title', 'unknown')}")
        print(f"🔢 API version: {openapi_schema.get('info', {}).get('version', 'unknown')}")
        
        # Count endpoints
        paths = openapi_schema.get('paths', {})
        endpoint_count = sum(len(methods) for methods in paths.values())
        print(f"🔗 Total endpoints: {endpoint_count}")
        
        print(f"\n📋 Available paths:")
        for path in sorted(paths.keys()):
            methods = list(paths[path].keys())
            print(f"  {path}: {', '.join(method.upper() for method in methods)}")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to export OpenAPI specification: {e}")
        return False

def main():
    """Main function."""
    print("🔄 Exporting OpenAPI specification...")
    print("="*50)
    
    success = export_openapi_spec()
    
    if success:
        print("\n" + "="*50)
        print("🎉 Export completed successfully!")
        print("\n💡 You can use this file with:")
        print("  - Swagger Editor: https://editor.swagger.io/")
        print("  - Postman: Import as OpenAPI 3.0")
        print("  - Code generators: swagger-codegen, openapi-generator")
        print("  - API testing tools: Insomnia, Paw, etc.")
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()