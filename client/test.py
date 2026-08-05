import fastmcp.client

print(dir(fastmcp.client))
from fastmcp.client import Client

print(Client)
from fastmcp.client import Client
import inspect

print(inspect.signature(Client))
from fastmcp import Context

print(dir(Context))
from fastmcp import Context
import inspect

print(inspect.signature(Context.sample))
from mcp.types import SamplingCapability

print(SamplingCapability)