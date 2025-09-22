#!/usr/bin/env python3
"""
Command Line Interface for RAG Chatbot
Provides an interactive CLI for querying the RAG system
"""

import argparse
import json
import os
import sys
import requests
from typing import Optional, Dict, Any
import readline  # For better input experience
from datetime import datetime


class RAGCLIClient:
    """CLI client for RAG chatbot interaction"""
    
    def __init__(self, api_url: str, timeout: int = 30):
        self.api_url = api_url.rstrip('/')
        self.timeout = timeout
        self.conversation_id: Optional[str] = None
        self.session = requests.Session()
        
        # Setup session headers
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'RAG-CLI-Client/1.0'
        })
    
    def health_check(self) -> bool:
        """Check if the RAG service is healthy"""
        try:
            response = self.session.get(
                f"{self.api_url}/health",
                timeout=self.timeout
            )
            return response.status_code == 200
        except requests.RequestException:
            return False
    
    def send_query(self, query: str, max_results: int = 3) -> Dict[str, Any]:
        """Send query to RAG service"""
        payload = {
            "query": query,
            "max_results": max_results
        }
        
        if self.conversation_id:
            payload["conversation_id"] = self.conversation_id
        
        try:
            response = self.session.post(
                f"{self.api_url}/chat",
                json=payload,
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                data = response.json()
                self.conversation_id = data.get("conversation_id")
                return data
            else:
                return {
                    "error": f"HTTP {response.status_code}: {response.text}",
                    "status": "error"
                }
                
        except requests.RequestException as e:
            return {
                "error": f"Request failed: {str(e)}",
                "status": "error"
            }
    
    def format_response(self, response: Dict[str, Any]) -> str:
        """Format response for CLI display"""
        if response.get("status") == "error":
            return f"❌ Error: {response.get('error', 'Unknown error')}"
        
        output = []
        
        # Main answer
        answer = response.get("answer", "No answer provided")
        output.append(f"🤖 Answer: {answer}")
        
        # Sources if available
        sources = response.get("sources", [])
        if sources:
            output.append("\n📚 Sources:")
            for i, source in enumerate(sources[:3], 1):  # Show top 3 sources
                source_name = source.get("source", "Unknown")
                score = source.get("score", 0)
                page = source.get("page")
                page_info = f" (page {page})" if page else ""
                output.append(f"  {i}. {source_name}{page_info} - Relevance: {score:.2f}")
        
        # Metadata
        processing_time = response.get("processing_time")
        if processing_time:
            output.append(f"\n⏱️  Processing time: {processing_time:.2f}s")
        
        cached = response.get("cached")
        if cached:
            output.append("💾 (cached response)")
        
        return "\n".join(output)


def interactive_mode(client: RAGCLIClient):
    """Run interactive CLI mode"""
    print("🚀 RAG Chatbot CLI - Interactive Mode")
    print("Type 'quit', 'exit', or press Ctrl+C to exit")
    print("Type 'help' for available commands")
    print("Type 'reset' to start a new conversation")
    print("-" * 50)
    
    if not client.health_check():
        print("⚠️  Warning: Cannot connect to RAG service. Responses may fail.")
        print(f"Service URL: {client.api_url}")
    
    while True:
        try:
            # Get user input
            prompt = "🔍 Query: " if client.conversation_id is None else f"🔍 Query [{client.conversation_id[:8]}...]: "
            user_input = input(prompt).strip()
            
            # Handle special commands
            if user_input.lower() in ['quit', 'exit']:
                print("👋 Goodbye!")
                break
            elif user_input.lower() == 'help':
                show_help()
                continue
            elif user_input.lower() == 'reset':
                client.conversation_id = None
                print("🔄 Conversation reset. Starting fresh.")
                continue
            elif user_input.lower() == 'status':
                if client.health_check():
                    print("✅ Service is healthy")
                else:
                    print("❌ Service appears to be down")
                continue
            elif not user_input:
                continue
            
            # Send query
            print("\n🤔 Thinking...")
            response = client.send_query(user_input)
            
            # Display response
            print("\n" + client.format_response(response))
            print("\n" + "=" * 60 + "\n")
            
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Unexpected error: {e}")


def single_query_mode(client: RAGCLIClient, query: str, max_results: int = 3):
    """Run single query mode"""
    print(f"🔍 Query: {query}")
    print("-" * 50)
    
    if not client.health_check():
        print("❌ Error: Cannot connect to RAG service")
        print(f"Service URL: {client.api_url}")
        sys.exit(1)
    
    response = client.send_query(query, max_results)
    print(client.format_response(response))
    
    # Exit with error code if query failed
    if response.get("status") == "error":
        sys.exit(1)


def batch_mode(client: RAGCLIClient, queries_file: str):
    """Run batch mode from file"""
    if not os.path.exists(queries_file):
        print(f"❌ Error: File '{queries_file}' not found")
        sys.exit(1)
    
    print(f"📄 Processing queries from: {queries_file}")
    print("-" * 50)
    
    if not client.health_check():
        print("❌ Error: Cannot connect to RAG service")
        sys.exit(1)
    
    try:
        with open(queries_file, 'r', encoding='utf-8') as f:
            queries = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        results = []
        for i, query in enumerate(queries, 1):
            print(f"\n📝 Query {i}/{len(queries)}: {query}")
            response = client.send_query(query)
            
            result = {
                "query": query,
                "timestamp": datetime.now().isoformat(),
                "response": response
            }
            results.append(result)
            
            print(client.format_response(response))
            print("-" * 40)
        
        # Save results to file
        output_file = f"rag_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 Results saved to: {output_file}")
        
    except Exception as e:
        print(f"❌ Error processing batch file: {e}")
        sys.exit(1)


