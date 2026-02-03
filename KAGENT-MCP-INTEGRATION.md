# KAgent MCP Integration - Agent Core as MCP Tools

## Overview

This branch implements Agent Core capabilities (Memory, Browser, Code Interpreter) as **MCP (Model Context Protocol) Tools** that can be used with KAgent. This creates a declarative, GitOps-native deployment where:

1. **Terraform** provisions Agent Core resources (Wave 0)
2. **MCP Server** exposes Agent Core as 6 tools (Wave 1)
3. **RemoteMCPServer CRD** registers tools with KAgent (Wave 2)
4. **Agent** (LangGraph or Strands BYO) uses the tools (Wave 3)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Kubernetes Cluster                       │
│                                                             │
│  Wave 0: Terraform (via Tofu Controller)                   │
│  ┌─────────────────────────────────────────┐                │
│  │ - Agent Core Memory                     │                │
│  │ - Agent Core Browser                    │                │
│  │ - Code Interpreter                      │                │
│  │ - IAM Roles + Pod Identity              │                │
│  │ - Outputs → Secret                      │                │
│  └─────────────────────────────────────────┘                │
│                    ↓                                        │
│  Wave 1: MCP Server Deployment                             │
│  ┌─────────────────────────────────────────┐                │
│  │ Single MCP Server with 6 tools:         │                │
│  │ 1. store_memory()                       │                │
│  │ 2. retrieve_memory()                    │                │
│  │ 3. browse_web()                         │                │
│  │ 4. extract_data()                       │                │
│  │ 5. execute_python()                     │                │
│  │ 6. execute_code()                       │                │
│  │                                         │                │
│  │ Service: agent-core-mcp:8080/mcp        │                │
│  └─────────────────────────────────────────┘                │
│                    ↓                                        │
│  Wave 2: RemoteMCPServer CRD                               │
│  ┌─────────────────────────────────────────┐                │
│  │ Registers MCP server with KAgent        │                │
│  │ URL: http://agent-core-mcp:8080/mcp     │                │
│  └─────────────────────────────────────────┘                │
│                    ↓                                        │
│  Wave 3: KAgent Agent                                      │
│  ┌─────────────────────────────────────────┐                │
│  │ References: agent-core-tools            │                │
│  │ Type: langgraph OR byo (Strands)        │                │
│  │ Checkpointer: postgres                  │                │
│  └─────────────────────────────────────────┘                │
└─────────────────────────────────────────────────────────────┘
```

## Directory Structure

```
agent-core-pocs/
├── mcp-server/                    # NEW: MCP Server implementation
│   ├── server.py                  # FastMCP server with 6 tools
│   ├── Dockerfile                 # Container image
│   ├── requirements.txt           # Python dependencies
│   └── README.md                  # MCP server documentation
│
├── gitops/agent-core-stack/templates/
│   ├── terraform-resource.yaml    # Wave 0: Terraform
│   ├── mcp-server.yaml            # Wave 1: MCP Server deployment
│   ├── remote-mcp-server.yaml     # Wave 2: RemoteMCPServer CRD
│   └── kagent-agent.yaml          # Wave 3: KAgent Agent CRD
│
├── examples/
│   ├── langgraph-agent/           # Example LangGraph agent
│   └── strands-byo-agent/         # Example Strands BYO agent
│
├── KAGENT-MCP-INTEGRATION.md      # This file
└── README.md                      # Main documentation (unchanged)
```

## Prerequisites

### On Your ML Cluster

1. **KAgent Operator** - Already installed
2. **ArgoCD** - For GitOps deployment
3. **Flux** - For Tofu Controller
4. **Tofu Controller** - For Terraform automation
5. **Postgres** - For KAgent checkpointing

### Installation (if not already installed)

```bash
# ArgoCD
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Flux
kubectl apply -f https://github.com/fluxcd/flux2/releases/latest/download/install.yaml

