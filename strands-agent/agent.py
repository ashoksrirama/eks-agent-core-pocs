from strands import Agent, tool
from strands_tools import use_aws
from typing import Dict, Any
import json
import os
import asyncio
from contextlib import suppress

from bedrock_agentcore.tools.browser_client import BrowserClient
from browser_use import Agent as BrowserAgent
from browser_use.browser.session import BrowserSession
from browser_use.browser import BrowserProfile
from langchain_aws import ChatBedrockConverse
from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter
from bedrock_agentcore.memory import MemoryClient
from rich.console import Console
import re

console = Console()

# Configuration from environment variables
BROWSER_ID = os.getenv('BROWSER_ID')
CODE_INTERPRETER_ID = os.getenv('CODE_INTERPRETER_ID')
MEMORY_ID = os.getenv('MEMORY_ID')
RESULTS_BUCKET = os.getenv('RESULTS_BUCKET', 'weather-results-bucket')
AWS_REGION = os.getenv('AWS_REGION', 'us-east-1')

# Check which capabilities are enabled
HAS_BROWSER = bool(BROWSER_ID)
HAS_CODE_INTERPRETER = bool(CODE_INTERPRETER_ID)
HAS_MEMORY = bool(MEMORY_ID)

console.print(f"[cyan]🔧 Enabled Capabilities:[/cyan]")
console.print(f"  Browser: {'✅' if HAS_BROWSER else '❌'}")
console.print(f"  Code Interpreter: {'✅' if HAS_CODE_INTERPRETER else '❌'}")
console.print(f"  Memory: {'✅' if HAS_MEMORY else '❌'}")

async def run_browser_task(browser_session, bedrock_chat, task: str) -> str:
    """Run a browser automation task"""
    try:
        console.print(f"[blue]🤖 Executing browser task:[/blue] {task[:100]}...")
        
        agent = BrowserAgent(task=task, llm=bedrock_chat, browser=browser_session)
        result = await agent.run()
        console.print("[green]✅ Browser task completed![/green]")
        
        if 'done' in result.last_action() and 'text' in result.last_action()['done']:
            return result.last_action()['done']['text']
        else:
            raise ValueError("NO Data")
            
    except Exception as e:
        console.print(f"[red]❌ Browser task error: {e}[/red]")
        raise

async def initialize_browser_session():
    """Initialize Browser session with AgentCore"""
    try:
        client = BrowserClient(AWS_REGION)
        client.start(identifier=BROWSER_ID)
        
        ws_url, headers = client.generate_ws_headers()
        console.print(f"[cyan]🔗 Browser WebSocket URL: {ws_url[:50]}...[/cyan]")
        
        browser_profile = BrowserProfile(headers=headers, timeout=150000)
        browser_session = BrowserSession(cdp_url=ws_url, browser_profile=browser_profile, keep_alive=True)
        
        console.print("[cyan]🔄 Initializing browser session...[/cyan]")
        await browser_session.start()
        
        bedrock_chat = ChatBedrockConverse(
            model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
            region_name=AWS_REGION
        )
        
        console.print("[green]✅ Browser session ready[/green]")
        return browser_session, bedrock_chat, client
        
    except Exception as e:
        console.print(f"[red]❌ Failed to initialize browser: {e}[/red]")
        raise

@tool
async def get_weather_data(city: str) -> Dict[str, Any]:
    """Get weather data for a city using browser automation"""
    if not HAS_BROWSER:
        return {"status": "error", "content": [{"text": "Browser capability not enabled"}]}
    
    browser_session = None
    
    try:
        console.print(f"[cyan]🌐 Getting weather data for {city}[/cyan]")
        
        browser_session, bedrock_chat, browser_client = await initialize_browser_session()
        
        task = f"""Extract 8-Day Weather Forecast for {city} from weather.gov
        Steps:
        - Go to https://weather.gov
        - Search for "{city}" and click GO
        - Click "Printable Forecast" link
        - Extract date, high, low, conditions, wind, precip for each day
        - Return JSON array of daily forecasts
        """
        
        result = await run_browser_task(browser_session, bedrock_chat, task)
        
        if browser_client:
            browser_client.stop()

        return {"status": "success", "content": [{"text": result}]}
        
    except Exception as e:
        console.print(f"[red]❌ Error getting weather data: {e}[/red]")
        return {"status": "error", "content": [{"text": f"Error: {str(e)}"}]}
        
    finally:
        if browser_session:
            with suppress(Exception):
                await browser_session.close()

@tool
def generate_analysis_code(weather_data: str) -> Dict[str, Any]:
    """Generate Python code for weather classification"""
    try:
        query = f"""Create Python code to classify weather days as GOOD/OK/POOR:
        Rules: GOOD: 65-80°F clear, OK: 55-85°F partly cloudy, POOR: <55°F or >85°F
        Weather data: {weather_data}
        Return code that outputs list of tuples: [('2025-09-16', 'GOOD'), ...]"""
        
        agent = Agent()
        result = agent(query)
        
        pattern = r'```(?:json|python)\n(.*?)\n```'
        match = re.search(pattern, result.message['content'][0]['text'], re.DOTALL)
        python_code = match.group(1).strip() if match else result.message['content'][0]['text']
        
        return {"status": "success", "content": [{"text": python_code}]}
    except Exception as e:
        return {"status": "error", "content": [{"text": f"Error: {str(e)}"}]}