def show_help():
    """Show help information"""
    help_text = """
🤖 RAG Chatbot CLI - Available Commands:

Interactive Mode Commands:
  help     - Show this help message
  status   - Check service health
  reset    - Start a new conversation (clear conversation ID)
  quit     - Exit the CLI
  exit     - Exit the CLI

Query Examples:
  "What is machine learning?"
  "How does neural network training work?"
  "Explain the difference between supervised and unsupervised learning"

Tips:
  - Use quotes around queries with special characters
  - Conversation context is maintained between queries
  - Use 'reset' to start fresh if conversation gets off track
  - Check 'status' if you're experiencing connection issues
"""
    print(help_text)


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="RAG Chatbot Command Line Interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode
  %(prog)s --api-url http://localhost:8000

  # Single query
  %(prog)s --api-url http://localhost:8000 --query "What is AI?"

  # Batch processing
  %(prog)s --api-url http://localhost:8000 --batch queries.txt

  # AWS Lambda endpoint
  %(prog)s --api-url https://api-id.execute-api.region.amazonaws.com/dev
        """
    )
    
    parser.add_argument(
        '--api-url',
        required=True,
        help='RAG service API URL (e.g., http://localhost:8000)'
    )
    
    parser.add_argument(
        '--query', '-q',
        help='Single query to execute (non-interactive mode)'
    )
    
    parser.add_argument(
        '--batch', '-b',
        help='File containing queries to process in batch mode'
    )
    
    parser.add_argument(
        '--max-results',
        type=int,
        default=3,
        help='Maximum number of source results to return (default: 3)'
    )
    
    parser.add_argument(
        '--timeout',
        type=int,
        default=30,
        help='Request timeout in seconds (default: 30)'
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version='RAG CLI Client 1.0'
    )
    
    args = parser.parse_args()
    
    # Create client
    client = RAGCLIClient(
        api_url=args.api_url,
        timeout=args.timeout
    )
    
    # Determine mode
    if args.query:
        single_query_mode(client, args.query, args.max_results)
    elif args.batch:
        batch_mode(client, args.batch)
    else:
        interactive_mode(client)


if __name__ == "__main__":
    main()