# Tofu Controller
kubectl apply -f argocd/tofu-controller-application.yaml
```

## Deployment

### Step 1: Configure values.yaml

```yaml
version: v6-kagent
projectName: ekspoc-v6-kagent
awsRegion: us-east-1
eksClusterName: ml-cluster  # Your ML cluster name

# Agent Core capabilities
capabilities:
  memory: true
  browser: true
  codeInterpreter: true

# MCP Server image
mcpServer:
  image:
    repository: 940019131157.dkr.ecr.us-east-1.amazonaws.com/agent-core-mcp
    tag: latest
    pullPolicy: Always

# KAgent configuration
kagent:
  enabled: true
  agentType: langgraph  # or 'byo' for Strands
  checkpointer:
    type: postgres
    secretName: postgres-credentials

namespace: agent-core-infra
```

### Step 2: Deploy

```bash
# Commit and push
git add .
git commit -m "Deploy KAgent MCP integration v6"
git push

# Deploy via ArgoCD
kubectl apply -f argocd/agent-core-stack.yaml
```

### Step 3: Monitor Deployment

```bash
# Watch Terraform (Wave 0)
kubectl get terraform agent-core-components-v6-kagent -n agent-core-infra -w

# Watch MCP Server (Wave 1)
kubectl get pods -n agent-core-infra -l app=agent-core-mcp-v6-kagent -w

# Watch RemoteMCPServer (Wave 2)
kubectl get remotemcpserver agent-core-tools-v6-kagent -n agent-core-infra

# Watch Agent (Wave 3)
kubectl get agent weather-agent-v6-kagent -n agent-core-infra
```

## MCP Tools Available

### Memory Tools

**1. store_memory(content, actor_id, session_id)**
- Stores information in Agent Core Memory
- Parameters:
  - `content` (str): Information to store
  - `actor_id` (str): User identifier (default: "user")
  - `session_id` (str): Session identifier (default: "default")
- Returns: `{"status": "success", "message": "..."}`

**2. retrieve_memory(query, max_results)**
- Retrieves information from Agent Core Memory
- Parameters:
  - `query` (str): Search query
  - `max_results` (int): Maximum results (default: 5)
- Returns: `{"status": "success", "results": [...]}`

### Browser Tools

**3. browse_web(url, task)**
- Browses web and extracts data using Agent Core Browser
- Parameters:
  - `url` (str): Target URL
  - `task` (str): Task description
- Returns: `{"status": "success", "data": "..."}`

**4. extract_data(url, selector)**
- Extracts specific data from a webpage
- Parameters:
  - `url` (str): Target URL
  - `selector` (str): CSS selector or extraction pattern
- Returns: `{"status": "success", "data": "..."}`

### Code Interpreter Tools

**5. execute_python(code)**
- Executes Python code using Agent Core Code Interpreter
- Parameters:
  - `code` (str): Python code to execute
- Returns: `{"status": "success", "result": {...}}`

**6. execute_code(code, language)**
- Executes code in specified language
- Parameters:
  - `code` (str): Code to execute
  - `language` (str): Programming language (default: "python")
- Returns: `{"status": "success", "result": "..."}`

## Using Tools in Your Agent

### Option A: LangGraph Agent

```python
from langgraph.prebuilt import create_react_agent
from langchain_aws import ChatBedrockConverse

# KAgent provides MCP tools automatically
# Agent must explicitly call them by name

model = ChatBedrockConverse(model="anthropic.claude-3-sonnet")

# Define workflow
def weather_workflow(state):
    # 1. Retrieve preferences from memory
    preferences = retrieve_memory("user activity preferences")
    
    # 2. Browse weather data
    weather = browse_web("https://weather.gov", "Get Tampa forecast")
    
    # 3. Execute analysis code
    analysis = execute_python(f"classify_weather({weather})")
    
    # 4. Store plan in memory
    store_memory(f"Activity plan: {analysis}")
    
    return {"result": analysis}