@tool
def execute_code(python_code: str) -> Dict[str, Any]:
    """Execute Python code using AgentCore Code Interpreter"""
    if not HAS_CODE_INTERPRETER:
        return {"status": "error", "content": [{"text": "Code Interpreter capability not enabled"}]}
    
    try:
        code_client = CodeInterpreter(AWS_REGION)
        code_client.start(identifier=CODE_INTERPRETER_ID)

        response = code_client.invoke("executeCode", {
            "code": python_code,
            "language": "python",
            "clearContext": True
        })

        for event in response["stream"]:
            code_execute_result = json.dumps(event["result"])
        
        analysis_results = json.loads(code_execute_result)
        console.print("Analysis results:", analysis_results)

        return {"status": "success", "content": [{"text": str(analysis_results)}]}

    except Exception as e:
        return {"status": "error", "content": [{"text": f"Error: {str(e)}"}]}

@tool
def store_user_preferences(preferences: str) -> Dict[str, Any]:
    """Store user activity preferences in memory"""
    if not HAS_MEMORY:
        return {"status": "success", "content": [{"text": "Memory not enabled. Preferences not stored."}]}
    
    try:
        client = MemoryClient(region_name=AWS_REGION)
        client.store(
            memory_id=MEMORY_ID,
            actor_id="user123",
            session_id="session456",
            content=f"User activity preferences: {preferences}",
            metadata={"type": "preferences"}
        )
        return {"status": "success", "content": [{"text": f"Preferences stored: {preferences}"}]}
    except Exception as e:
        return {"status": "error", "content": [{"text": f"Error storing preferences: {str(e)}"}]}

@tool
def get_activity_preferences() -> Dict[str, Any]:
    """Get user activity preferences from memory"""
    if not HAS_MEMORY:
        return {"status": "success", "content": [{"text": "Memory not enabled. Default: outdoor activities, hiking, beaches, museums."}]}
    
    try:
        client = MemoryClient(region_name=AWS_REGION)
        response = client.retrieve(
            memory_id=MEMORY_ID,
            query="What are the user's activity preferences and interests?",
            max_results=5
        )
        
        if response and len(response) > 0:
            preferences = "\n".join([item.get('content', '') for item in response])
            return {"status": "success", "content": [{"text": f"User preferences: {preferences}"}]}
        else:
            return {"status": "success", "content": [{"text": "No preferences stored. Default: outdoor activities, hiking, beaches, museums."}]}
    except Exception as e:
        return {"status": "error", "content": [{"text": f"Error retrieving preferences: {str(e)}"}]}

@tool
def store_activity_plan(city: str, plan: str) -> Dict[str, Any]:
    """Store the activity plan in memory for future reference"""
    if not HAS_MEMORY:
        return {"status": "success", "content": [{"text": "Memory not enabled. Plan not stored."}]}
    
    try:
        client = MemoryClient(region_name=AWS_REGION)
        client.store(
            memory_id=MEMORY_ID,
            actor_id="user123",
            session_id="session456",
            content=f"Activity plan for {city}: {plan}",
            metadata={"city": city, "type": "activity_plan"}
        )
        return {"status": "success", "content": [{"text": f"Activity plan stored in memory for {city}"}]}
    except Exception as e:
        return {"status": "error", "content": [{"text": f"Error storing plan: {str(e)}"}]}

def create_weather_agent() -> Agent:
    """Create the weather agent with all tools"""
    system_prompt = f"""You are a Weather-Based Activity Planning Assistant with memory.

    When a user asks about activities for a location:
    1. Extract city from query
    2. Call get_activity_preferences() to check if user has stored preferences
    3. If user mentions preferences in their query (e.g., "I like hiking"), call store_user_preferences() to save them
    4. Call get_weather_data(city) to get weather forecast
    5. Call generate_analysis_code(weather_data) to create classification code
    6. Call execute_code(python_code) to classify weather days
    7. Generate personalized activity recommendations based on weather and preferences
    8. Call store_activity_plan(city, plan) to save the plan in memory for future reference
    9. Store results.md in S3 Bucket: {RESULTS_BUCKET} via use_aws tool
    
    Memory stores user preferences across sessions. Always check memory first and save new preferences/plans."""
    
    return Agent(
        tools=[get_weather_data, generate_analysis_code, execute_code, store_user_preferences, get_activity_preferences, store_activity_plan, use_aws],
        system_prompt=system_prompt,
        name="WeatherActivityPlanner"
    )

async def async_main(query=None):
    """Main async function"""
    console.print("🌤️ Weather-Based Activity Planner")
    console.print("=" * 30)
    
    agent = create_weather_agent()
    
    query = query or "What should I do this weekend in Richmond VA?"
    console.print(f"\n[bold blue]🔍 Query:[/bold blue] {query}")
    
    try:
        os.environ["BYPASS_TOOL_CONSENT"] = "True"
        result = agent(query)
        return {"status": "completed", "result": result.message['content'][0]['text']}
        
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    console.print("🚀 Strands Agent Running on EKS")
    console.print("Waiting for requests...")
    console.print("Press Ctrl+C to exit")
    
    # Keep container running
    import time
    while True:
        time.sleep(3600)
