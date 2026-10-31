"""OpenAPI 3.0.3 Specification Definition for Web-Dash Public API (Step 5.14)."""
from typing import Dict, Any

OPENAPI_SPEC: Dict[str, Any] = {
    "openapi": "3.0.3",
    "info": {
        "title": "Web-Dash Enterprise Network Automation API",
        "version": "2.0.0",
        "description": (
            "Carrier-grade, air-gap safe REST API for Huawei VRP network automation, "
            "inventory discovery, config backup/compliance, alarm management, and telemetry."
        ),
        "contact": {
            "name": "NOC Engineering Team",
            "email": "noc-automation@local.domain",
        },
    },
    "servers": [
        {"url": "/", "description": "Current Web-Dash Host Server"}
    ],
    "components": {
        "securitySchemes": {
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "wbd_<token>",
                "description": "API Bearer token issued via /api/v1/tokens",
            },
            "CookieAuth": {
                "type": "apiKey",
                "in": "cookie",
                "name": "session",
                "description": "Browser session cookie",
            },
        },
        "schemas": {
            "ApiToken": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "token_prefix": {"type": "string"},
                    "user_id": {"type": "integer"},
                    "username": {"type": "string"},
                    "scopes": {"type": "array", "items": {"type": "string"}},
                    "revoked": {"type": "boolean"},
                    "is_active": {"type": "boolean"},
                    "created_at": {"type": "string", "format": "date-time"},
                    "expires_at": {"type": "string", "format": "date-time", "nullable": True},
                    "last_used_at": {"type": "string", "format": "date-time", "nullable": True},
                },
            },
            "Device": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "mgmt_ip": {"type": "string"},
                    "role": {"type": "string"},
                    "province": {"type": "string"},
                    "site": {"type": "string"},
                    "health_status": {"type": "string"},
                    "enabled": {"type": "boolean"},
                },
            },
            "Job": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string"},
                    "status": {"type": "string", "enum": ["queued", "running", "succeeded", "failed", "cancelled"]},
                    "mode": {"type": "string", "enum": ["apply", "dry_run"]},
                    "created_by": {"type": "string"},
                    "created_at": {"type": "string", "format": "date-time"},
                    "finished_at": {"type": "string", "format": "date-time", "nullable": True},
                    "summary": {"type": "object"},
                },
            },
            "NocDigest": {
                "type": "object",
                "properties": {
                    "generated_at": {"type": "string", "format": "date-time"},
                    "status": {"type": "string", "enum": ["HEALTHY", "ATTENTION_NEEDED", "CRITICAL"]},
                    "highlights": {"type": "array", "items": {"type": "string"}},
                    "metrics": {"type": "object"},
                    "alarms": {"type": "object"},
                    "down_links": {"type": "object"},
                    "licenses": {"type": "object"},
                    "jobs": {"type": "object"},
                    "compliance": {"type": "object"},
                },
            },
        },
    },
    "security": [{"BearerAuth": []}, {"CookieAuth": []}],
    "paths": {
        "/api/v1/openapi.json": {
            "get": {
                "summary": "Retrieve OpenAPI Specification",
                "description": "Returns standard OpenAPI 3.0.3 specification JSON.",
                "responses": {
                    "200": {"description": "OpenAPI JSON document"}
                },
            }
        },
        "/api/v1/tokens": {
            "get": {
                "summary": "List API Tokens",
                "description": "Retrieve issued API tokens for automation.",
                "responses": {
                    "200": {
                        "description": "List of API tokens",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "tokens": {"type": "array", "items": {"$ref": "#/components/schemas/ApiToken"}}
                                    },
                                }
                            }
                        },
                    }
                },
            },
            "post": {
                "summary": "Create API Token",
                "description": "Issue a new scoped API token. Raw secret is returned only once.",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["name"],
                                "properties": {
                                    "name": {"type": "string"},
                                    "scopes": {"type": "array", "items": {"type": "string"}},
                                    "expires_in_days": {"type": "integer", "default": 30},
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "201": {"description": "Token created with raw secret"}
                },
            },
        },
        "/api/v1/tokens/{token_id}": {
            "delete": {
                "summary": "Revoke API Token",
                "parameters": [
                    {"name": "token_id", "in": "path", "required": True, "schema": {"type": "integer"}}
                ],
                "responses": {
                    "200": {"description": "Token successfully revoked"}
                },
            }
        },
        "/api/v1/devices": {
            "get": {
                "summary": "List Inventory Devices",
                "parameters": [
                    {"name": "province", "in": "query", "schema": {"type": "string"}},
                    {"name": "role", "in": "query", "schema": {"type": "string"}},
                ],
                "responses": {
                    "200": {"description": "List of devices"}
                },
            }
        },
        "/api/v1/jobs": {
            "get": {
                "summary": "List Jobs",
                "parameters": [
                    {"name": "status", "in": "query", "schema": {"type": "string"}},
                    {"name": "type", "in": "query", "schema": {"type": "string"}},
                ],
                "responses": {
                    "200": {"description": "List of jobs"}
                },
            },
            "post": {
                "summary": "Submit Automation Job",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "required": ["job_type"],
                                "properties": {
                                    "job_type": {"type": "string"},
                                    "mode": {"type": "string", "default": "apply"},
                                    "params": {"type": "object"},
                                    "devices": {"type": "array", "items": {"type": "string"}},
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "201": {"description": "Job submitted"}
                },
            },
        },
        "/api/v1/jobs/{job_id}": {
            "get": {
                "summary": "Get Job Details and Status",
                "parameters": [
                    {"name": "job_id", "in": "path", "required": True, "schema": {"type": "string"}}
                ],
                "responses": {
                    "200": {"description": "Job record"}
                },
            }
        },
        "/api/v1/reports/digest": {
            "get": {
                "summary": "Daily NOC Operations Digest",
                "parameters": [
                    {"name": "hours", "in": "query", "schema": {"type": "integer", "default": 24}}
                ],
                "responses": {
                    "200": {
                        "description": "NOC digest data",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/NocDigest"}
                            }
                        },
                    }
                },
            }
        },
        "/api/v1/reports/digest/export": {
            "get": {
                "summary": "Export Daily NOC Digest",
                "parameters": [
                    {"name": "format", "in": "query", "schema": {"type": "string", "enum": ["xlsx", "csv", "json"], "default": "xlsx"}},
                    {"name": "hours", "in": "query", "schema": {"type": "integer", "default": 24}},
                ],
                "responses": {
                    "200": {"description": "File download attachment"}
                },
            }
        },
        "/api/v1/reports/export": {
            "post": {
                "summary": "Unified Data Export",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "format": {"type": "string", "enum": ["csv", "xlsx", "json"]},
                                    "filename": {"type": "string"},
                                    "fieldnames": {"type": "array", "items": {"type": "string"}},
                                    "data": {"type": "array", "items": {"type": "object"}},
                                },
                            }
                        }
                    },
                },
                "responses": {
                    "200": {"description": "File download"}
                },
            }
        },
    },
}