agent = create_react_agent(model, tools=[weather_workflow])
```

### Option B: Strands BYO Agent

```python
from strands import Agent, tool
import requests

MCP_SERVER_URL = "http://agent-core-mcp:8080/mcp"

# Wrap MCP tools as Strands tools
@tool
def store_memory(content: str) -> dict:
    """Store information in memory"""
    response = requests.post(
        f"{MCP_SERVER_URL}/tools/store_memory",
        json={"content": content}
    )
    return response.json()

@tool
def retrieve_memory(query: str) -> dict:
    """Retrieve information from memory"""
    response = requests.post(
        f"{MCP_SERVER_URL}/tools/retrieve_memory",
        json={"query": query}
    )
    return response.json()

# Create agent with wrapped tools
agent = Agent(
    tools=[store_memory, retrieve_memory, ...],
    system_prompt="You are a weather planning assistant..."
)
```

## Testing

### Test MCP Server Directly

```bash
# Port-forward to MCP server
kubectl port-forward -n agent-core-infra svc/agent-core-mcp-v6-kagent 8080:8080

# Test store_memory
curl -X POST http://localhost:8080/mcp/tools/store_memory \
  -H "Content-Type: application/json" \
  -d '{"content": "User loves hiking", "actor_id": "user123"}'

# Test retrieve_memory
curl -X POST http://localhost:8080/mcp/tools/retrieve_memory \
  -H "Content-Type: application/json" \
  -d '{"query": "user preferences", "max_results": 5}'
```

### Test via KAgent Agent

```bash
# Invoke agent
kubectl exec -it -n agent-core-infra deployment/weather-agent-v6-kagent -- \
  curl -X POST http://localhost:8000/invoke \
  -H "Content-Type: application/json" \
  -d '{"input": "What should I do in Tampa?", "thread_id": "user-123"}'
```

## Key Differences from Main Branch

| Feature | Main Branch | KAgent MCP Branch |
|---------|-------------|-------------------|
| Deployment | Kubernetes Deployment | KAgent Agent CRD |
| Tools | Embedded in agent code | MCP Server (separate) |
| Tool Discovery | N/A | RemoteMCPServer CRD |
| Checkpointing | Manual | KAgent automatic |
| API | None | KAgent REST API |
| State Management | None | KAgent + Postgres |
| Agent Type | Strands only | LangGraph or Strands BYO |

## Benefits

1. **Declarative Everything** - Infrastructure, tools, and agents all via CRDs
2. **Tool Reusability** - Multiple agents can use same MCP server
3. **Independent Scaling** - Scale MCP server and agents separately
4. **Checkpointing** - Automatic conversation state management
5. **REST API** - KAgent provides API automatically
6. **GitOps Native** - All changes via Git commits

## Troubleshooting

### MCP Server Not Starting

```bash
# Check logs
kubectl logs -n agent-core-infra -l app=agent-core-mcp-v6-kagent

# Check secret
kubectl get secret agent-core-outputs-v6-kagent -n agent-core-infra
```

### RemoteMCPServer Not Registered

```bash
# Check CRD
kubectl describe remotemcpserver agent-core-tools-v6-kagent -n agent-core-infra

# Test connectivity
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
  curl http://agent-core-mcp-v6-kagent:8080/mcp
```

### Agent Can't Access Tools

```bash
# Check agent logs
kubectl logs -n agent-core-infra -l app=weather-agent-v6-kagent

# Verify RemoteMCPServer reference
kubectl get agent weather-agent-v6-kagent -n agent-core-infra -o yaml
```

## Next Steps

1. Review MCP server implementation in `mcp-server/`
2. Test with example agents in `examples/`
3. Customize agent logic for your use case
4. Deploy to production cluster

## Support

For issues or questions:
- Check `mcp-server/README.md` for MCP server details
- Review KAgent documentation: https://kagent.dev/docs
- See examples in `examples/` directory
