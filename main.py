#!/usr/bin/env python
"""
Entry point for the AI Nutrition Companion application.
Run this file to start the server.
"""
import os
import sys
import uvicorn

def main():
    """Run the server with the appropriate settings."""
    # Get port from environment variable or use default
    port = int(os.getenv("PORT", 9000))

    # Print a clickable development URL
    print(f"\nLocal development URL: http://127.0.0.1:{port}\n")
    
    # Start server
    uvicorn.run(
        "app.web.openai_ptalk.app:app",
        host="0.0.0.0",
        port=port,
        log_level="info"
    )

if __name__ == "__main__":
    # Add the project root to Python path if needed
    project_root = os.path.dirname(os.path.abspath(__file__))
    if project_root not in sys.path:
        sys.path.append(project_root)
    
    main()