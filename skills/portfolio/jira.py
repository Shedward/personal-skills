# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=1.26,<2"]
# ///
"""Read Jira inclusion links through the configured Streamable HTTP MCP server."""

import argparse
import asyncio
import json
import os
import sys
import tomllib
from pathlib import Path

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from collect import select_issues


def connection():
    codex = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "config.toml"
    servers = tomllib.loads(codex.read_text()).get("mcp_servers", {}) if codex.is_file() else {}
    server = servers.get("jira-mcp") or servers.get("jira")
    if not server:
        claude = Path.home() / ".claude.json"
        servers = json.loads(claude.read_text()).get("mcpServers", {}) if claude.is_file() else {}
        server = servers.get("jira-mcp") or servers.get("jira")
    if not server or not server.get("url"):
        raise ValueError("Нужен HTTP MCP-сервер jira-mcp или jira в настройках Codex или Claude")
    headers = dict(server.get("http_headers") or server.get("headers") or {})
    headers.update({name: os.environ[var] for name, var in server.get("env_http_headers", {}).items()})
    if server.get("bearer_token_env_var"):
        headers["Authorization"] = "Bearer " + os.environ[server["bearer_token_env_var"]]
    return server["url"], headers


async def get_issues(session, keys, fields):
    response = await session.call_tool("get_jira_issue", {
        "issue_keys": keys if len(keys) > 1 else keys[0], "fields": fields,
    })
    if response.isError:
        raise ValueError("Jira MCP вернул ошибку get_jira_issue")
    data = response.structuredContent
    if data is None:
        data = json.loads(response.content[0].text)
    if isinstance(data, dict) and "result" in data:
        data = data["result"]
    return {item["key"]: item for item in (data if isinstance(data, list) else [data])}


async def collect(args):
    url, headers = connection()
    async with httpx.AsyncClient(headers=headers, timeout=30) as http:
        async with streamable_http_client(url, http_client=http) as (reader, writer, _):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                parents = await get_issues(session, [args.key, *args.via],
                                           ["summary", "status", "issuelinks", "description"])
                portfolio, issues = select_issues(parents, args.key, vars(args))
                for start in range(0, len(issues), 20):
                    batch = issues[start:start + 20]
                    details = await get_issues(session, [i["key"] for i in batch], ["description"])
                    for issue in batch:
                        issue["description"] = details[issue["key"]]["fields"].get("description")
                return {"portfolio": portfolio, "issues": issues}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("key")
    parser.add_argument("via", nargs="*")
    parser.add_argument("--child-project")
    parser.add_argument("--jira-url")
    try:
        print(json.dumps(asyncio.run(collect(parser.parse_args())), ensure_ascii=False))
    except Exception as error:
        while isinstance(error, BaseExceptionGroup) and len(error.exceptions) == 1:
            error = error.exceptions[0]
        sys.exit(f"Jira MCP: {type(error).__name__}: {error}")
